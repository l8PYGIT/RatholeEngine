"""Phase 2A backend & proxy hardening regression tests."""
import hashlib
import io
import json
import os
import ssl
import sys
import tempfile
import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../rathole-manager/ratholehub")))
import hub
import hubcmds
import ssh_proxy


class FakeSock:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.sent = []
        self.closed = False

    def recv(self, n):
        if not self._chunks:
            return b""
        c = self._chunks.pop(0)
        if len(c) > n:
            self._chunks.insert(0, c[n:])
            return c[:n]
        return c

    def sendall(self, data):
        self.sent.append(data)

    def shutdown(self, _how):
        pass

    def close(self):
        self.closed = True


class TestSSHProxyHardening(unittest.TestCase):
    def test_connect_socks5_handles_fragmented_reads_and_url_encoded_creds(self):
        # Greeting reply fragmented byte-by-byte: \x05\x02, auth reply \x01\x00,
        # connect reply \x05\x00\x00\x01 + 127.0.0.1 + port 22
        chunks = [
            b"\x05", b"\x02",
            b"\x01", b"\x00",
            b"\x05", b"\x00", b"\x00", b"\x01", b"\x7f\x00", b"\x00\x01\x00\x16",
        ]
        sock = FakeSock(chunks)
        parsed = urllib.parse.urlparse("socks5://my%40user:p%3Ass@127.0.0.1:1080")
        ssh_proxy.connect_socks5(sock, parsed, "198.51.100.1", 22)
        auth_pkt = sock.sent[1]
        self.assertIn(b"my@user", auth_pkt)
        self.assertIn(b"p:ss", auth_pkt)

    def test_connect_http_preserves_leftover_banner_bytes_and_caps_headers(self):
        banner = b"SSH-2.0-OpenSSH_9.2\r\n"
        sock = FakeSock([b"HTTP/1.1 200 Connection Established\r\n\r\n" + banner])
        parsed = urllib.parse.urlparse("http://u%3A1:p%402@127.0.0.1:8080")
        extra = ssh_proxy.connect_http(sock, parsed, "198.51.100.1", 22)
        self.assertEqual(extra, banner)
        self.assertIn(b"Basic dToxOnBAMg==", sock.sent[0])

        huge = FakeSock([b"X" * 20000])
        with self.assertRaises(ConnectionError):
            ssh_proxy.connect_http(huge, parsed, "198.51.100.1", 22)

    def test_https_proxy_wraps_tls_and_redacts_credentials_in_errors(self):
        raw_sock = MagicMock()
        tls_sock = MagicMock()
        tls_sock.recv.return_value = b""
        ctx = MagicMock()
        ctx.wrap_socket.return_value = tls_sock
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["ssh_proxy.py", "https://alice:topsecret@proxy.example:8443", "1.2.3.4", "22"]), \
             patch.object(ssh_proxy.socket, "create_connection", return_value=raw_sock), \
             patch.object(ssl, "create_default_context", return_value=ctx), \
             patch.object(sys, "stderr", stderr):
            with self.assertRaises(SystemExit) as ex:
                ssh_proxy.main()
        self.assertEqual(ex.exception.code, 1)
        ctx.wrap_socket.assert_called_once()
        self.assertNotIn("topsecret", stderr.getvalue())


