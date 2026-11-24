#!/usr/bin/env python3
"""Unit and live HTTP mock tests for M7: Paqet (Direct PCK), Managed Xray, Cover Scanner & v2.2.0 changelog."""

import http.client
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HUB_DIR = os.path.join(REPO_ROOT, "rathole-manager", "ratholehub")
if HUB_DIR not in sys.path:
    sys.path.insert(0, HUB_DIR)

import hubcmds  # noqa: E402


def _load_hub():
    os.environ.setdefault("RATHOLEHUB_MOCK", "1")
    spec = importlib.util.spec_from_file_location("hub", os.path.join(HUB_DIR, "hub.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hub = _load_hub()


class TestM7HubCmds(unittest.TestCase):
    def test_iran_paqet_and_xray_scan(self):
        self.assertEqual(hubcmds.build_iran_cmd("paqet_status", {}), ["ratholectl", "paqet", "status"])
        self.assertEqual(hubcmds.build_iran_cmd("paqet_show", {}), ["ratholectl", "paqet", "show"])
        self.assertEqual(hubcmds.build_iran_cmd("paqet_off", {}), ["ratholectl", "paqet", "off"])
        cmd = hubcmds.build_iran_cmd("paqet_on", {
            "remote": "198.51.100.5:9999",
            "key": "0123456789abcdef0123456789abcdef",
            "mode": "fast2",
            "block": "aes-128-gcm",
            "conn": 2,
            "iface": "eth0",
            "local_ip": "203.0.113.2",
            "router_mac": "aa:bb:cc:dd:ee:ff",
        })
        self.assertEqual(cmd, [
            "ratholectl", "paqet", "on", "198.51.100.5:9999",
            "0123456789abcdef0123456789abcdef", "--mode", "fast2",
            "--block", "aes-128-gcm", "--conn", "2",
            "--iface", "eth0", "--local-ip", "203.0.113.2", "--router-mac", "aa:bb:cc:dd:ee:ff",
        ])
        self.assertIsNone(hubcmds.build_iran_cmd("paqet_on", {"remote": "bad host", "key": "0123456789abcdef"}))
        self.assertIsNone(hubcmds.build_iran_cmd("paqet_on", {
            "remote": "198.51.100.5:9999", "key": "0123456789abcdef", "router_mac": "badmac",
        }))
        self.assertIsNone(hubcmds.build_iran_cmd("paqet_on", {
            "remote": "198.51.100.5:9999", "key": "0123456789abcdef", "conn": 999,
        }))
        self.assertEqual(hubcmds.build_iran_cmd("paqet_node_on", {"name": "pq1"}), ["ratholectl", "paqet", "node", "pq1", "on"])
        self.assertEqual(hubcmds.build_iran_cmd("paqet_node_off", {"name": "pq1"}), ["ratholectl", "paqet", "node", "pq1", "off"])
        self.assertEqual(
            hubcmds.build_iran_cmd("xray_scan", {"domains": "www.microsoft.com,aws.amazon.com", "top": 5, "timeout": 3}),
            ["ratholectl", "xray", "scan", "--domains", "www.microsoft.com,aws.amazon.com", "--top", "5", "--timeout", "3", "--json"],
        )
        self.assertIsNone(hubcmds.build_iran_cmd("xray_scan", {"domains": "bad;id"}))

    def test_node_paqet_and_xray(self):
        self.assertEqual(
            hubcmds.build_node_cmd("paqet_on", {"port": 9999, "mode": "fast3", "block": "salsa20", "conn": 4}),
            ["ratholenode", "paqet", "on", "9999", "--mode", "fast3", "--block", "salsa20", "--conn", "4"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd("xray_status", {}),
            ["ratholenode", "xray", "status", "--json"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd("xray_uri", {"host": "panel.example.com", "port": 443}),
            ["ratholenode", "xray", "uri", "panel.example.com", "443"],
        )
        self.assertIsNone(hubcmds.build_node_cmd("xray_uri", {"port": 443}))
        cmd_r = hubcmds.build_node_cmd("xray_setup", {
            "mode": "reality",
            "port": 8443,
            "uuid": "11111111-2222-4333-8444-555555555555",
            "dest": "www.microsoft.com:443",
            "sni": "www.microsoft.com",
            "short_id": "a1b2c3d4",
            "proxy_protocol": True,
        })
        self.assertEqual(cmd_r, [
            "ratholenode", "xray", "setup", "reality",
            "--port", "8443", "--uuid", "11111111-2222-4333-8444-555555555555",
            "--dest", "www.microsoft.com:443", "--sni", "www.microsoft.com",
            "--short-id", "a1b2c3d4", "--proxy-protocol",
        ])
        # Unpaired REALITY keypair must be rejected
        self.assertIsNone(hubcmds.build_node_cmd("xray_setup", {
            "mode": "reality",
            "private_key": "A" * 43,
        }))
        # XHTTP TLS without cert/key must be rejected
        self.assertIsNone(hubcmds.build_node_cmd("xray_setup", {
            "mode": "xhttp", "tls": True, "path": "/xhttp",
        }))
        cmd_x = hubcmds.build_node_cmd("xray_setup", {
            "mode": "xhttp", "port": 2087, "path": "/xhttp", "xhttp_mode": "stream-up",
            "tls": True, "cert": "/etc/xray/cert.pem", "key": "/etc/xray/key.pem",
        })
        self.assertEqual(cmd_x, [
            "ratholenode", "xray", "setup", "xhttp",
            "--port", "2087", "--path", "/xhttp", "--mode", "stream-up",
            "--tls", "--cert", "/etc/xray/cert.pem", "--key", "/etc/xray/key.pem",
        ])

    def test_write_actions_and_audit_redaction(self):
        for w in ("paqet_on", "paqet_off", "paqet_node_on", "paqet_node_off", "xray_setup", "xray_off"):
            self.assertIn(w, hubcmds.WRITE_ACTIONS)
        for ro in ("paqet_status", "paqet_show", "xray_status", "xray_uri", "xray_scan"):
            self.assertNotIn(ro, hubcmds.WRITE_ACTIONS)

        r1 = hub._redact_cmd_for_audit("paqet_on", ["ratholectl", "paqet", "on", "1.2.3.4:9999", "supersecretkey123", "--mode", "fast"])
        self.assertNotIn("supersecretkey123", r1)
        self.assertIn("***REDACTED***", r1)

        r2 = hub._redact_cmd_for_audit("paqet_on", ["ratholenode", "paqet", "on", "9999", "nodesecretkey456", "--mode", "fast"])
        self.assertNotIn("nodesecretkey456", r2)
        self.assertIn("***REDACTED***", r2)

        r3 = hub._redact_cmd_for_audit("xray_setup", [
            "ratholenode", "xray", "setup", "reality",
            "--uuid", "11111111-2222-4333-8444-555555555555",
            "--private-key", "PrivKeySecretValue1234567890abcdef12345678",
        ])
        self.assertNotIn("11111111-2222-4333-8444-555555555555", r3)
        self.assertNotIn("PrivKeySecretValue", r3)


class TestM7HubHttpMock(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.conf_path = os.path.join(self.td.name, "config.json")
        self.inv_path = os.path.join(self.td.name, "inventory.json")
        self.audit_path = os.path.join(self.td.name, "audit.log")
        self.orig = (hub.CONF_PATH, hub.INV_PATH, hub.AUDIT_PATH, hub.MOCK)
        hub.CONF_PATH = self.conf_path
        hub.INV_PATH = self.inv_path
        hub.AUDIT_PATH = self.audit_path
        hub.MOCK = True
        self.admin_token = "test-admin-token-m7-0123456789abcdef"
        hub.save_config({
            "api_token": self.admin_token,
            "admin_password_sha256": hub._hash_password("TestPass123!"),
            "listen_host": "127.0.0.1",
            "listen_port": 0,
        })
        hub.set_inventory([
            {"name": "rp01", "role": "iran", "host": "5.202.4.40"},
            {"name": "trk01", "role": "node", "host": "198.51.100.5"},
        ])
        self.srv = hub.ThreadingHTTPServer(("127.0.0.1", 0), hub.Handler)
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()
        st, tok_res = self._req("POST", "/api/tokens", {"name": "reader", "scope": "read"})
        assert st in (200, 201) and tok_res.get("token"), (st, tok_res)
        self.ro_token = tok_res["token"]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        hub.CONF_PATH, hub.INV_PATH, hub.AUDIT_PATH, hub.MOCK = self.orig
        self.td.cleanup()

    def _req(self, method, path, body=None, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Authorization": f"Bearer {token or self.admin_token}", "Content-Type": "application/json"}
        conn.request(method, path, body=(json.dumps(body) if body is not None else None), headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        conn.close()
        return resp.status, json.loads(raw) if raw else {}

    def test_mock_paqet_and_xray_routes(self):
        st, d = self._req("POST", "/api/servers/rp01/action", {"action": "xray_scan", "args": {"top": 2}})
        self.assertEqual(st, 200)
        self.assertEqual(d["rc"], 0)
        parsed = json.loads(d["out"])
        self.assertEqual(parsed["recommended"], "www.microsoft.com")

        st, d = self._req("POST", "/api/servers/trk01/action", {"action": "xray_status", "args": {}})
        self.assertEqual(st, 200)
        self.assertNotIn("privateKey", d["out"])
        self.assertEqual(json.loads(d["out"])["mode"], "reality")

        st, d = self._req("POST", "/api/servers/trk01/action", {"action": "xray_uri", "args": {}})
        self.assertEqual(st, 200)
        self.assertIn("vless://", d["out"])

        st, d = self._req("GET", "/api/servers/trk01/paqetconnect")
        self.assertEqual(st, 200)
        self.assertTrue(d["ok"])
        self.assertEqual(d["remote"], "198.51.100.5:9999")
        self.assertEqual(d["mode"], "fast")

        # Scope guard: read token cannot fetch paqetconnect (contains shared key)
        st, d = self._req("GET", "/api/servers/trk01/paqetconnect", token=self.ro_token)
        self.assertEqual(st, 403)

    def test_v220_telegram_notify_dry_run(self):
        r = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "tools", "telegram_notify.py"), "--tag", "v2.2.0", "--dry-run"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr or r.stdout)
        self.assertIn("paqet", (r.stdout + r.stderr).lower())


if __name__ == "__main__":
    unittest.main()
