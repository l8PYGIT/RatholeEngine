"""Orchestrator coordinating bidirectional sweeps, A/B testing, and profile export."""

from __future__ import annotations

import copy
import datetime
import json
import os
import secrets
import socket
import threading
import time

from .audit import run_non_kernel_audit
from .probes import probe_trial, probe_unloaded_rtt
from .profile import build_profile, clamp_config_for_ram, encode_profile_b64, load_profile_any
from .protocol import ControlClient
from .scoring import diagnose_findings, raw_throughput, score_trials
from .sweep import _config_from_snapshot, run_staged_sweep
from .sysstate import MockSysDriver, RealLinuxDriver, apply_candidate, capture_snapshot, discover_capabilities, restore_snapshot
from .watchdog import WatchdogController


def _atomic_write_json(path: str, data: dict, mode: int = 0o600) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def _trim_trial_summary(t: dict) -> dict:
    return {
        "id": t.get("id"),
        "name": t.get("name"),
        "throughput_mbps": round(raw_throughput(t), 2),
        "throughput_1_mbps": t.get("throughput_1_mbps"),
        "throughput_n_mbps": t.get("throughput_n_mbps"),
        "throughput_bidir_mbps": t.get("throughput_bidir_mbps"),
        "unloaded_rtt_p50_ms": t.get("unloaded_rtt_p50_ms"),
        "loaded_rtt_p95_ms": t.get("loaded_rtt_p95_ms"),
        "jitter_ms": t.get("jitter_ms"),
        "retrans_pct": t.get("retrans_pct"),
        "udp_loss_pct": t.get("udp_loss_pct"),
        "stability_cov": t.get("stability_cov"),
        "disqualified": bool(t.get("disqualified")),
        "disqualify_reason": t.get("disqualify_reason"),
        "subscores": t.get("subscores") or {},
        "scores": t.get("scores") or {},
    }


def _strip_private_cand_keys(cfg: dict) -> dict:
    out = copy.deepcopy(cfg or {})
    out.pop("name", None)
    out.pop("socket_mss", None)
    return out