class TestHubCmdsHardening(unittest.TestCase):
    def test_non_dict_and_non_string_args_never_raise_typeerror(self):
        self.assertIsNone(hubcmds.build_iran_cmd("add_node", ["not", "a", "dict"]))
        self.assertIsNone(hubcmds.build_node_cmd("add_svc", None))
        for action, bad_args in [
            ("add_node", {"name": 123, "inbound": "8080"}),
            ("rm_node", {"name": ["a"]}),
            ("proxy_add", {"name": "p1", "upstream": 999}),
            ("frp_node_on", {"name": None}),
            ("add_svc", {"name": 42, "token": "abcd1234", "inbound": "8080"}),
            ("plain_on", {"port": ["8880"]}),
            ("noise_on", {"remote": 123, "pubkey": "A" * 44}),
            ("backhaul_on", {"mode": ["nginx_tls"], "remote_addr": "x.test", "token": "a" * 16}),
        ]:
            with self.subTest(action=action):
                target = hubcmds.build_iran_cmd if action in ("add_node", "rm_node", "proxy_add", "frp_node_on") else hubcmds.build_node_cmd
                self.assertIsNone(target(action, bad_args))

    def test_strict_regexes_reject_leading_dash_dotdot_and_bad_ip(self):
        self.assertIsNone(hubcmds.RE_NAME.match("-badname"))
        self.assertIsNone(hubcmds.RE_HOST.match("-badhost.com"))
        self.assertIsNone(hubcmds.RE_PATH.match("/etc/nginx/../shadow"))
        self.assertIsNone(hubcmds.RE_IP.match("999.1.1.1"))
        self.assertIsNone(hubcmds.RE_UPSTREAM.match("http://127.0.0.1:99999"))
        self.assertIsNotNone(hubcmds.RE_IP.match("10.10.10.1"))
        self.assertIsNotNone(hubcmds.RE_NAME.match("node_01"))


class TestHubBackendHardening(unittest.TestCase):
    def test_body_json_rejects_negative_content_length_and_non_dict(self):
        h = object.__new__(hub.Handler)
        h.headers = {"Content-Length": "-1"}
        h.rfile = io.BytesIO(b'{"a":1}')
        self.assertEqual(h._body_json(), {})

        h2 = object.__new__(hub.Handler)
        h2.headers = {"Content-Length": "7"}
        h2.rfile = io.BytesIO(b'[1,2,3]')
        self.assertEqual(h2._body_json(), {})

    def test_authed_rejects_empty_api_token(self):
        cfg = {"api_token": ""}
        self.assertFalse(hub.authed(cfg, {"Authorization": "Bearer "}, {}))
        self.assertFalse(hub.check_session(cfg, hub.make_session_token(cfg)))

    def test_password_hashing_supports_pbkdf2_and_legacy_sha256(self):
        salted = hub._hash_password("MyStrongPass123")
        self.assertTrue(salted.startswith("pbkdf2_sha256$"))
        self.assertTrue(hub._verify_password("MyStrongPass123", salted))
        self.assertFalse(hub._verify_password("wrong", salted))

        legacy = hashlib.sha256(b"admin").hexdigest()
        self.assertTrue(hub._verify_password("admin", legacy))
        self.assertFalse(hub._verify_password("nope", legacy))

    def test_mock_intercepts_api_servers_and_inventory_redacts_tokens(self):
        srv = {"name": "api1", "role": "node", "transport": "api", "api_url": "http://127.0.0.1:8089", "api_token": "tok_secret_123"}
        with patch.object(hub, "MOCK", True), \
             patch.object(hub, "run_on_agent", side_effect=AssertionError("must not call agent in mock")):
            res = hub.run_on_server(srv, ["ratholenode", "ls"])
        self.assertEqual(res["rc"], 0)

        pub = hub._public_server({"name": "api1", "transport": "api", "api_url": "http://1.2.3.4:8089", "api_token": "tok_secret_123", "proxy": "http://u:p@127.0.0.1:8080"})
        self.assertNotIn("api_token", pub)
        self.assertTrue(pub["api_token_set"])
        self.assertNotIn(":p@", pub.get("proxy", ""))

    def test_audit_cmd_redacts_secrets_and_allows_root_ssh_key_path(self):
        cmd = hub.build_node_cmd("add_svc", {"name": "de1", "token": "deadbeef12345678", "inbound": "8080"})
        redacted = hub._redact_cmd_for_audit("add_svc", cmd)
        self.assertNotIn("deadbeef12345678", redacted)
        self.assertIn("***REDACTED***", redacted)
        self.assertTrue(hub.valid_ssh_key_path("/root/.ssh/id_ed25519"))
        self.assertFalse(hub.valid_ssh_key_path("/etc/passwd"))

    def test_save_json_handles_bare_filename_in_temp_dir(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.getcwd()
            try:
                os.chdir(td)
                hub.save_json("bare.json", {"ok": True})
                with open("bare.json", encoding="utf-8") as f:
                    self.assertEqual(json.loads(f.read()), {"ok": True})
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
