#!/usr/bin/env python3
"""Comprehensive tests for M4: tg_relay (real local HTTP/SOCKS5 proxies + SSH auto-relay + diagnose-relay),
monitor (HysteresisTracker, BotCommandRouter, config validation), live Hub /api/monitor/* HTTP + RBAC, and CLI.
"""

import contextlib
import base64
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
import select
import socket
import struct
import sys
import tempfile
import threading
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HUB_DIR = os.path.join(REPO_ROOT, "rathole-manager", "ratholehub")
if HUB_DIR not in sys.path:
    sys.path.insert(0, HUB_DIR)

import hubsec  # noqa: E402
import monitor  # noqa: E402
import tg_relay  # noqa: E402


def _load_hub():
    os.environ.setdefault("RATHOLEHUB_MOCK", "1")
    spec = importlib.util.spec_from_file_location("hub", os.path.join(HUB_DIR, "hub.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hub = _load_hub()


def _pump_bidirectional(a, b, initial_to_b=b""):
    try:
        if initial_to_b:
            b.sendall(initial_to_b)
        socks = [a, b]
        while socks:
            r, _, _ = select.select(socks, [], [], 2.0)
            if not r:
                continue
            for s in r:
                data = s.recv(4096)
                if not data:
                    return
                dst = b if s is a else a
                dst.sendall(data)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except Exception:
                pass


class _MockTelegramServer:
    def __init__(self):
        self.calls = []
        self.updates = []
        outer = self

        class TgHandler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, obj):
                raw = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                outer.calls.append(("GET", self.path, {}))
                if self.path.endswith("/getMe"):
                    return self._reply(200, {"ok": True, "result": {"id": 999, "username": "RatholeTestBot"}})
                return self._reply(404, {"ok": False, "error_code": 404, "description": "not found"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length", "0") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8")) if n > 0 else {}
                outer.calls.append(("POST", self.path, body))
                if self.path.endswith("/getUpdates"):
                    return self._reply(200, {"ok": True, "result": list(outer.updates)})
                if self.path.endswith("/sendMessage"):
                    return self._reply(200, {"ok": True, "result": {"message_id": len(outer.calls)}})
                if self.path.endswith("/answerCallbackQuery"):
                    return self._reply(200, {"ok": True, "result": True})
                return self._reply(404, {"ok": False, "error_code": 404, "description": "not found"})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), TgHandler)
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.th.join(timeout=2)