class TunerOrchestrator:
    """Runs full 6-stage benchmarks, live A/B profile tests, and N-way comparisons."""

    def __init__(
        self,
        peer_host: str,
        ctrl_port: int,
        token: str,
        mode: str = "brutal",
        goal: str = "balanced",
        deep: bool = False,
        tags: dict | None = None,
        out_dir: str | None = None,
        driver=None,
        state_dir: str | None = None,
        fast_test: bool = False,
        progress_cb=None,
        job_id: str | None = None,
    ):
        self.peer_host = peer_host
        self.ctrl_port = int(ctrl_port)
        self.token = token
        self.mode = mode
        self.goal = goal
        self.deep = bool(deep)
        self.tags = dict(tags or {})
        self.job_id = job_id or f"job_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}"
        self.state_dir = state_dir or "/var/lib/rathole-tuner"
        self.out_dir = out_dir or os.path.join(self.state_dir, "jobs", self.job_id)
        self.driver = driver if driver is not None else RealLinuxDriver()
        self.fast_test = bool(fast_test)
        self._user_progress_cb = progress_cb
        self._session_id = secrets.token_hex(4)
        self._watchdog = WatchdogController(os.path.join(self.state_dir, "wd"), session_id=f"orch_{self._session_id}")
        self._t0 = time.monotonic()

    def _resolve_peer_ip(self) -> str:
        try:
            return socket.gethostbyname(self.peer_host)
        except OSError:
            return self.peer_host

    def _emit_progress(self, info: dict) -> None:
        payload = {
            "job_id": self.job_id,
            "mode": self.mode,
            "goal": self.goal,
            "elapsed_s": round(time.monotonic() - self._t0, 2),
            **info,
        }
        prog_file = os.path.join(self.state_dir, "jobs", self.job_id, "progress.json")
        try:
            _atomic_write_json(prog_file, payload, mode=0o600)
        except OSError:
            pass
        if self._user_progress_cb:
            self._user_progress_cb(payload)

    def _start_heartbeat(self, client: ControlClient) -> tuple[threading.Event, threading.Thread]:
        stop_ev = threading.Event()

        def _beat():
            while not stop_ev.wait(5.0):
                try:
                    self._watchdog.heartbeat()
                    client.call("heartbeat", {"ts": int(time.time())}, timeout=4.0)
                except Exception:
                    pass

        thr = threading.Thread(target=_beat, daemon=True)
        thr.start()
        return stop_ev, thr

    def _setup_session(self, client: ControlClient) -> tuple[dict, dict, int, int, dict]:
        peer_ip = self._resolve_peer_ip()
        hello = client.call("hello", {"role": "orchestrator"})
        data_tcp_port = int(hello.get("data_tcp_port", 29891))
        data_udp_port = int(hello.get("data_udp_port", data_tcp_port))

        caps_local = discover_capabilities(self.driver, peer_ip=peer_ip)
        caps_remote = client.call("caps", {"peer_ip": ""}).get("caps") or {}

        os.makedirs(self.state_dir, exist_ok=True)
        snap_path = os.path.join(self.state_dir, "snapshots", f"pre-{self._session_id}.json")
        local_snap = capture_snapshot(self.driver, iface=caps_local["iface"], peer_ip=peer_ip, save_path=snap_path)

        client.call("snapshot", {"iface": caps_remote.get("iface", ""), "mode": self.mode})
        if self.mode == "brutal" and not isinstance(self.driver, MockSysDriver):
            self._watchdog.arm(snap_path, ttl_s=45.0)
        return caps_local, caps_remote, data_tcp_port, data_udp_port, local_snap

    def _teardown_session(self, client: ControlClient, local_snap: dict | None) -> None:
        if local_snap is not None:
            try:
                restore_snapshot(self.driver, local_snap, session_id=self._session_id)
            except Exception:
                pass
        try:
            self._watchdog.disarm()
        except Exception:
            pass
        try:
            client.call("revert", {"session_id": self._session_id}, timeout=5.0)
        except Exception:
            pass
        try:
            client.call("shutdown", {}, timeout=5.0)
        except Exception:
            pass
        client.close()

    def run(self) -> dict:
        """Run complete 6-stage benchmark, score all 4 goals, build portable profile, restore baseline."""
        client = ControlClient(self.peer_host, self.ctrl_port, self.token, timeout=15.0)
        local_snap = None
        hb_ev = None
        hb_thr = None
        try:
            client.connect()
            caps_local, caps_remote, tcp_port, udp_port, local_snap = self._setup_session(client)
            hb_ev, hb_thr = self._start_heartbeat(client)

            sweep_res = run_staged_sweep(
                ctrl_client=client,
                host=self.peer_host,
                data_tcp_port=tcp_port,
                data_udp_port=udp_port,
                local_driver=self.driver,
                caps_local=caps_local,
                caps_remote=caps_remote,
                mode=self.mode,
                goal=self.goal,
                deep=self.deep,
                fast_test=self.fast_test,
                session_id=self._session_id,
                progress_cb=self._emit_progress,
            )

            audit_local = run_non_kernel_audit(self.driver, role="iran")
            audit_remote = (client.call("audit", {}) or {}).get("audit") or {}

            winner_cfg = _strip_private_cand_keys(sweep_res["winner"].get("config") or {})
            iran_cfg = clamp_config_for_ram(winner_cfg, caps_local["ram_mb"])
            node_cfg = clamp_config_for_ram(winner_cfg, caps_remote.get("ram_mb", 1024))
            node_cfg["recommended_carrier"] = sweep_res["recommended_carrier"]

            diagnostics = diagnose_findings(
                sweep_res["baseline"],
                sweep_res["winner"],
                sweep_res["pmtu"],
                audit_iran=audit_local,
                audit_node=audit_remote,
            )
            non_kernel_recs = {
                "nginx": (audit_local.get("nginx_recommendations") or []) + (audit_remote.get("nginx_recommendations") or []),
                "xray": (audit_local.get("xray_recommendations") or []) + (audit_remote.get("xray_recommendations") or []),
                "system": (audit_local.get("system_recommendations") or []) + (audit_remote.get("system_recommendations") or []),
            }
            benchmarks = {
                "baseline": _trim_trial_summary(sweep_res["baseline"]),
                "winner": _trim_trial_summary(sweep_res["winner"]),
                "top_candidates": [_trim_trial_summary(x) for x in sweep_res["top_candidates"][:5]],
                "carriers": sweep_res["carriers"],
            }
            profile = build_profile(
                meta={
                    "name": f"{self.tags.get('iran_dc', 'iran')}-to-{self.tags.get('node_dc', 'node')}",
                    "mode": self.mode,
                    "goal": self.goal,
                    "tags": self.tags,
                },
                environment={
                    "iran": {
                        "kernel": caps_local["kernel"],
                        "cpus": caps_local["cpus"],
                        "ram_mb": caps_local["ram_mb"],
                        "virt": caps_local["virt"],
                        "nic_driver": caps_local["nic_driver"],
                        "available_cc": caps_local["available_cc"],
                    },
                    "node": {
                        "kernel": caps_remote.get("kernel", ""),
                        "cpus": caps_remote.get("cpus", 1),
                        "ram_mb": caps_remote.get("ram_mb", 1024),
                        "virt": caps_remote.get("virt", "unknown"),
                        "nic_driver": caps_remote.get("nic_driver", "unknown"),
                        "available_cc": caps_remote.get("available_cc", []),
                    },
                    "pmtu": sweep_res["pmtu"],
                },
                diagnostics=diagnostics,
                benchmarks=benchmarks,
                iran_config=iran_cfg,
                node_config=node_cfg,
                non_kernel_recommendations=non_kernel_recs,
                strip_pii=True,
            )
            b64 = encode_profile_b64(profile)

            report = {
                "ok": True,
                "job_id": self.job_id,
                "elapsed_s": round(time.monotonic() - self._t0, 2),
                "profile": profile,
                "profile_b64": b64,
                "benchmarks": benchmarks,
                "diagnostics": diagnostics,
                "pmtu": sweep_res["pmtu"],
                "non_kernel_recommendations": non_kernel_recs,
            }
            os.makedirs(self.out_dir, exist_ok=True)
            _atomic_write_json(os.path.join(self.out_dir, "report.json"), report)
            _atomic_write_json(os.path.join(self.out_dir, "profile.json"), profile)
            with open(os.path.join(self.out_dir, "profile.b64"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(b64 + "\n")
            return report
        finally:
            if hb_ev is not None:
                hb_ev.set()
            if hb_thr is not None:
                hb_thr.join(timeout=1.5)
            self._teardown_session(client, local_snap)

    def _run_imported_trial(
        self,
        prof_id: str,
        prof_obj: dict,
        client: ControlClient,
        caps_local: dict,
        caps_remote: dict,
        local_snap: dict,
        tcp_port: int,
        udp_port: int,
        unloaded_p50: float,
        dur_s: float,
    ) -> dict:
        iran_cfg = clamp_config_for_ram(prof_obj["iran_config"], caps_local["ram_mb"])
        node_cfg = clamp_config_for_ram(prof_obj["node_config"], caps_remote.get("ram_mb", 1024))
        mss_ov = 0
        if self.mode == "brutal":
            apply_candidate(
                self.driver, iran_cfg, iface=caps_local["iface"], peer_ip=self.peer_host,
                session_id=self._session_id, ram_mb=caps_local["ram_mb"], ipv6_active=caps_local["ipv6_active"],
            )
            client.call("apply_cand", {"config": node_cfg, "iface": caps_remote.get("iface", ""), "session_id": self._session_id})
        elif iran_cfg.get("mtu"):
            mss_ov = max(536, int(iran_cfg["mtu"]) - 40)

        try:
            m = probe_trial(
                self.peer_host, tcp_port, udp_port,
                duration_s=dur_s, streams=4, mss_override=mss_ov,
                include_bidir=True, include_burst=True, unloaded_p50_ms=unloaded_p50,
            )
        finally:
            if self.mode == "brutal":
                restore_snapshot(self.driver, local_snap, session_id=self._session_id)
                client.call("revert", {"session_id": self._session_id})
        m["id"] = prof_id
        m["name"] = (prof_obj.get("meta") or {}).get("name") or prof_id
        return m

    def test_profile(self, profile_spec: str) -> dict:
        """A/B test one external/AI-generated profile live against Baseline."""
        prof = load_profile_any(profile_spec, verify_sha=False)
        client = ControlClient(self.peer_host, self.ctrl_port, self.token, timeout=15.0)
        local_snap = None
        hb_ev = None
        hb_thr = None
        dur_s = 0.14 if self.fast_test else 5.0
        try:
            client.connect()
            caps_local, caps_remote, tcp_port, udp_port, local_snap = self._setup_session(client)
            hb_ev, hb_thr = self._start_heartbeat(client)

            unloaded = probe_unloaded_rtt(self.peer_host, tcp_port, udp_port, samples=4 if self.fast_test else 15)
            unloaded_p50 = float(unloaded["tcp_rtt"]["p50"] or 1.0)

            base_m = probe_trial(
                self.peer_host, tcp_port, udp_port,
                duration_s=dur_s, streams=4, include_bidir=True, include_burst=True,
                unloaded_p50_ms=unloaded_p50,
            )
            base_m["id"] = "baseline"
            base_m["name"] = "baseline"

            cand_m = self._run_imported_trial(
                "candidate", prof, client, caps_local, caps_remote, local_snap,
                tcp_port, udp_port, unloaded_p50, dur_s,
            )
            scored = score_trials([base_m, cand_m], baseline_id="baseline")
            b_res, c_res = scored[0], scored[1]
            b_tp = raw_throughput(b_res) or 1.0
            c_tp = raw_throughput(c_res)
            return {
                "ok": True,
                "goal": self.goal,
                "mode": self.mode,
                "profile_name": (prof.get("meta") or {}).get("name"),
                "baseline": _trim_trial_summary(b_res),
                "candidate": _trim_trial_summary(c_res),
                "delta": {
                    "throughput_pct": round(((c_tp - b_tp) / b_tp) * 100.0, 2),
                    "loaded_rtt_p95_diff_ms": round(c_res["loaded_rtt_p95_ms"] - b_res["loaded_rtt_p95_ms"], 2),
                    "goal_score_diff": round(c_res["scores"][self.goal] - b_res["scores"][self.goal], 2),
                },
            }
        finally:
            if hb_ev is not None:
                hb_ev.set()
            if hb_thr is not None:
                hb_thr.join(timeout=1.5)
            self._teardown_session(client, local_snap)

    def compare_profiles(self, profile_specs: list[str]) -> dict:
        """Benchmark Baseline + multiple imported profiles back-to-back and rank them."""
        profiles = [load_profile_any(spec, verify_sha=False) for spec in profile_specs]
        client = ControlClient(self.peer_host, self.ctrl_port, self.token, timeout=15.0)
        local_snap = None
        hb_ev = None
        hb_thr = None
        dur_s = 0.14 if self.fast_test else 5.0
        try:
            client.connect()
            caps_local, caps_remote, tcp_port, udp_port, local_snap = self._setup_session(client)
            hb_ev, hb_thr = self._start_heartbeat(client)

            unloaded = probe_unloaded_rtt(self.peer_host, tcp_port, udp_port, samples=4 if self.fast_test else 15)
            unloaded_p50 = float(unloaded["tcp_rtt"]["p50"] or 1.0)

            base_m = probe_trial(
                self.peer_host, tcp_port, udp_port,
                duration_s=dur_s, streams=4, include_bidir=True, include_burst=True,
                unloaded_p50_ms=unloaded_p50,
            )
            base_m["id"] = "baseline"
            base_m["name"] = "baseline"
            trials = [base_m]

            for idx, prof in enumerate(profiles):
                trials.append(self._run_imported_trial(
                    f"profile_{idx + 1}", prof, client, caps_local, caps_remote, local_snap,
                    tcp_port, udp_port, unloaded_p50, dur_s,
                ))

            scored = score_trials(trials, baseline_id="baseline")
            ranked = sorted(scored, key=lambda x: x["scores"][self.goal], reverse=True)
            return {
                "ok": True,
                "goal": self.goal,
                "mode": self.mode,
                "leaderboard": [_trim_trial_summary(x) for x in ranked],
            }
        finally:
            if hb_ev is not None:
                hb_ev.set()
            if hb_thr is not None:
                hb_thr.join(timeout=1.5)
            self._teardown_session(client, local_snap)
