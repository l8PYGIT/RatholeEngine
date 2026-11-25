"""Unit and live E2E integration tests for pure stdlib RFC 6455 WS and Reverse Agent."""

from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "rathole-manager"))
sys.path.insert(0, os.path.join(ROOT, "rathole-manager", "ratholehub"))

import hub
import ratholeagent
import wsutil


class _MiniWSServer:
    """Minimal RFC 6455 loopback server for unit-testing wsutil in isolation."""

    def __init__(self, on_conn):
        self.on_conn = on_conn

        class _H(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self_h):
                try:
                    ws = wsutil.ws_accept_handshake(self_h)
                except wsutil.WSError as exc:
                    self_h.send_response(400)
                    self_h.end_headers()
                    self_h.wfile.write(str(exc).encode())
                    return
                on_conn(ws, self_h.headers, self_h.path)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.th.join(timeout=3)


class TestWSUtil(unittest.TestCase):
    def test_handshake_masking_ping_pong_and_fragmentation(self):
        received = []

        def on_conn(ws, hdrs, path):
            received.append((path, dict(hdrs)))
            try:
                ws.send_ping(b"srv-hb")
                msg1 = ws.recv_message()
                msg2 = ws.recv_message()
                ws.send_json({"echo1": msg1, "echo2": msg2})
                ws.recv_message()  # Wait for close
            finally:
                ws.close()

        mini = _MiniWSServer(on_conn)
        self.addCleanup(mini.close)

        c = wsutil.ws_connect(
            f"ws://127.0.0.1:{mini.port}/hub/ws/agent?v=1",
            headers={"X-Agent-Name": "n1", "Authorization": "Bearer tok"},
            timeout=5.0,
        )
        try:
            self.assertTrue(c.mask_outgoing)
            c.send_text("hello-ws")
            # Send a 2-fragment masked TEXT message directly using raw frame headers
            p1, p2 = b"frag-", b"complete"
            m1, m2 = os.urandom(4), os.urandom(4)
            f1 = bytes([wsutil.OP_TEXT, 0x80 | len(p1)]) + m1 + wsutil._xor_mask(p1, m1)
            f2 = bytes([0x80 | wsutil.OP_CONT, 0x80 | len(p2)]) + m2 + wsutil._xor_mask(p2, m2)
            with c.write_lock:
                c.sock.sendall(f1 + f2)
            reply = json.loads(c.recv_message())
            self.assertEqual(reply, {"echo1": "hello-ws", "echo2": "frag-complete"})
            self.assertEqual(received[0][0], "/hub/ws/agent?v=1")
            self.assertEqual(received[0][1].get("X-Agent-Name"), "n1")
            c.send_close(1000)
        finally:
            c.close()

    def test_rejects_oversized_frame_and_bad_accept(self):
        # 1) Reject frame length > MAX_FRAME_BYTES on read
        s_a, s_b = socket.socketpair()
        try:
            ws_a = wsutil.WSConn(s_a, mask_outgoing=False)
            huge_hdr = struct.pack("!BBQ", 0x81, 127, wsutil.MAX_FRAME_BYTES + 1)
            s_b.sendall(huge_hdr)
            with self.assertRaises(wsutil.WSError):
                ws_a.recv_message()
        finally:
            s_a.close()
            s_b.close()

        # 2) Reject forged Sec-WebSocket-Accept from server
        srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv_sock.bind(("127.0.0.1", 0))
        srv_sock.listen(1)
        port = srv_sock.getsockname()[1]

        def bad_srv():
            conn, _ = srv_sock.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(
                    b"HTTP/1.1 101 Switching Protocols\r\n"
                    b"Upgrade: websocket\r\nConnection: Upgrade\r\n"
                    b"Sec-WebSocket-Accept: INVALIDACCEPT==\r\n\r\n"
                )

        th = threading.Thread(target=bad_srv, daemon=True)
        th.start()
        try:
            with self.assertRaises(wsutil.WSError):
                wsutil.ws_connect(f"ws://127.0.0.1:{port}/ws/agent", timeout=3.0)
        finally:
            srv_sock.close()
            th.join(timeout=2)

    def test_http_connect_proxy_tunnel(self):
        seen_connect = []

        def on_ws(ws, _hdrs, _path):
            try:
                m = ws.recv_message()
                ws.send_text(f"proxied:{m}")
            finally:
                ws.close()

        mini = _MiniWSServer(on_ws)
        self.addCleanup(mini.close)

        px_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        px_sock.bind(("127.0.0.1", 0))
        px_sock.listen(2)
        px_port = px_sock.getsockname()[1]
        stop_ev = threading.Event()

        def relay(src, dst):
            try:
                while True:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        def px_loop():
            conn, _ = px_sock.accept()
            head = b""
            while b"\r\n\r\n" not in head:
                head += conn.recv(4096)
            seen_connect.append(head.decode("latin-1"))
            upstream = socket.create_connection(("127.0.0.1", mini.port), timeout=5)
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            t1 = threading.Thread(target=relay, args=(conn, upstream), daemon=True)
            t2 = threading.Thread(target=relay, args=(upstream, conn), daemon=True)
            t1.start(); t2.start()
            while not stop_ev.is_set() and (t1.is_alive() or t2.is_alive()):
                time.sleep(0.05)
            conn.close()
            upstream.close()

        pt = threading.Thread(target=px_loop, daemon=True)
        pt.start()
        self.addCleanup(lambda: (stop_ev.set(), px_sock.close(), pt.join(timeout=2)))

        c = wsutil.ws_connect(
            f"ws://127.0.0.1:{mini.port}/ws/agent",
            proxy=f"http://user1:pass1@127.0.0.1:{px_port}",
            timeout=5.0,
        )
        try:
            c.send_text("ok")
            self.assertEqual(c.recv_message(), "proxied:ok")
            self.assertIn("CONNECT 127.0.0.1:", seen_connect[0])
            self.assertIn("Proxy-Authorization: Basic ", seen_connect[0])
        finally:
            c.close()