class _MockHttpConnectProxy:
    def __init__(self, auth_user=None, auth_pass=None, redirect_target=None):
        self.auth_user = auth_user
        self.auth_pass = auth_pass
        self.redirect_target = redirect_target
        self.connect_count = 0
        self._stop = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.sock.settimeout(0.5)
        self.port = self.sock.getsockname()[1]
        self.th = threading.Thread(target=self._accept_loop, daemon=True)
        self.th.start()

    def _handle_client(self, cli):
        try:
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 8192:
                chunk = cli.recv(1024)
                if not chunk:
                    cli.close()
                    return
                buf += chunk
            head, extra = buf.split(b"\r\n\r\n", 1)
            lines = head.decode("latin1").split("\r\n")
            req_line = lines[0].split()
            if len(req_line) < 2 or req_line[0].upper() != "CONNECT":
                cli.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                cli.close()
                return
            if self.auth_user and self.auth_pass:
                expected = "Basic " + base64.b64encode(f"{self.auth_user}:{self.auth_pass}".encode()).decode()
                hdr_auth = ""
                for ln in lines[1:]:
                    if ln.lower().startswith("proxy-authorization:"):
                        hdr_auth = ln.split(":", 1)[1].strip()
                if hdr_auth != expected:
                    cli.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
                    cli.close()
                    return
            host, port_s = req_line[1].rsplit(":", 1)
            dst = self.redirect_target if self.redirect_target else (host, int(port_s))
            self.connect_count += 1
            up = socket.create_connection(dst, timeout=3.0)
            cli.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            _pump_bidirectional(cli, up, initial_to_b=extra)
        except Exception:
            try:
                cli.close()
            except Exception:
                pass

    def _accept_loop(self):
        while not self._stop:
            try:
                cli, _ = self.sock.accept()
                threading.Thread(target=self._handle_client, args=(cli,), daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                break

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except Exception:
            pass
        self.th.join(timeout=2)


class _MockSocks5Proxy:
    def __init__(self, auth_user=None, auth_pass=None, redirect_target=None):
        self.auth_user = auth_user
        self.auth_pass = auth_pass
        self.redirect_target = redirect_target
        self.connect_count = 0
        self._stop = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.sock.settimeout(0.5)
        self.port = self.sock.getsockname()[1]
        self.th = threading.Thread(target=self._accept_loop, daemon=True)
        self.th.start()

    def _recv_n(self, s, n):
        buf = bytearray()
        while len(buf) < n:
            c = s.recv(n - len(buf))
            if not c:
                raise ConnectionError("eof")
            buf.extend(c)
        return bytes(buf)

    def _handle_client(self, cli):
        try:
            hdr = self._recv_n(cli, 2)
            ver, nmethods = hdr[0], hdr[1]
            if ver != 5:
                cli.close()
                return
            methods = self._recv_n(cli, nmethods)
            if self.auth_user and self.auth_pass:
                if 2 not in methods:
                    cli.sendall(b"\x05\xff")
                    cli.close()
                    return
                cli.sendall(b"\x05\x02")
                sub = self._recv_n(cli, 2)
                ulen = sub[1]
                u = self._recv_n(cli, ulen).decode()
                plen = self._recv_n(cli, 1)[0]
                p = self._recv_n(cli, plen).decode()
                if u != self.auth_user or p != self.auth_pass:
                    cli.sendall(b"\x01\x01")
                    cli.close()
                    return
                cli.sendall(b"\x01\x00")
            else:
                cli.sendall(b"\x05\x00")

            req = self._recv_n(cli, 4)
            atyp = req[3]
            if atyp == 1:
                host = socket.inet_ntoa(self._recv_n(cli, 4))
            elif atyp == 3:
                ln = self._recv_n(cli, 1)[0]
                host = self._recv_n(cli, ln).decode()
            elif atyp == 4:
                host = socket.inet_ntop(socket.AF_INET6, self._recv_n(cli, 16))
            else:
                cli.close()
                return
            port = struct.unpack(">H", self._recv_n(cli, 2))[0]
            dst = self.redirect_target if self.redirect_target else (host, port)
            self.connect_count += 1
            up = socket.create_connection(dst, timeout=3.0)
            cli.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            _pump_bidirectional(cli, up)
        except Exception:
            try:
                cli.close()
            except Exception:
                pass

    def _accept_loop(self):
        while not self._stop:
            try:
                cli, _ = self.sock.accept()
                threading.Thread(target=self._handle_client, args=(cli,), daemon=True).start()
            except socket.timeout:
                continue
            except OSError:
                break

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except Exception:
            pass
        self.th.join(timeout=2)


class _ClosedPort:
    @staticmethod
    def get():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
        s.close()
        return p


class TestM4TgRelay(unittest.TestCase):
    def setUp(self):
        self.tg = _MockTelegramServer()
        self.token = "123456789:ABCDEF_super_secret_bot_token_value"

    def tearDown(self):
        self.tg.close()

    def test_redaction_and_proxy_validation(self):
        self.assertTrue(tg_relay.valid_proxy_url(""))
        self.assertTrue(tg_relay.valid_proxy_url("socks5h://user:pass@127.0.0.1:1080"))
        self.assertTrue(tg_relay.valid_proxy_url("https://proxy.example.com:8443"))
        self.assertFalse(tg_relay.valid_proxy_url("ftp://127.0.0.1:21"))
        self.assertFalse(tg_relay.valid_proxy_url("http://127.0.0.1:99999"))
        self.assertFalse(tg_relay.valid_proxy_url("socks5://bad host:1080"))

        raw = f"POST https://api.telegram.org/bot{self.token}/getMe via http://alice:s3cr3t@1.2.3.4:8080 failed"
        clean = tg_relay.redact_secrets(raw, [self.token, "http://alice:s3cr3t@1.2.3.4:8080"])
        self.assertNotIn(self.token, clean)
        self.assertNotIn("s3cr3t", clean)
        self.assertIn("bot***", clean)
        self.assertIn("http://***@1.2.3.4:8080", clean)

    def test_direct_http_connect_and_socks5_with_auth(self):
        http_px = _MockHttpConnectProxy(auth_user="u1", auth_pass="p1")
        socks_px = _MockSocks5Proxy(auth_user="su", auth_pass="sp")
        socks_noauth = _MockSocks5Proxy()
        try:
            url = f"http://127.0.0.1:{self.tg.port}/bot{self.token}/getMe"
            st1, d1 = tg_relay.http_json_request(url, proxy_url="", timeout=5)
            self.assertEqual(st1, 200)
            self.assertTrue(d1["ok"])

            st2, d2 = tg_relay.http_json_request(
                url, proxy_url=f"http://u1:p1@127.0.0.1:{http_px.port}", timeout=5
            )
            self.assertEqual(st2, 200)
            self.assertTrue(d2["ok"])
            self.assertEqual(http_px.connect_count, 1)

            st3, d3 = tg_relay.http_json_request(
                url, proxy_url=f"socks5://su:sp@127.0.0.1:{socks_px.port}", timeout=5
            )
            self.assertEqual(st3, 200)
            self.assertTrue(d3["ok"])
            self.assertEqual(socks_px.connect_count, 1)

            st4, d4 = tg_relay.http_json_request(
                url, proxy_url=f"socks5h://127.0.0.1:{socks_noauth.port}", timeout=5
            )
            self.assertEqual(st4, 200)
            self.assertTrue(d4["ok"])
            self.assertEqual(socks_noauth.connect_count, 1)
        finally:
            http_px.close()
            socks_px.close()
            socks_noauth.close()

    def test_auto_relay_ssh_failover_diagnose_and_chunking(self):
        dead_port = _ClosedPort.get()
        socks_px = _MockSocks5Proxy(redirect_target=("127.0.0.1", self.tg.port))
        tunnels = []

        class FakeTunnel:
            def __init__(self, server, ssh_key_path="", ssh_opts=None):
                self.name = server["name"]
                self.closed = False
                if self.name == "node1":
                    raise RuntimeError(f"ssh timeout dialing {server['host']} bot{server.get('leak', '')}")
                self.proxy_url = f"socks5h://127.0.0.1:{socks_px.port}"
                tunnels.append(self)

            def is_alive(self):
                return not self.closed

            def close(self):
                self.closed = True

        inv = [
            {"name": "rp01", "role": "iran", "host": "5.202.4.40"},
            {"name": "node1", "role": "node", "host": "198.51.100.1"},
            {"name": "node2", "role": "node", "host": "198.51.100.2"},
        ]

        mgr = tg_relay.TelegramRelayManager(
            relay_mode="auto",
            proxy_url="",
            inventory_fn=lambda: inv,
            api_base=f"http://127.0.0.1:{dead_port}",
            timeout=3,
            tunnel_factory=FakeTunnel,
        )
        try:
            cli = tg_relay.TelegramClient(self.token, mgr)
            me = cli.get_me()
            self.assertEqual(me["username"], "RatholeTestBot")
            rt = mgr.active_route()
            self.assertEqual(rt["mode"], "ssh_auto")
            self.assertEqual(rt["node"], "node2")
            self.assertEqual(len(tunnels), 1)
            self.assertFalse(tunnels[0].closed)

            # Chunking a 9,200-char payload splits <= 4000 chars and attaches reply_markup only on final chunk
            long_msg = "\n".join(f"line-{i:04d} " + ("X" * 40) for i in range(190))
            self.assertGreater(len(long_msg), 9000)
            self.tg.calls.clear()
            res_list = cli.send_message(12345, long_msg, reply_markup={"inline_keyboard": [[{"text": "OK", "callback_data": "x"}]]})
            self.assertGreaterEqual(len(res_list), 3)
            send_bodies = [b for (_, path, b) in self.tg.calls if path.endswith("/sendMessage")]
            self.assertEqual(len(send_bodies), len(res_list))
            for idx, b in enumerate(send_bodies):
                self.assertLessEqual(len(b["text"]), 4000)
                if idx < len(send_bodies) - 1:
                    self.assertNotIn("reply_markup", b)
                else:
                    self.assertIn("reply_markup", b)

            # diagnose_relay probes direct (fails on dead_port) + node1 (fails) + node2 (succeeds) and closes tunnel
            diag = tg_relay.diagnose_relay(
                self.token,
                inv,
                proxy_url="",
                api_base=f"http://127.0.0.1:{dead_port}",
                timeout=3,
                tunnel_factory=FakeTunnel,
            )
            self.assertFalse(diag["direct"]["ok"])
            self.assertEqual(diag["recommended_mode"], "ssh_auto")
            self.assertEqual(diag["best_ssh_node"], "node2")
            self.assertEqual(len(diag["ssh_nodes"]), 2)
            self.assertTrue(tunnels[-1].closed)
            self.assertNotIn(self.token, json.dumps(diag))
        finally:
            mgr.close()
            socks_px.close()


class TestM4HysteresisTracker(unittest.TestCase):
    def test_thresholds_persistence_and_mute(self):
        with tempfile.TemporaryDirectory() as d:
            st_path = os.path.join(d, "state.json")
            tr = monitor.HysteresisTracker(fail_threshold=3, recover_threshold=2, cooldown_sec=300, state_path=st_path)
            bad_obs = {"server:rp01": {"ok": False, "severity": "error", "title": "rp01 down", "detail": "timeout"}}
            ok_obs = {"server:rp01": {"ok": True}}

            self.assertEqual(tr.evaluate(bad_obs, now=100), [])
            self.assertEqual(tr.evaluate(bad_obs, now=160), [])
            ev3 = tr.evaluate(bad_obs, now=220)
            self.assertEqual(len(ev3), 1)
            self.assertEqual(ev3[0]["kind"], "firing")
            # Subsequent failures while firing do not spam
            self.assertEqual(tr.evaluate(bad_obs, now=280), [])
            self.assertEqual(tr.evaluate(bad_obs, now=340), [])

            # Reload from disk -> remembers active alert and does not re-fire
            tr2 = monitor.HysteresisTracker(fail_threshold=3, recover_threshold=2, cooldown_sec=300, state_path=st_path)
            self.assertEqual(len(tr2.active_alerts()), 1)
            self.assertEqual(tr2.evaluate(bad_obs, now=400), [])

            # Recover threshold=2 -> no resolve on 1st ok, resolves on 2nd ok
            self.assertEqual(tr2.evaluate(ok_obs, now=460), [])
            ev_rec = tr2.evaluate(ok_obs, now=520)
            self.assertEqual(len(ev_rec), 1)
            self.assertEqual(ev_rec[0]["kind"], "resolved")
            self.assertEqual(tr2.active_alerts(), [])

            # Mute suppresses notifications while advancing state accurately
            tr2.set_mute(10, now=1000)
            self.assertTrue(tr2.is_muted(now=1001))
            self.assertEqual(tr2.evaluate(bad_obs, now=1010), [])
            self.assertEqual(tr2.evaluate(bad_obs, now=1020), [])
            self.assertEqual(tr2.evaluate(bad_obs, now=1030), [])
            self.assertEqual(len(tr2.active_alerts()), 1)
            self.assertGreaterEqual(tr2.muted_count, 1)
            tr2.clear_mute()
            self.assertFalse(tr2.is_muted(now=1040))


class TestM4BotCommandRouter(unittest.TestCase):
    def _fake_hub(self):
        class FakeHub:
            def __init__(self):
                self.actions = []

            def get_servers(self):
                return [
                    {"name": "rp01", "role": "iran", "host": "5.202.4.40"},
                    {"name": "trk01", "role": "node", "host": "198.51.100.10"},
                ]

            def get_fleet_drift(self):
                return {
                    "servers_checked": 2,
                    "servers_unreachable": 0,
                    "summary": {"total": 1, "error": 1, "warning": 0, "info": 0, "clean": False},
                    "items": [{"severity": "error", "server": "rp01", "service": "x", "kind": "k", "message": "bad <script>alert(1)</script>"}],
                }

            def link_test(self, srv, node=None, count=3):
                self.actions.append(("link_test", srv, node, count))
                return {"ok": True, "verdict": "healthy", "diagnosis": "OK", "iran_to_node": {"rtt_ms": {"avg": 25.4}, "loss_pct": 0.0}}

            def run_action(self, srv, action, args=None):
                self.actions.append((action, srv))
                return {"rc": 0, "out": f"{action} ok on <{srv}>", "err": ""}

        class FakeRelay:
            def active_route(self):
                return {"mode": "ssh_auto", "node": "trk01", "proxy": "socks5h://127.0.0.1:41234"}

        return FakeHub(), FakeRelay()

    def test_authorization_commands_callbacks_and_escaping(self):
        fh, fr = self._fake_hub()
        tr = monitor.HysteresisTracker()

        # Fail-closed when allowed_chat_ids empty
        closed_router = monitor.BotCommandRouter(fh, tr, fr, [])
        self.assertEqual(closed_router.handle_update({"message": {"chat": {"id": 1001}, "text": "/status"}}), [])

        router = monitor.BotCommandRouter(fh, tr, fr, [1001], allow_remote_actions=True)
        # Unauthorized chat ignored
        self.assertEqual(router.handle_update({"message": {"chat": {"id": 9999}, "text": "/status"}}), [])

        for cmd in ("/start", "/help", "/status", "/drift", "/alerts", "/relay", "/test rp01 trk01", "/doctor rp01", "/restart rp01", "/mute 15", "/unmute"):
            acts = router.handle_update({"message": {"chat": {"id": 1001}, "text": cmd}})
            self.assertEqual(len(acts), 1, cmd)
            self.assertEqual(acts[0]["chat_id"], 1001)

        # Injection rejection
        fh.actions.clear()
        acts_bad = router.handle_update({"message": {"chat": {"id": 1001}, "text": "/restart rp01;id"}})
        self.assertEqual(fh.actions, [])
        self.assertIn("Usage", acts_bad[0]["text"])

        # Disabled remote actions enforcement
        ro_router = monitor.BotCommandRouter(fh, tr, fr, [1001], allow_remote_actions=False)
        acts_dis = ro_router.handle_update({"message": {"chat": {"id": 1001}, "text": "/restart rp01"}})
        self.assertEqual(fh.actions, [])
        self.assertIn("disabled", acts_dis[0]["text"])

        # Escaping & callback query
        drift_acts = router.handle_update({"callback_query": {"id": "cbq_1", "data": "cb:drift", "message": {"chat": {"id": 1001}}}})
        self.assertEqual(drift_acts[0]["callback_query_id"], "cbq_1")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", drift_acts[0]["text"])
        self.assertNotIn("<script>", drift_acts[0]["text"])


class TestM4MonitorHubHttpAndCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = (
            hub.CONF_PATH,
            hub.INV_PATH,
            hub.MOCK,
            hub.AUDIT_PATH,
            hub.MON_CONF_PATH,
            dict(hub._OVERVIEW_CACHE),
            hub._LAST_DRIFT_SUMMARY,
            hub._LOGIN_FAILS_TOTAL,
            dict(hub._HTTP_REQS),
            dict(hub._LOGIN_FAILS),
            os.environ.get("RATHOLEMON_CONF"),
            os.environ.get("RATHOLEMON_STATE"),
            os.environ.get("RATHOLEHUB_CONF"),
            os.environ.get("RATHOLEHUB_INV"),
        )
        self.conf = os.path.join(self.tmp.name, "conf.json")
        self.inv = os.path.join(self.tmp.name, "inv.json")
        self.audit = os.path.join(self.tmp.name, "audit.log")
        self.mon_conf = os.path.join(self.tmp.name, "monitor.json")
        self.mon_state = os.path.join(self.tmp.name, "monitor-state.json")
        self.tok = "test_m4_admin_token_abcdef123456"
        with open(self.conf, "w", encoding="utf-8") as f:
            json.dump({
                "api_token": self.tok,
                "admin_password_sha256": hub._hash_password("pass1234"),
                "listen_host": "127.0.0.1",
                "listen_port": 0,
            }, f)
        with open(self.inv, "w", encoding="utf-8") as f:
            json.dump([
                {"name": "rp01", "role": "iran", "host": "5.202.4.40"},
                {"name": "trk01", "role": "node", "host": "198.51.100.10"},
            ], f)

        hub.CONF_PATH = self.conf
        hub.INV_PATH = self.inv
        hub.MOCK = True
        hub.AUDIT_PATH = self.audit
        hub.MON_CONF_PATH = self.mon_conf
        hub._OVERVIEW_CACHE.clear()
        hub._LAST_DRIFT_SUMMARY = None
        hub._LOGIN_FAILS_TOTAL = 0
        hub._HTTP_REQS.clear()
        hub._HTTP_REQS.update({"GET": 0, "POST": 0, "PUT": 0, "DELETE": 0})
        hub._LOGIN_FAILS.clear()
        os.environ["RATHOLEMON_CONF"] = self.mon_conf
        os.environ["RATHOLEMON_STATE"] = self.mon_state
        os.environ["RATHOLEHUB_CONF"] = self.conf
        os.environ["RATHOLEHUB_INV"] = self.inv

        self.srv = hub.ThreadingHTTPServer(("127.0.0.1", 0), hub.Handler)
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.th.join(timeout=2)
        (
            hub.CONF_PATH,
            hub.INV_PATH,
            hub.MOCK,
            hub.AUDIT_PATH,
            hub.MON_CONF_PATH,
            orig_cache,
            orig_drift,
            orig_fails_tot,
            orig_reqs,
            orig_login_fails,
            env_mc,
            env_ms,
            env_hc,
            env_hi,
        ) = self.orig
        hub._OVERVIEW_CACHE.clear()
        hub._OVERVIEW_CACHE.update(orig_cache)
        hub._LAST_DRIFT_SUMMARY = orig_drift
        hub._LOGIN_FAILS_TOTAL = orig_fails_tot
        hub._HTTP_REQS.clear()
        hub._HTTP_REQS.update(orig_reqs)
        hub._LOGIN_FAILS.clear()
        hub._LOGIN_FAILS.update(orig_login_fails)
        for k, v in (
            ("RATHOLEMON_CONF", env_mc),
            ("RATHOLEMON_STATE", env_ms),
            ("RATHOLEHUB_CONF", env_hc),
            ("RATHOLEHUB_INV", env_hi),
        ):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def _req(self, method, path, body=None, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            hdrs = {"Content-Type": "application/json"}
            if token is not None:
                hdrs["Authorization"] = f"Bearer {token}"
            raw = json.dumps(body).encode("utf-8") if body is not None else None
            conn.request(method, path, body=raw, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data) if data else {}
        finally:
            conn.close()

    def test_hub_monitor_rbac_config_diagnose_test_and_cli_once(self):
        ro_tok = self._req("POST", "/api/tokens", {"name": "ro", "scope": "read"}, token=self.tok)[1]["token"]
        op_tok = self._req("POST", "/api/tokens", {"name": "op", "scope": "operate"}, token=self.tok)[1]["token"]

        for tok in (ro_tok, op_tok):
            self.assertEqual(self._req("GET", "/api/monitor/config", token=tok)[0], 403)
            self.assertEqual(self._req("POST", "/api/monitor/config", {"enabled": True}, token=tok)[0], 403)
            self.assertEqual(self._req("POST", "/api/monitor/diagnose-relay", {}, token=tok)[0], 403)
            self.assertEqual(self._req("POST", "/api/monitor/test", {}, token=tok)[0], 403)

        # Bad config rejected
        self.assertEqual(self._req("POST", "/api/monitor/config", {"relay_mode": "invalid"}, token=self.tok)[0], 400)
        self.assertEqual(self._req("POST", "/api/monitor/config", {"proxy": "ftp://bad:21"}, token=self.tok)[0], 400)
        self.assertEqual(self._req("POST", "/api/monitor/config", {"poll_interval_sec": 5}, token=self.tok)[0], 400)

        # Unconfigured test rejected with 400
        self.assertEqual(self._req("POST", "/api/monitor/test", {}, token=self.tok)[0], 400)

        # Valid save -> secret stored cleanly, preserved on omit, redacted on GET & audit
        secret_bt = "987654321:M4_VerySecretToken_XYZ"
        st_sv, sv = self._req("POST", "/api/monitor/config", {
            "enabled": True,
            "bot_token": secret_bt,
            "allowed_chat_ids": [111, -100222],
            "relay_mode": "ssh_auto",
            "hub_url": f"http://127.0.0.1:{self.port}",
        }, token=self.tok)
        self.assertEqual(st_sv, 200)
        self.assertTrue(sv["config"]["bot_token_set"])
        self.assertNotIn("bot_token", sv["config"])

        # Subsequent save without bot_token keeps saved secret
        self.assertEqual(self._req("POST", "/api/monitor/config", {"poll_interval_sec": 45}, token=self.tok)[0], 200)
        st_gt, gt = self._req("GET", "/api/monitor/config", token=self.tok)
        self.assertEqual(st_gt, 200)
        self.assertTrue(gt["bot_token_set"])
        self.assertEqual(gt["poll_interval_sec"], 45)
        self.assertNotIn(secret_bt, json.dumps(gt))
        if os.path.exists(self.audit):
            with open(self.audit, "r", encoding="utf-8") as f:
                self.assertNotIn(secret_bt, f.read())

        st_diag, diag = self._req("POST", "/api/monitor/diagnose-relay", {}, token=self.tok)
        self.assertEqual(st_diag, 200)
        self.assertEqual(diag["recommended_mode"], "ssh_auto")
        self.assertEqual(diag["best_ssh_node"], "trk01")

        st_tst, tst = self._req("POST", "/api/monitor/test", {}, token=self.tok)
        self.assertEqual(st_tst, 200)
        self.assertTrue(tst["ok"])
        self.assertEqual(tst["sent"], 2)

        # CLI `monitor.py once --json` against live mock Hub HTTP server
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = monitor.main(["--conf", self.mon_conf, "once", "--json"])
        self.assertEqual(rc, 0)
        cli_out = json.loads(buf.getvalue())
        self.assertTrue(cli_out["ok"])
        self.assertGreaterEqual(cli_out["observations_count"], 3)

    def test_hub_auto_installs_and_toggles_monitor_unit(self):
        # Verify non-mock _monitor_config_save installs & enables ratholemonitor.service directly from Hub
        with tempfile.TemporaryDirectory() as td:
            unit_p = os.path.join(td, "ratholemonitor.service")
            inst_p = os.path.join(td, "install-monitor.sh")
            with open(inst_p, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\nexit 0\n")
            seen = []

            def fake_run(cmd, **kw):
                seen.append(list(cmd))
                if cmd[:2] == ["bash", inst_p]:
                    with open(unit_p, "w", encoding="utf-8") as uf:
                        uf.write("[Unit]\nDescription=stub\n")
                class _R:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return _R()

            orig_mock = hub.MOCK
            orig_unit = hub.MON_UNIT_PATH
            orig_inst = hub.MON_INSTALLER_PATH
            orig_run = hub.subprocess.run
            try:
                hub.MOCK = False
                hub.MON_UNIT_PATH = unit_p
                hub.MON_INSTALLER_PATH = inst_p
                hub.subprocess.run = fake_run

                st, res = self._req("POST", "/api/monitor/config", {
                    "enabled": True,
                    "bot_token": "987654321:M4_AutoInstallToken_XYZ",
                    "allowed_chat_ids": [111],
                    "relay_mode": "auto",
                }, token=self.tok)
                self.assertEqual(st, 200)
                self.assertNotIn("service_error", res)
                self.assertTrue(res["config"]["service_installed"])
                self.assertIn(["bash", inst_p, "--enable"], seen)
                self.assertIn(["systemctl", "enable", "--now", "ratholemonitor"], seen)
                self.assertIn(["systemctl", "restart", "ratholemonitor"], seen)

                seen.clear()
                st2, res2 = self._req("POST", "/api/monitor/config", {"enabled": False}, token=self.tok)
                self.assertEqual(st2, 200)
                self.assertIn(["systemctl", "disable", "--now", "ratholemonitor"], seen)
            finally:
                hub.MOCK = orig_mock
                hub.MON_UNIT_PATH = orig_unit
                hub.MON_INSTALLER_PATH = orig_inst
                hub.subprocess.run = orig_run


if __name__ == "__main__":
    unittest.main()
