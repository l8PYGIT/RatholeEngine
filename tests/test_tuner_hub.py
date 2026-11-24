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
        self.jobs_path = os.path.join(self.td.name, "tuner-jobs.json")
        self.orig = (
            hub.CONF_PATH,
            hub.INV_PATH,
            hub.AUDIT_PATH,
            hub.MOCK,
            getattr(hub, "TUNER_PROFILES_PATH", None),
            getattr(hub, "TUNER_JOBS_PATH", None),
        )
        hub.CONF_PATH = self.conf_path
        hub.INV_PATH = self.inv_path
        hub.AUDIT_PATH = self.audit_path
        hub.MOCK = True
        hub.TUNER_PROFILES_PATH = self.prof_path
        hub.TUNER_JOBS_PATH = self.jobs_path
        hub._tuner_jobs_loaded_path = None
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
        orig_tp, orig_tj = self.orig[4], self.orig[5]
        hub.CONF_PATH, hub.INV_PATH, hub.AUDIT_PATH, hub.MOCK = self.orig[:4]
        if orig_tp is not None:
            hub.TUNER_PROFILES_PATH = orig_tp
        if orig_tj is not None:
            hub.TUNER_JOBS_PATH = orig_tj
        hub._tuner_jobs_loaded_path = None
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

    def test_tuner_start_resolves_api_transport_node_host(self):
        orig_cache = dict(hub._OVERVIEW_CACHE)
        self.addCleanup(lambda: (hub._OVERVIEW_CACHE.clear(), hub._OVERVIEW_CACHE.update(orig_cache)))

        hub.set_inventory([
            {"name": "rp01", "role": "iran", "host": "5.202.4.40"},
            {"name": "api-node", "role": "node", "transport": "api", "api_url": "http://78.135.77.57:8089", "api_token": "agent-tok"},
            {"name": "loop-node", "role": "node", "transport": "api", "api_url": "http://127.0.0.1:8089", "api_token": "loop-tok"},
            {"name": "empty-node", "role": "node", "transport": "api"},
        ])
        hub._OVERVIEW_CACHE["loop-node"] = (time.time() + 60, {"public_ip": "91.107.14.22", "host": "127.0.0.1"})

        # Resolution helper checks (when present)
        self.assertEqual(hub.node_public_host({"name": "api-node", "transport": "api", "api_url": "http://78.135.77.57:8089"}), "78.135.77.57")
        self.assertEqual(hub.node_public_host({"name": "loop-node", "transport": "api", "api_url": "http://127.0.0.1:8089"}), "91.107.14.22")
        self.assertEqual(hub.node_public_host({"name": "loop-node", "public_ip": "1.2.3.4", "host": "5.6.7.8"}, explicit="9.9.9.9"), "9.9.9.9")
        self.assertEqual(hub.node_public_host({"name": "empty-node"}), "")

        # Starting tuner on REST Agent node without `host` or `public_ip` must succeed, incl. spaced tags
        st, start_res = self._req("POST", "/api/tuner/start", {
            "iran": "rp01", "node": "api-node", "mode": "brutal", "goal": "balanced",
            "tags": {"iran_dc": "arvan tehran", "node_dc": "hetzner fsn1"},
        })
        self.assertIn(st, (200, 202), start_res)
        jid = start_res["job_id"]
        job = {}
        for _ in range(40):
            st, job = self._req("GET", f"/api/tuner/jobs/{jid}")
            if job.get("status") in ("done", "error", "cancelled"):
                break
            time.sleep(0.05)
        self.assertEqual(job.get("status"), "done", job)

        # Unresolvable node still returns clear 400 error
        st_bad, err_res = self._req("POST", "/api/tuner/start", {"iran": "rp01", "node": "empty-node"})
        self.assertEqual(st_bad, 400)
        self.assertIn("node host invalid", err_res.get("error", ""))

    def test_job_persistence_error_formatting_and_json_extraction(self):
        # 1) Resilient JSON extraction from noisy stdout
        noisy = "[*] rathole-tuner notice: checking kernel\nWARNING: clock skew 5s\n{\"ok\": true, \"phase\": \"cc_qdisc_pacing\", \"stage_index\": 2}\n"
        parsed = hub._extract_json_obj(noisy)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["stage_index"], 2)

        # 2) Traceback tail extraction & outdated-node hint
        long_tb = "Traceback (most recent call last):\n" + "\n".join(
            f'  File "/usr/local/share/rathole/tuner/mod{i}.py", line {10 + i}, in fn_{i}\n    do_something_long_identifier_{i}()'
            for i in range(12)
        ) + "\ntuner.profile.ProfileValidationError: remote_cand.qdisc invalid: mq"
        formatted_tb = hub._format_tuner_error("iran bench", {"rc": 1, "err": long_tb, "out": ""})
        self.assertTrue(formatted_tb.startswith("[iran bench] tuner.profile.ProfileValidationError: remote_cand.qdisc invalid: mq"))
        self.assertLessEqual(len(formatted_tb), 1200)

        outdated_err = hub._format_tuner_error("node responder", {"rc": 1, "err": "[!] dstvr nashenakhte: bench", "out": ""})
        self.assertIn("Hint: update this server to v2.3+", outdated_err)

        # 3) Completed job persists to disk across cleared in-memory dict
        st, start_res = self._req("POST", "/api/tuner/start", {"iran": "rp01", "node": "trk01"})
        self.assertIn(st, (200, 202), start_res)
        jid = start_res["job_id"]
        for _ in range(40):
            _, j = self._req("GET", f"/api/tuner/jobs/{jid}")
            if j.get("status") == "done":
                break
            time.sleep(0.05)
        self.assertTrue(os.path.exists(self.jobs_path))

        with hub._tuner_jobs_lock:
            hub._TUNER_JOBS.clear()
            hub._tuner_jobs_loaded_path = None
        st_list, jl = self._req("GET", "/api/tuner/jobs")
        self.assertEqual(st_list, 200)
        restored = next((x for x in jl["jobs"] if x["job_id"] == jid), None)
        self.assertIsNotNone(restored)
        self.assertEqual(restored["status"], "done")
        self.assertIn("profile_b64", restored.get("result") or {})

        # 4) Persisted 'running' job converts cleanly to 'error' on hub reload, preserving live_trials & pmtu
        hub.save_json(self.jobs_path, {
            "jobs": [{
                "job_id": "job_crashed_99",
                "iran": "rp01",
                "node": "trk01",
                "status": "running",
                "phase": "mtu_mss_offload",
                "stage_index": 1,
                "stage_total": 6,
                "created_at": int(time.time()),
                "pmtu": {"forward_bytes": 1420, "reverse_bytes": 1420, "blackhole_detected": False},
                "live_trials": [{"id": "baseline", "name": "baseline", "stage": 0, "throughput_mbps": 180.0, "score": 55.0}],
            }]
        })
        hub._tuner_jobs_loaded_path = None
        st_crash, crashed = self._req("GET", "/api/tuner/jobs/job_crashed_99")
        self.assertEqual(st_crash, 200, crashed)
        self.assertEqual(crashed["status"], "error")
        self.assertIn("restarted", (crashed.get("error") or "").lower())
        self.assertEqual(crashed["pmtu"]["forward_bytes"], 1420)
        self.assertEqual(len(crashed["live_trials"]), 1)

        # 5) Live progress forwarding + visible error capture on failure
        orig_run = hub.run_on_server
        hub.MOCK = False

        def fake_run(server, cmd_args, timeout=120):
            if cmd_args[:3] == ["ratholenode", "bench", "listen"]:
                return {"rc": 0, "out": json.dumps({"ok": True, "pid": 999, "port": 29890}), "err": ""}
            if cmd_args[:3] == ["ratholenode", "bench", "stop-listen"]:
                return {"rc": 0, "out": json.dumps({"ok": True, "stopped": True}), "err": ""}
            if cmd_args[:3] == ["ratholectl", "bench", "job"]:
                return {"rc": 0, "out": json.dumps({
                    "phase": "mtu_mss_offload", "stage_index": 1, "stage_total": 6,
                    "completed_trials": 2, "estimated_trials": 10, "best_so_far": 77.5,
                    "pmtu": {"forward_bytes": 1380, "reverse_bytes": 1380, "blackhole_detected": False},
                    "live_trials": [{"id": "baseline", "name": "baseline", "stage": 0, "throughput_mbps": 110.0, "loaded_rtt_p95_ms": 95.0, "jitter_ms": 6.0, "retrans_pct": 0.4, "score": 77.5, "disqualified": False}],
                }), "err": ""}
            if cmd_args[:3] == ["ratholectl", "bench", "run"]:
                time.sleep(1.6)
                return {"rc": 1, "out": "", "err": "Traceback (most recent call last):\n  File \"x.py\", line 1\nRuntimeError: port 29891 probe failed"}
            return {"rc": 0, "out": "", "err": ""}

        hub.run_on_server = fake_run
        try:
            st_l, res_l = self._req("POST", "/api/tuner/start", {"iran": "rp01", "node": "trk01"})
            self.assertIn(st_l, (200, 202), res_l)
            ljid = res_l["job_id"]
            j_live = {}
            for _ in range(50):
                _, j_live = self._req("GET", f"/api/tuner/jobs/{ljid}")
                if j_live.get("status") == "error":
                    break
                time.sleep(0.08)
            self.assertEqual(j_live.get("status"), "error", j_live)
            self.assertIn("RuntimeError: port 29891 probe failed", j_live.get("error") or "")
            self.assertEqual((j_live.get("pmtu") or {}).get("forward_bytes"), 1380)
            self.assertGreaterEqual(len(j_live.get("live_trials") or []), 1)
        finally:
            hub.run_on_server = orig_run
            hub.MOCK = True


if __name__ == "__main__":
    unittest.main()
