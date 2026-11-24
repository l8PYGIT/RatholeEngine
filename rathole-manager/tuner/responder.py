"""HMAC-authenticated peer responder daemon for rathole-tuner."""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import threading
import time

from . import DEFAULT_CTRL_PORT, DEFAULT_DATA_PORT, TUNER_VERSION
from .audit import run_non_kernel_audit
from .probes import ProbeServer
from .profile import ProfileValidationError, _validate_side_config
from .protocol import ProtocolError, recv_frame, send_frame, sign_frame, verify_frame
from .sysstate import (
    MockSysDriver,
    RealLinuxDriver,
    apply_candidate,
    capture_snapshot,
    discover_capabilities,
    read_net_counters,
    restore_snapshot,
)
from .watchdog import WatchdogController


class TunerResponder:
    """Hosts control listener and bulk/echo/UDP probe server for an orchestrator."""

    def __init__(
        self,
        bind_host: str = "0.0.0.0",
        ctrl_port: int = DEFAULT_CTRL_PORT,
        data_port: int = DEFAULT_DATA_PORT,
        token: str = "",
        idle_timeout: int = 600,
        driver=None,
        state_dir: str | None = None,
        pidfile: str | None = None,
    ):
        self.bind_host = bind_host
        self._req_ctrl_port = int(ctrl_port)
        self._req_data_port = int(data_port)
        self.ctrl_port = 0
        self.data_tcp_port = 0
        self.data_udp_port = 0
        self.token = token
        self.idle_timeout = max(10, int(idle_timeout))
        self.driver = driver if driver is not None else RealLinuxDriver()
        self.state_dir = state_dir or "/var/lib/rathole-tuner/responder"
        self.pidfile = pidfile

        self._ctrl_sock: socket.socket | None = None
        self._probe = ProbeServer(self.bind_host, tcp_port=self._req_data_port, udp_port=self._req_data_port)
        self._stop_ev = threading.Event()
        self._seen_nonces: dict[str, int] = {}
        self._snapshot: dict | None = None
        self._session_id = secrets.token_hex(4)
        self._watchdog = WatchdogController(self.state_dir, session_id=f"resp_{self._session_id}")
        self._caps_cache: dict | None = None
        self._last_activity = time.monotonic()
        self._carrier_proc: subprocess.Popen | None = None

    def start(self) -> None:
        self._stop_ev.clear()
        self._probe.start()
        self.data_tcp_port = self._probe.tcp_port
        self.data_udp_port = self._probe.udp_port

        cs = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        cs.bind((self.bind_host, self._req_ctrl_port))
        cs.listen(16)
        cs.settimeout(0.4)
        self._ctrl_sock = cs
        self.ctrl_port = cs.getsockname()[1]
        self._last_activity = time.monotonic()

        if self.pidfile:
            os.makedirs(os.path.dirname(self.pidfile), exist_ok=True)
            with open(self.pidfile, "w", encoding="utf-8") as fh:
                fh.write(f"{os.getpid()}\n")

    def stop(self) -> None:
        self._stop_ev.set()
        try:
            self._revert_and_disarm()
        finally:
            self._probe.stop()
            if self._ctrl_sock is not None:
                try:
                    self._ctrl_sock.close()
                except OSError:
                    pass
                self._ctrl_sock = None
            if self.pidfile:
                try:
                    os.remove(self.pidfile)
                except OSError:
                    pass

    def _revert_and_disarm(self) -> None:
        self._stop_carrier_proc()
        if self._snapshot is not None:
            try:
                restore_snapshot(self.driver, self._snapshot, session_id=self._session_id)
            except Exception:
                pass
            self._snapshot = None
        try:
            self._watchdog.disarm()
        except Exception:
            pass

    def _stop_carrier_proc(self) -> None:
        if self._carrier_proc is not None:
            try:
                self._carrier_proc.terminate()
                self._carrier_proc.wait(timeout=2.0)
            except Exception:
                try:
                    self._carrier_proc.kill()
                except Exception:
                    pass
            self._carrier_proc = None

    def _handle_action(self, action: str, payload: dict) -> dict:
        self._last_activity = time.monotonic()

        if action == "hello":
            return {
                "ok": True,
                "version": TUNER_VERSION,
                "data_tcp_port": self.data_tcp_port,
                "data_udp_port": self.data_udp_port,
            }
        if action == "caps":
            peer_ip = str(payload.get("peer_ip", "") or "")
            self._caps_cache = discover_capabilities(self.driver, peer_ip=peer_ip)
            return {"ok": True, "caps": self._caps_cache}
        if action == "snapshot":
            iface = str(payload.get("iface", "") or (self._caps_cache or {}).get("iface", ""))
            peer_ip = str(payload.get("peer_ip", "") or "")
            mode = str(payload.get("mode", "brutal") or "brutal")
            os.makedirs(self.state_dir, exist_ok=True)
            snap_file = os.path.join(self.state_dir, f"pre-{self._session_id}.json")
            self._snapshot = capture_snapshot(self.driver, iface=iface, peer_ip=peer_ip, save_path=snap_file)
            if mode == "brutal" and not isinstance(self.driver, MockSysDriver):
                self._watchdog.arm(snap_file, ttl_s=45.0)
            return {"ok": True, "iface": self._snapshot["iface"]}
        if action == "heartbeat":
            self._watchdog.heartbeat()
            return {"ok": True, "ts": int(time.time())}
        if action == "apply_cand":
            raw_cfg = payload.get("config") or {}
            try:
                cfg = _validate_side_config(raw_cfg, "remote_cand")
            except ProfileValidationError as exc:
                return {"ok": False, "error": str(exc)}
            caps = self._caps_cache or discover_capabilities(self.driver)
            iface = str(payload.get("iface") or caps["iface"])
            sess = str(payload.get("session_id") or self._session_id)
            res = apply_candidate(
                self.driver,
                cfg,
                iface=iface,
                session_id=sess,
                ram_mb=caps["ram_mb"],
                ipv6_active=caps["ipv6_active"],
            )
            return {"ok": True, **res}
        if action == "revert":
            sess = str(payload.get("session_id") or self._session_id)
            if self._snapshot is not None:
                restore_snapshot(self.driver, self._snapshot, session_id=sess)
            return {"ok": True}
        if action == "stats":
            caps = self._caps_cache or discover_capabilities(self.driver)
            return {"ok": True, "counters": read_net_counters(self.driver, caps["iface"])}
        if action == "audit":
            return {"ok": True, "audit": run_non_kernel_audit(self.driver, role="node")}
        if action == "carrier_start":
            self._stop_carrier_proc()
            kind = str(payload.get("kind", "") or "")
            if kind == "kcp":
                bin_p = self.driver.which("kcptun-server") or "/usr/local/bin/kcptun-server"
                if not (bin_p and os.path.isfile(bin_p) and os.access(bin_p, os.X_OK)):
                    return {"ok": False, "error": "kcptun-server missing"}
                listen_port = int(payload.get("listen_port", 29920))
                target_port = int(payload.get("target_port", self.data_tcp_port))
                mtu = max(1200, min(1450, int(payload.get("mtu", 1350))))
                mode_k = str(payload.get("mode", "fast2") or "fast2")
                if mode_k not in ("fast", "fast2", "fast3", "normal"):
                    mode_k = "fast2"
                ds = max(1, min(30, int(payload.get("datashard", 10))))
                ps = max(0, min(20, int(payload.get("parityshard", 3))))
                k = str(payload.get("key", self.token[:24]) or "tuner-kcp")
                self._carrier_proc = subprocess.Popen(
                    [
                        bin_p,
                        "-t", f"127.0.0.1:{target_port}",
                        "-l", f":{listen_port}",
                        "-key", k, "-crypt", "aes-128",
                        "-mode", mode_k, "-mtu", str(mtu),
                        "-sndwnd", "2048", "-rcvwnd", "2048",
                        "-datashard", str(ds), "-parityshard", str(ps),
                        "-nocomp",
                    ],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                time.sleep(0.35)
                if self._carrier_proc.poll() is not None:
                    self._stop_carrier_proc()
                    return {"ok": False, "error": "kcptun-server exited early"}
                return {"ok": True, "kind": "kcp", "listen_port": listen_port}
            return {"ok": True, "status": "noop"}
        if action == "carrier_stop":
            self._stop_carrier_proc()
            return {"ok": True}
        if action == "shutdown":
            self._revert_and_disarm()
            self._stop_ev.set()
            return {"ok": True}
        return {"ok": False, "error": "unsupported action"}

    def _serve_client(self, conn: socket.socket) -> None:
        conn.settimeout(15.0)
        try:
            while not self._stop_ev.is_set():
                try:
                    frame = recv_frame(conn)
                except socket.timeout:
                    if time.monotonic() - self._last_activity > self.idle_timeout:
                        self._stop_ev.set()
                        break
                    continue
                except ProtocolError:
                    break
                try:
                    verified = verify_frame(self.token, frame, seen_nonces=self._seen_nonces)
                except ProtocolError as exc:
                    err = sign_frame(self.token, frame.get("action", "hello") if frame.get("action") in ("hello", "caps", "snapshot", "heartbeat", "apply_cand", "revert", "stats", "audit", "shutdown") else "hello", {"ok": False, "error": str(exc)})
                    send_frame(conn, err)
                    continue
                action = verified["action"]
                resp_payload = self._handle_action(action, verified["payload"])
                send_frame(conn, sign_frame(self.token, action, resp_payload, frame_id=verified["id"]))
                if action == "shutdown":
                    break
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def serve_forever(self) -> None:
        if self._ctrl_sock is None:
            self.start()
        try:
            while not self._stop_ev.is_set():
                if time.monotonic() - self._last_activity > self.idle_timeout:
                    break
                try:
                    conn, _ = self._ctrl_sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                self._serve_client(conn)
        finally:
            self.stop()
