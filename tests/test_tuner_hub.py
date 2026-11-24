#!/usr/bin/env python3
"""Unit and live HTTP mock tests for RatholeHub tuner integration."""

import http.client
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MGR_ROOT = os.path.join(REPO_ROOT, "rathole-manager")
HUB_DIR = os.path.join(MGR_ROOT, "ratholehub")
for _p in (MGR_ROOT, HUB_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hubcmds  # noqa: E402
from tuner.profile import build_profile, encode_profile_b64  # noqa: E402


def _load_hub():
    os.environ.setdefault("RATHOLEHUB_MOCK", "1")
    spec = importlib.util.spec_from_file_location("hub", os.path.join(HUB_DIR, "hub.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hub = _load_hub()


def _sample_b64():
    p = build_profile(
        meta={"name": "arvan-hetzner", "tags": {"iran_dc": "arvan", "node_dc": "hetzner"}},
        environment={"pmtu": {"forward_bytes": 1460, "reverse_bytes": 1460}},
        diagnostics=[],
        benchmarks={"baseline": {"throughput_mbps": 120.0}, "winner": {"throughput_mbps": 340.0}},
        iran_config={"mtu": 1460, "qdisc": {"kind": "fq", "params": {}}, "sysctl": {"net.ipv4.tcp_congestion_control": "bbr"}},
        node_config={"mtu": 1460, "qdisc": {"kind": "fq", "params": {}}, "sysctl": {"net.ipv4.tcp_congestion_control": "bbr"}},
    )
    return p, encode_profile_b64(p)


class TestTunerHubCmds(unittest.TestCase):
    def test_bench_commands_validation_and_injection_rejection(self):
        tok = "0123456789abcdef0123456789abcdef"
        _, b64 = _sample_b64()

        self.assertEqual(hubcmds.build_iran_cmd("bench_status", {}), ["ratholectl", "bench", "status", "--json"])
        self.assertEqual(hubcmds.build_node_cmd("bench_status", {}), ["ratholenode", "bench", "status", "--json"])
        self.assertEqual(hubcmds.build_iran_cmd("bench_job", {"id": "job_123"}), ["ratholectl", "bench", "job", "job_123"])
        self.assertIsNone(hubcmds.build_iran_cmd("bench_job", {"id": "bad;id"}))

        ls_cmd = hubcmds.build_node_cmd("bench_listen_start", {"port": 29890, "data_port": 29891, "token": tok, "idle_timeout": 900})
        self.assertEqual(ls_cmd[:6], ["ratholenode", "bench", "listen", "--daemon", "--port", "29890"])
        self.assertIsNone(hubcmds.build_node_cmd("bench_listen_start", {"port": 29890, "token": "bad;tok"}))

        self.assertEqual(hubcmds.build_node_cmd("bench_listen_stop", {}), ["ratholenode", "bench", "stop-listen"])

        run_cmd = hubcmds.build_iran_cmd("bench_run_brutal", {
            "peer": "198.51.100.5:29890", "token": tok, "goal": "low-latency", "deep": True, "job_id": "job_abc",
        })
        self.assertIn("--mode", run_cmd)
        self.assertIn("brutal", run_cmd)
        self.assertIn("--deep", run_cmd)
        self.assertIsNone(hubcmds.build_iran_cmd("bench_run_brutal", {"peer": "198.51.100.5:29890\n", "token": tok}))
        self.assertIsNone(hubcmds.build_iran_cmd("bench_run_safe", {"peer": "198.51.100.5:29890", "token": tok, "goal": "invalid"}))

        tp = hubcmds.build_iran_cmd("bench_test_profile", {"peer": "198.51.100.5:29890", "token": tok, "profile": b64, "mode": "safe"})
        self.assertIsNotNone(tp)
        self.assertIsNone(hubcmds.build_iran_cmd("bench_test_profile", {"peer": "198.51.100.5:29890", "token": tok, "profile": "not_rthprof1"}))

        ap = hubcmds.build_iran_cmd("bench_apply", {"profile": b64, "side": "iran"})
        self.assertEqual(ap, ["ratholectl", "bench", "apply", b64, "--side", "iran", "--json"])
        self.assertIsNone(hubcmds.build_iran_cmd("bench_apply", {"profile": b64 + ";rm", "side": "iran"}))

        self.assertEqual(hubcmds.build_node_cmd("bench_rollback", {}), ["ratholenode", "bench", "rollback", "--json"])

        for ro in ("bench_status", "bench_job"):
            self.assertNotIn(ro, hubcmds.WRITE_ACTIONS)
        for wr in ("bench_listen_start", "bench_listen_stop", "bench_run_safe", "bench_run_brutal", "bench_test_profile", "bench_apply", "bench_rollback"):
            self.assertIn(wr, hubcmds.WRITE_ACTIONS)

        red = hub._redact_cmd_for_audit("bench_run_brutal", ["ratholectl", "bench", "run", "--peer", "1.2.3.4:29890", "--token", tok])
        self.assertNotIn(tok, red)
        self.assertIn("***REDACTED***", red)


class TestTunerHubHttpApi(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.conf_path = os.path.join(self.td.name, "config.json")
        self.inv_path = os.path.join(self.td.name, "inventory.json")
        self.audit_path = os.path.join(self.td.name, "audit.log")
        self.prof_path = os.path.join(self.td.name, "tuner-profiles.json")
        self.orig = (hub.CONF_PATH, hub.INV_PATH, hub.AUDIT_PATH, hub.MOCK, getattr(hub, "TUNER_PROFILES_PATH", None))
        hub.CONF_PATH = self.conf_path
        hub.INV_PATH = self.inv_path
        hub.AUDIT_PATH = self.audit_path
        hub.MOCK = True
        hub.TUNER_PROFILES_PATH = self.prof_path
        with hub._tuner_jobs_lock:
            hub._TUNER_JOBS.clear()

        self.admin_token = "test-admin-token-tuner-0123456789abc"
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
        orig_tp = self.orig[4]
        hub.CONF_PATH, hub.INV_PATH, hub.AUDIT_PATH, hub.MOCK = self.orig[:4]
        if orig_tp is not None:
            hub.TUNER_PROFILES_PATH = orig_tp
        self.td.cleanup()

    def _req(self, method, path, body=None, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Authorization": f"Bearer {token or self.admin_token}", "Content-Type": "application/json"}
        conn.request(method, path, body=(json.dumps(body) if body is not None else None), headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        conn.close()
        return resp.status, json.loads(raw) if raw else {}

    def test_tuner_jobs_profiles_apply_and_rollback(self):
        # Scope enforcement: read-only user cannot start, import, apply, or rollback
        st, _ = self._req("POST", "/api/tuner/start", {"iran": "rp01", "node": "trk01"}, token=self.ro_token)
        self.assertEqual(st, 403)
        st, _ = self._req("POST", "/api/tuner/profiles", {"profile": "rthprof1:abc"}, token=self.ro_token)
        self.assertEqual(st, 403)

        # Start mock benchmark job
        st, start_res = self._req("POST", "/api/tuner/start", {
            "iran": "rp01", "node": "trk01", "mode": "brutal", "goal": "balanced",
            "tags": {"iran_dc": "arvan-thr", "node_dc": "hetzner-fsn1"},
        })
        self.assertIn(st, (200, 202), start_res)
        job_id = start_res["job_id"]

        job = {}
        for _ in range(40):
            st, job = self._req("GET", f"/api/tuner/jobs/{job_id}")
            self.assertEqual(st, 200)
            if job.get("status") in ("done", "error", "cancelled"):
                break
            time.sleep(0.05)
        self.assertEqual(job.get("status"), "done", job)
        rep = job["result"]
        self.assertEqual(rep["profile"]["schema"], "rathole.netprofile.v1")
        self.assertTrue(rep["profile_b64"].startswith("rthprof1:"))

        # Import both rthprof1 string and raw AI JSON dict into library
        st, saved1 = self._req("POST", "/api/tuner/profiles", {
            "name": "arvan-to-hetzner",
            "profile": rep["profile_b64"],
        })
        self.assertEqual(st, 200, saved1)
        prof_id = saved1["profile"]["id"]

        ai_prof, _ = _sample_b64()
        st, saved2 = self._req("POST", "/api/tuner/profiles", {
            "name": "ai-edited",
            "profile": ai_prof,
        })
        self.assertEqual(st, 200, saved2)

        # Reject invalid/dangerous sysctl JSON import
        bad_prof = json.loads(json.dumps(ai_prof))
        bad_prof["iran_config"]["sysctl"]["kernel.modprobe"] = "/tmp/evil"
        st, bad_res = self._req("POST", "/api/tuner/profiles", {"profile": bad_prof})
        self.assertEqual(st, 400, bad_res)

        st, plist = self._req("GET", "/api/tuner/profiles")
        self.assertEqual(st, 200)
        self.assertEqual(len(plist["profiles"]), 2)

        # Apply stored profile to both servers & rollback both servers
        st, ap_res = self._req("POST", "/api/tuner/apply", {
            "iran": "rp01", "node": "trk01", "profile_id": prof_id,
        })
        self.assertEqual(st, 200, ap_res)
        self.assertTrue(ap_res["ok"])

        st, rb_res = self._req("POST", "/api/tuner/rollback", {"iran": "rp01", "node": "trk01"})
        self.assertEqual(st, 200, rb_res)
        self.assertTrue(rb_res["ok"])

        st, del_res = self._req("DELETE", f"/api/tuner/profiles/{prof_id}")
        self.assertEqual(st, 200, del_res)

        st, jl = self._req("GET", "/api/tuner/jobs")
        self.assertEqual(st, 200)
        self.assertGreaterEqual(len(jl["jobs"]), 1)

        st, c_res = self._req("POST", f"/api/tuner/jobs/{job_id}/cancel", {})
        self.assertEqual(st, 200, c_res)
        self.assertTrue(c_res["ok"])


if __name__ == "__main__":
    unittest.main()
