#!/usr/bin/env python3
"""Unit and live HTTP mock tests for M2: hubdiag (link_test & fleet drift), hubcmds, and Hub endpoints."""

from datetime import datetime, timezone
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
import hubdiag  # noqa: E402


def _load_hub():
    os.environ.setdefault("RATHOLEHUB_MOCK", "1")
    spec = importlib.util.spec_from_file_location("hub", os.path.join(HUB_DIR, "hub.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hub = _load_hub()


class TestM2HubCmds(unittest.TestCase):
    def test_link_test_commands_and_readonly(self):
        self.assertEqual(
            hubcmds.build_iran_cmd("link_test", {"name": "trk01", "count": 7}),
            ["ratholectl", "test", "trk01", "--count", "7", "--json"],
        )
        self.assertEqual(
            hubcmds.build_iran_cmd("link_test", {"name": "trk01"}),
            ["ratholectl", "test", "trk01", "--count", "5", "--json"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd("link_test", {"count": "10"}),
            ["ratholenode", "test", "--count", "10", "--json"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd("link_test", {}),
            ["ratholenode", "test", "--count", "5", "--json"],
        )

        # Injection & out-of-range rejection
        self.assertIsNone(hubcmds.build_iran_cmd("link_test", {"name": "trk01;id"}))
        self.assertIsNone(hubcmds.build_iran_cmd("link_test", {"name": ""}))
        self.assertIsNone(hubcmds.build_iran_cmd("link_test", {"name": "trk01", "count": 0}))
        self.assertIsNone(hubcmds.build_iran_cmd("link_test", {"name": "trk01", "count": 21}))
        self.assertIsNone(hubcmds.build_node_cmd("link_test", {"count": "5;id"}))
        self.assertNotIn("link_test", hubcmds.WRITE_ACTIONS)


class TestM2SynthesizeLinkTest(unittest.TestCase):
    def test_diagnosis_cases(self):
        ok_ir = {"ok": True, "verdict": "healthy", "listener_up": True, "port": 1005}
        ok_nd = {"ok": True, "verdict": "healthy", "backends": [{"name": "trk01", "up": True, "port": 8444}]}

        r = hubdiag.synthesize_link_test("trk01", ok_ir, ok_nd, peer_name="trk01")
        self.assertTrue(r["ok"])
        self.assertEqual(r["verdict"], "healthy")
        self.assertEqual(r["diagnosis_code"], "healthy")

        deg_nd = {**ok_nd, "verdict": "degraded"}
        r_deg = hubdiag.synthesize_link_test("trk01", ok_ir, deg_nd, peer_name="trk01")
        self.assertTrue(r_deg["ok"])
        self.assertEqual(r_deg["verdict"], "degraded")
        self.assertEqual(r_deg["diagnosis_code"], "degraded_link")

        bad_back = {**ok_nd, "backends": [{"name": "trk01", "up": False, "port": 8444}]}
        r_back = hubdiag.synthesize_link_test("trk01", ok_ir, bad_back, peer_name="trk01")
        self.assertFalse(r_back["ok"])
        self.assertEqual(r_back["diagnosis_code"], "backend_down")

        r_lst = hubdiag.synthesize_link_test("trk01", {**ok_ir, "ok": False, "listener_up": False}, ok_nd)
        self.assertEqual(r_lst["diagnosis_code"], "listener_down")

        r_car = hubdiag.synthesize_link_test("trk01", ok_ir, {**ok_nd, "ok": False, "transport": "ws", "detail": "tls_error"})
        self.assertEqual(r_car["diagnosis_code"], "carrier_unreachable")

        r_e2e = hubdiag.synthesize_link_test("trk01", {"ok": False, "verdict": "failed", "listener_up": True, "detail": "remote_closed"}, ok_nd)
        self.assertEqual(r_e2e["diagnosis_code"], "e2e_failed")


class TestM2ComputeFleetDrift(unittest.TestCase):
    def _clean_fixture(self):
        inv = [
            {"name": "rp01", "role": "iran", "host": "5.202.4.40"},
            {"name": "trk01", "role": "node", "host": "198.51.100.10"},
        ]
        ovs = {
            "rp01": {
                "server": "rp01", "role": "iran", "host": "5.202.4.40", "domain": "rp01.example.com", "reachable": True,
                "version": {"manager": "2.1.1"},
                "status": {
                    "domain": "rp01.example.com",
                    "cert": {"expiry": "Dec 20 00:00:00 2026 GMT"},
                    "services": {"rathole_server": "yes", "nginx": "yes", "nginx_config_ok": "yes", "backhaul": "yes"},
                    "features": {"backhaul": {"configured": True, "active": True, "profile": "balanced"}},
                },
                "backhaul": {"enabled": True, "profile": "balanced", "transport": "wsmux"},
                "nodes": [{"name": "trk01", "port": "1005", "inbound_port": "8444", "transport": "backhaul", "sni": ""}],
            },
            "trk01": {
                "server": "trk01", "role": "node", "host": "198.51.100.10", "reachable": True,
                "version": {"manager": "2.1.1"},
                "main_server": "rp01.example.com:443", "main_tunnel": "ws",
                "services": [],
                "backhaul_services": [{"name": "trk01", "inbound": "8444"}],
                "backhaul": {"enabled": True, "profile": "balanced", "transport": "wssmux"},
                "status": {"main": {"transport": "ws", "service": {"name": "rathole-client", "active": True}}},
            },
        }
        return inv, ovs

    def test_clean_fleet(self):
        inv, ovs = self._clean_fixture()
        now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
        res = hubdiag.compute_fleet_drift(inv, ovs, hub_version="2.1.1", now=now)
        self.assertTrue(res["summary"]["clean"])
        self.assertEqual(res["summary"]["total"], 0)
        self.assertEqual(res["items"], [])

    def test_all_drift_kinds_detected(self):
        inv, ovs = self._clean_fixture()
        inv.append({"name": "dead-srv", "role": "node", "host": "203.0.113.9"})
        ovs["dead-srv"] = {"reachable": False, "error": "ssh timeout"}

        # Version skew, cert expiring (<14d), service down, orphan Iran node, inbound mismatch
        ovs["rp01"]["version"]["manager"] = "2.0.0"
        ovs["rp01"]["status"]["cert"]["expiry"] = "Nov 25 00:00:00 2026 GMT"
        ovs["rp01"]["status"]["services"]["nginx"] = "no"
        ovs["rp01"]["nodes"].append({"name": "orphan_ir", "port": "1006", "inbound_port": "8445", "transport": "ws", "sni": ""})
        ovs["trk01"]["backhaul_services"][0]["inbound"] = "9999"
        ovs["trk01"]["services"] = [{"name": "orphan_node_svc", "inbound": "8450"}]
        ovs["trk01"]["backhaul"]["profile"] = "aggressive"

        now = datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc)
        res = hubdiag.compute_fleet_drift(inv, ovs, hub_version="2.1.1", now=now)
        kinds = {(it["kind"], it.get("service")) for it in res["items"]}
        self.assertIn(("unreachable", ""), kinds)
        self.assertIn(("version_skew", ""), kinds)
        self.assertIn(("cert_expiring", "tls_cert"), kinds)
        self.assertIn(("service_down", "nginx"), kinds)
        self.assertIn(("orphan_iran_node", "orphan_ir"), kinds)
        self.assertIn(("orphan_foreign_service", "orphan_node_svc"), kinds)
        self.assertIn(("inbound_port_mismatch", "trk01"), kinds)
        self.assertIn(("profile_mismatch", "trk01"), kinds)
        self.assertFalse(res["summary"]["clean"])

    def test_expired_cert_and_carrier_and_adaptive_info_and_frp_protocol(self):
        inv, ovs = self._clean_fixture()
        ovs["rp01"]["status"]["cert"]["expiry"] = "Nov 10 00:00:00 2026 GMT"
        ovs["rp01"]["frp"] = {"enabled": True, "transport": "quic"}
        ovs["rp01"]["nodes"] = [
            {"name": "n_frp", "port": "1010", "inbound_port": "8444", "transport": "frp", "sni": ""},
            {"name": "n_ws", "port": "1011", "inbound_port": "8445", "transport": "ws", "sni": ""},
            {"name": "n_nz", "port": "1012", "inbound_port": "8446", "transport": "noise", "sni": ""},
        ]
        ovs["trk01"]["services"] = [
            {"name": "n_frp", "inbound": "8444"},
            {"name": "n_ws", "inbound": "8445"},
            {"name": "n_nz", "inbound": "8446"},
        ]
        ovs["trk01"]["backhaul_services"] = []
        ovs["trk01"]["main_tunnel"] = "frp"
        ovs["trk01"]["frp"] = {"enabled": True, "transport": "tcp"}

        now = datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc)
        res = hubdiag.compute_fleet_drift(inv, ovs, hub_version="2.1.1", now=now)
        by_key = {(it["kind"], it["service"]): it for it in res["items"]}
        self.assertEqual(by_key[("cert_expiring", "tls_cert")]["severity"], "error")
        self.assertEqual(by_key[("protocol_mismatch", "n_frp")]["severity"], "error")
        self.assertEqual(by_key[("carrier_mismatch", "n_ws")]["severity"], "error")
        self.assertEqual(by_key[("carrier_mismatch", "n_nz")]["severity"], "error")

        # ws <-> kcp adaptive failover must be info severity (not error)
        ovs["rp01"]["nodes"] = [{"name": "n_ws", "port": "1011", "inbound_port": "8445", "transport": "ws", "sni": ""}]
        ovs["trk01"]["services"] = [{"name": "n_ws", "inbound": "8445"}]
        ovs["trk01"]["main_tunnel"] = "kcp"
        res2 = hubdiag.compute_fleet_drift(inv, ovs, hub_version="2.1.1", now=now)
        cm = [it for it in res2["items"] if it["kind"] == "carrier_mismatch"]
        self.assertEqual(len(cm), 1)
        self.assertEqual(cm[0]["severity"], "info")


class TestM2HubHttpEndpoints(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = (hub.CONF_PATH, hub.INV_PATH, hub.MOCK, hub.AUDIT_PATH)
        self.conf = os.path.join(self.tmp.name, "conf.json")
        self.inv = os.path.join(self.tmp.name, "inv.json")
        self.audit = os.path.join(self.tmp.name, "audit.log")
        self.tok = "test_m2_token_abcdef123456"
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
        self.srv = hub.ThreadingHTTPServer(("127.0.0.1", 0), hub.Handler)
        self.port = self.srv.server_address[1]
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.th.join(timeout=2)
        hub.CONF_PATH, hub.INV_PATH, hub.MOCK, hub.AUDIT_PATH = self.orig
        self.tmp.cleanup()

    def _req(self, method, path, body=None, authed=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            hdrs = {"Content-Type": "application/json"}
            if authed:
                hdrs["Authorization"] = f"Bearer {self.tok}"
            raw = json.dumps(body).encode("utf-8") if body is not None else None
            conn.request(method, path, body=raw, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data) if data else {}
        finally:
            conn.close()

    def test_fleet_drift_and_link_test_endpoints(self):
        st0, _ = self._req("GET", "/api/fleet/drift", authed=False)
        self.assertEqual(st0, 401)
        st1, drift = self._req("GET", "/api/fleet/drift")
        self.assertEqual(st1, 200)
        self.assertEqual(drift["servers_checked"], 2)
        self.assertIn("summary", drift)
        self.assertIn("items", drift)

        st_u, _ = self._req("POST", "/api/servers/rp01/link-test", {"node": "trk01"}, authed=False)
        self.assertEqual(st_u, 401)

        st_bad_cnt, _ = self._req("POST", "/api/servers/rp01/link-test", {"node": "trk01", "count": 99})
        self.assertEqual(st_bad_cnt, 400)

        st_bad_nm, _ = self._req("POST", "/api/servers/rp01/link-test", {"node": "trk01;id"})
        self.assertEqual(st_bad_nm, 400)

        st_ok, res = self._req("POST", "/api/servers/rp01/link-test", {"node": "trk01", "count": 3})
        self.assertEqual(st_ok, 200)
        self.assertTrue(res["ok"])
        self.assertEqual(res["verdict"], "healthy")
        self.assertEqual(res["iran_to_node"]["count"], 3)
        self.assertEqual(res["node_to_iran"]["count"], 3)

        st_nd, nd_res = self._req("POST", "/api/servers/trk01/link-test", {"count": 4})
        self.assertEqual(st_nd, 200)
        self.assertTrue(nd_res["ok"])
        self.assertEqual(nd_res["node_to_iran"]["count"], 4)


if __name__ == "__main__":
    unittest.main()