class TestHubReverseAgentE2E(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.orig = {
            "CONF": hub.CONF_PATH,
            "INV": hub.INV_PATH,
            "AUDIT": hub.AUDIT_PATH,
            "PROF": hub.TUNER_PROFILES_PATH,
            "JOBS": hub.TUNER_JOBS_PATH,
            "MOCK": hub.MOCK,
            "LOADED": hub._tuner_jobs_loaded_path,
        }
        hub.CONF_PATH = os.path.join(self.td.name, "conf.json")
        hub.INV_PATH = os.path.join(self.td.name, "inv.json")
        hub.AUDIT_PATH = os.path.join(self.td.name, "audit.log")
        hub.TUNER_PROFILES_PATH = os.path.join(self.td.name, "profiles.json")
        hub.TUNER_JOBS_PATH = os.path.join(self.td.name, "jobs.json")
        hub._tuner_jobs_loaded_path = None
        hub._TUNER_JOBS.clear()
        hub._LOGIN_FAILS.clear()
        hub.MOCK = False

        self.admin_token = "adm-rev-token-0123456789abcdef"
        hub.save_config({
            "api_token": self.admin_token,
            "admin_password_sha256": hub._hash_password("strongpass"),
            "listen_host": "127.0.0.1",
            "listen_port": 0,
        })
        hub.set_inventory([])
        self.clients = []
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), hub.Handler)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()

    def tearDown(self):
        for cl in self.clients:
            cl.stop()
        with hub._reverse_lock:
            names = list(hub._REVERSE_AGENTS.keys())
        for nm in names:
            hub._close_reverse_session(nm)
        self.srv.shutdown()
        self.srv.server_close()
        self.th.join(timeout=4)
        hub._LOGIN_FAILS.clear()
        hub.CONF_PATH = self.orig["CONF"]
        hub.INV_PATH = self.orig["INV"]
        hub.AUDIT_PATH = self.orig["AUDIT"]
        hub.TUNER_PROFILES_PATH = self.orig["PROF"]
        hub.TUNER_JOBS_PATH = self.orig["JOBS"]
        hub._tuner_jobs_loaded_path = self.orig["LOADED"]
        hub.MOCK = self.orig["MOCK"]
        hub._TUNER_JOBS.clear()

    def _api(self, method, path, body=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        hdrs = {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}
        conn.request(method, path, body=(json.dumps(body) if body is not None else None), headers=hdrs)
        r = conn.getresponse()
        raw = r.read().decode("utf-8", errors="replace")
        conn.close()
        return r.status, json.loads(raw) if raw else {}

    def _wait_session(self, name, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with hub._reverse_lock:
                sess = hub._REVERSE_AGENTS.get(name)
                if sess and not sess.closed.is_set() and sess.public_ip:
                    return sess
            time.sleep(0.03)
        self.fail(f"Reverse agent session '{name}' did not finish hello within {timeout}s")

    def test_auth_rejection_and_rate_limit(self):
        st, add_res = self._api("POST", "/api/servers", {"name": "rev1", "role": "node", "transport": "reverse_ws"})
        self.assertEqual(st, 200, add_res)
        self.assertTrue(len(add_res.get("api_token", "")) >= 32)
        st2, _ = self._api("POST", "/api/servers", {"name": "ssh1", "role": "node", "transport": "ssh", "host": "192.0.2.10"})
        self.assertEqual(st2, 200)

        # GET /api/servers never leaks api_token
        _, lst = self._api("GET", "/api/servers")
        r1 = next(x for x in lst if x["name"] == "rev1")
        self.assertNotIn("api_token", r1)
        self.assertTrue(r1["api_token_set"])
        self.assertFalse(r1["reverse_connected"])

        import http.client
        for headers, expected_codes in [
            ({}, (401,)),
            ({"X-Agent-Name": "rev1", "Authorization": "Bearer wrong-token"}, (403,)),
            ({"X-Agent-Name": "ssh1", "Authorization": "Bearer some-token"}, (403,)),
        ]:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            conn.request("GET", "/hub/ws/agent", headers=headers)
            resp = conn.getresponse()
            resp.read()
            conn.close()
            self.assertIn(resp.status, expected_codes)

        # Trigger 429 rate-limit after remaining failures
        got_429 = False
        for _ in range(5):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            conn.request("GET", "/ws/agent", headers={"X-Agent-Name": "rev1", "Authorization": "Bearer wrong"})
            resp = conn.getresponse()
            resp.read()
            conn.close()
            if resp.status == 429:
                got_429 = True
                break
        self.assertTrue(got_429)

    def test_end_to_end_multiplexed_exec_reconnect_and_cleanup(self):
        _, add_res = self._api("POST", "/api/servers", {"name": "rev-eu", "role": "node", "transport": "reverse_ws"})
        tok = add_res["api_token"]
        hub._LOGIN_FAILS.clear()

        c1 = ratholeagent.ReverseAgentClient(
            f"ws://127.0.0.1:{self.port}/hub/ws/agent",
            name="rev-eu",
            token=tok,
            role="node",
            ping_interval=10,
            allow_test_python=True,
            public_ip="198.51.100.77",
        )
        self.clients.append(c1)
        t1 = threading.Thread(target=c1.run_forever, daemon=True)
        t1.start()

        sess1 = self._wait_session("rev-eu")
        srv_rec = hub.load_json(hub.INV_PATH, [])[0]

        # Node public IP resolution + public view fields
        self.assertEqual(hub.node_public_host(srv_rec), "198.51.100.77")
        _, lst = self._api("GET", "/api/servers")
        pub = next(x for x in lst if x["name"] == "rev-eu")
        self.assertTrue(pub["reverse_connected"])
        self.assertEqual(pub["reverse_public_ip"], "198.51.100.77")
        self.assertEqual(pub["reverse_version"], ratholeagent.AGENT_VERSION)

        # Concurrent multiplexed commands (1 slow + 3 fast)
        cmds = [
            [sys.executable, "-c", "import time; time.sleep(0.35); print('slow-done')"],
            [sys.executable, "-c", "print('fast-1')"],
            [sys.executable, "-c", "print('fast-2')"],
            [sys.executable, "-c", "import sys; print('err-line', file=sys.stderr); sys.exit(2)"],
        ]
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda c: hub.run_on_server(srv_rec, c, timeout=10), cmds))
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 2.0)
        self.assertEqual(results[0]["rc"], 0)
        self.assertIn("slow-done", results[0]["out"])
        self.assertEqual(results[1]["out"].strip(), "fast-1")
        self.assertEqual(results[2]["out"].strip(), "fast-2")
        self.assertEqual(results[3]["rc"], 2)
        self.assertIn("err-line", results[3]["err"])

        # Reconnect superseding: second client replaces first without evicting new session
        c2 = ratholeagent.ReverseAgentClient(
            f"ws://127.0.0.1:{self.port}/ws/agent",
            name="rev-eu",
            token=tok,
            role="node",
            ping_interval=10,
            allow_test_python=True,
            public_ip="198.51.100.88",
        )
        self.clients.append(c2)
        # Prevent c1 from racing back in after superseding so we test clean replacement
        c1.stop_event.set()
        t2 = threading.Thread(target=c2.run_forever, daemon=True)
        t2.start()

        deadline = time.monotonic() + 5.0
        sess2 = None
        while time.monotonic() < deadline:
            with hub._reverse_lock:
                cur = hub._REVERSE_AGENTS.get("rev-eu")
                if cur and cur is not sess1 and cur.public_ip == "198.51.100.88":
                    sess2 = cur
                    break
            time.sleep(0.03)
        self.assertIsNotNone(sess2)
        t1.join(timeout=3)
        with hub._reverse_lock:
            self.assertIs(hub._REVERSE_AGENTS.get("rev-eu"), sess2)
        res_c2 = hub.run_on_server(srv_rec, [sys.executable, "-c", "print('from-c2')"], timeout=5)
        self.assertEqual(res_c2["rc"], 0)
        self.assertIn("from-c2", res_c2["out"])

        # Mid-exec disconnect wakes waiting caller immediately (no 60s wait)
        def stop_soon():
            time.sleep(0.15)
            c2.stop()
        threading.Thread(target=stop_soon, daemon=True).start()
        t_dis = time.monotonic()
        dis_res = hub.run_on_server(srv_rec, [sys.executable, "-c", "import time; time.sleep(20)"], timeout=60)
        self.assertLess(time.monotonic() - t_dis, 3.0)
        self.assertNotEqual(dis_res["rc"], 0)

    def test_allowlist_deploy_rotate_and_delete_disconnect(self):
        _, add_res = self._api("POST", "/api/servers", {"name": "rev-sec", "role": "node", "transport": "reverse_ws"})
        tok = add_res["api_token"]
        srv_rec = hub.load_json(hub.INV_PATH, [])[0]

        # Enforce strict ALLOWED_BINARIES over WS when allow_test_python=False
        c_sec = ratholeagent.ReverseAgentClient(
            f"ws://127.0.0.1:{self.port}/ws/agent",
            name="rev-sec",
            token=tok,
            role="node",
            allow_test_python=False,
            public_ip="203.0.113.5",
        )
        self.clients.append(c_sec)
        threading.Thread(target=c_sec.run_forever, daemon=True).start()
        sess = self._wait_session("rev-sec")

        for bad_cmd in (["bash", "-c", "id"], ["/tmp/evil/ratholenode", "ls"], ["python3", "-c", "print(1)"]):
            res = hub.run_on_server(srv_rec, bad_cmd, timeout=5)
            self.assertEqual(res["rc"], 1)
            self.assertIn("not permitted", res["err"])

        # deploy_to_server dispatches [ratholenode, update, stable] over reverse_ws
        with patch.object(hub, "run_on_server", return_value={"rc": 0, "out": "updated", "err": ""}) as m_ros:
            dep = hub.deploy_to_server(srv_rec)
        self.assertEqual(dep["rc"], 0)
        self.assertEqual(m_ros.call_args[0][1][:3], ["ratholenode", "update", "stable"])

        # Token rotation disconnects active WS session
        c_sec.stop_event.set()
        st_rot, rot_res = self._api("PUT", "/api/servers/rev-sec", {"rotate_token": True})
        self.assertEqual(st_rot, 200, rot_res)
        self.assertTrue(len(rot_res.get("api_token", "")) >= 32)
        self.assertTrue(sess.closed.wait(timeout=2.0))

        # Reconnect with rotated token, then verify DELETE closes session
        c_new = ratholeagent.ReverseAgentClient(
            f"ws://127.0.0.1:{self.port}/ws/agent",
            name="rev-sec",
            token=rot_res["api_token"],
            role="node",
            public_ip="203.0.113.6",
        )
        self.clients.append(c_new)
        threading.Thread(target=c_new.run_forever, daemon=True).start()
        sess_new = self._wait_session("rev-sec")
        c_new.stop_event.set()
        st_del, _ = self._api("DELETE", "/api/servers/rev-sec")
        self.assertEqual(st_del, 200)
        self.assertTrue(sess_new.closed.wait(timeout=2.0))


if __name__ == "__main__":
    unittest.main()
