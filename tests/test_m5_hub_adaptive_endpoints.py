#!/usr/bin/env python3
"""Unit and live HTTP mock tests for M5: multi-carrier adaptive chain, backup endpoints, and Hub integration."""

import http.client
import importlib.util
import json
import os
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


class TestM5HubCmdsAndParser(unittest.TestCase):
    def test_adaptive_on_backwards_compat_and_chain(self):
        self.assertEqual(
            hubcmds.build_node_cmd("adaptive_on", {"interval": "30", "failures": "3", "recoveries": "5"}),
            ["ratholenode", "adaptive", "on", "--interval", "30", "--failures", "3", "--recoveries", "5"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd(
                "adaptive_on",
                {
                    "interval": "30",
                    "failures": "3",
                    "recoveries": "5",
                    "chain": "ws,noise,kcp,frp",
                    "probe_candidates": True,
                    "allow_insecure": "1",
                },
            ),
            [
                "ratholenode", "adaptive", "on",
                "--interval", "30", "--failures", "3", "--recoveries", "5",
                "--chain", "ws,noise,kcp,frp", "--probe-candidates", "--allow-insecure",
            ],
        )

        # Bad chains & flags rejected
        for bad_chain in ("ws,ws", "ws;id", "ws,bogus", "ws,kcp,noise,frp,plain,ws"):
            self.assertIsNone(hubcmds.build_node_cmd("adaptive_on", {"chain": bad_chain}), bad_chain)
        self.assertIsNone(hubcmds.build_node_cmd("adaptive_on", {"probe_candidates": "maybe"}))
        self.assertIsNone(hubcmds.build_node_cmd("adaptive_on", {"allow_insecure": 2}))

    def test_endpoints_commands_and_write_actions(self):
        self.assertEqual(hubcmds.build_node_cmd("endpoints_ls", {}), ["ratholenode", "endpoints", "ls", "--json"])
        self.assertEqual(hubcmds.build_node_cmd("endpoints_test", {}), ["ratholenode", "endpoints", "test", "--json"])
        self.assertEqual(
            hubcmds.build_node_cmd("endpoints_add", {"addr": "5.202.4.41:443"}),
            ["ratholenode", "endpoints", "add", "5.202.4.41:443"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd("endpoints_rm", {"addr": "5.202.4.41:443"}),
            ["ratholenode", "endpoints", "rm", "5.202.4.41:443"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd("endpoints_switch", {"addr": "5.202.4.41:443"}),
            ["ratholenode", "endpoints", "switch", "5.202.4.41:443"],
        )

        self.assertNotIn("endpoints_ls", hubcmds.WRITE_ACTIONS)
        self.assertNotIn("endpoints_test", hubcmds.WRITE_ACTIONS)
        for act in ("endpoints_add", "endpoints_rm", "endpoints_switch"):
            self.assertIn(act, hubcmds.WRITE_ACTIONS)
            self.assertIsNone(hubcmds.build_node_cmd(act, {"addr": "5.202.4.41:443;id"}))
            self.assertIsNone(hubcmds.build_node_cmd(act, {"addr": "5.202.4.41"}))

    def test_parse_adaptive_state_fields_and_sanitization(self):
        parsed = hub.parse_adaptive_state({
            "time": "2026-11-23T12:00:00Z",
            "current": "frp",
            "classification": "healthy",
            "latency_ms": 22,
            "consecutive_failures": 0,
            "consecutive_recoveries": 3,
            "last_switch_ts": 1700000123,
            "chain": "ws,noise,frp",
            "active_endpoint": "5.202.4.41:443",
            "primary_recoveries": 1,
            "last_reason": "carrier_failover",
            "token": "secret_should_be_stripped",
            "control_path": "/_rh/secret",
        })
        self.assertEqual(parsed["chain"], "ws,noise,frp")
        self.assertEqual(parsed["active_endpoint"], "5.202.4.41:443")
        self.assertEqual(parsed["last_reason"], "carrier_failover")
        self.assertNotIn("token", parsed)
        self.assertNotIn("control_path", parsed)


class TestM5HubEndpointsHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = (
            hub.CONF_PATH,
            hub.INV_PATH,
            hub.MOCK,
            hub.AUDIT_PATH,
            dict(hub._OVERVIEW_CACHE),
            hub._LAST_DRIFT_SUMMARY,
            hub._LOGIN_FAILS_TOTAL,
            dict(hub._HTTP_REQS),
            dict(hub._LOGIN_FAILS),
        )
        self.conf = os.path.join(self.tmp.name, "conf.json")
        self.inv = os.path.join(self.tmp.name, "inv.json")
        self.audit = os.path.join(self.tmp.name, "audit.log")
        self.tok = "test_m5_admin_token_abcdef123456"
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
        hub._OVERVIEW_CACHE.clear()
        hub._LAST_DRIFT_SUMMARY = None
        hub._LOGIN_FAILS_TOTAL = 0
        hub._HTTP_REQS.clear()
        hub._HTTP_REQS.update({"GET": 0, "POST": 0, "PUT": 0, "DELETE": 0})
        hub._LOGIN_FAILS.clear()

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
            orig_cache,
            orig_drift,
            orig_fails_tot,
            orig_reqs,
            orig_login_fails,
        ) = self.orig
        hub._OVERVIEW_CACHE.clear()
        hub._OVERVIEW_CACHE.update(orig_cache)
        hub._LAST_DRIFT_SUMMARY = orig_drift
        hub._LOGIN_FAILS_TOTAL = orig_fails_tot
        hub._HTTP_REQS.clear()
        hub._HTTP_REQS.update(orig_reqs)
        hub._LOGIN_FAILS.clear()
        hub._LOGIN_FAILS.update(orig_login_fails)
        self.tmp.cleanup()

    def _req(self, method, path, body=None, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            hdrs = {"Content-Type": "application/json", "Authorization": f"Bearer {token or self.tok}"}
            raw = json.dumps(body).encode("utf-8") if body is not None else None
            conn.request(method, path, body=raw, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data) if data else {}
        finally:
            conn.close()

    def test_hub_endpoints_and_adaptive_chain_actions(self):
        st_ls, d_ls = self._req("POST", "/api/servers/trk01/action", {"action": "endpoints_ls", "args": {}})
        self.assertEqual(st_ls, 200)
        self.assertEqual(d_ls["rc"], 0)
        ls_obj = json.loads(d_ls["out"])
        self.assertIn("backups", ls_obj)
        self.assertIn("scores", ls_obj)

        st_tst, d_tst = self._req("POST", "/api/servers/trk01/action", {"action": "endpoints_test", "args": {}})
        self.assertEqual(st_tst, 200)
        self.assertTrue(json.loads(d_tst["out"])["results"][0]["last_ok"])

        st_add, d_add = self._req("POST", "/api/servers/trk01/action", {"action": "endpoints_add", "args": {"addr": "5.202.4.42:443"}})
        self.assertEqual(st_add, 200)
        self.assertEqual(d_add["rc"], 0)

        st_ad, d_ad = self._req("POST", "/api/servers/trk01/action", {
            "action": "adaptive_on",
            "args": {"interval": "30", "failures": "3", "recoveries": "5", "chain": "ws,noise,frp", "probe_candidates": "1"},
        })
        self.assertEqual(st_ad, 200)
        self.assertEqual(d_ad["rc"], 0)


if __name__ == "__main__":
    unittest.main()
