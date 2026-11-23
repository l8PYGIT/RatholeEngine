#!/usr/bin/env python3
"""Unit and live HTTP mock tests for M3: hubsec (tokens, CSRF, 2FA TOTP/recovery, audit chain, /metrics), hubcmds undo, and Hub HTTP endpoints."""

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
HUB_DIR = os.path.join(REPO_ROOT, "rathole-manager", "ratholehub")
if HUB_DIR not in sys.path:
    sys.path.insert(0, HUB_DIR)

import hubcmds  # noqa: E402
import hubsec  # noqa: E402


def _load_hub():
    os.environ.setdefault("RATHOLEHUB_MOCK", "1")
    spec = importlib.util.spec_from_file_location("hub", os.path.join(HUB_DIR, "hub.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hub = _load_hub()


class TestM3HubSecUnits(unittest.TestCase):
    def test_rfc6238_totp_vectors_and_replay(self):
        # RFC 6238 ASCII "12345678901234567890" -> Base32 GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ
        sec = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.assertEqual(hubsec.totp_code(sec, for_time=59, digits=6), "287082")
        self.assertEqual(hubsec.totp_code(sec, for_time=1111111109, digits=6), "081804")

        step_t = int(1000000 // 30)
        code = hubsec.totp_code(sec, for_time=1000000)
        self.assertEqual(hubsec.verify_totp(sec, code, for_time=1000000), step_t)
        # +/-1 window accepted
        prev_code = hubsec.totp_code(sec, for_time=1000000 - 30)
        self.assertEqual(hubsec.verify_totp(sec, prev_code, for_time=1000000), step_t - 1)
        # Out of window rejected
        old_code = hubsec.totp_code(sec, for_time=1000000 - 120)
        self.assertIsNone(hubsec.verify_totp(sec, old_code, for_time=1000000))
        # Replay protection
        self.assertIsNone(hubsec.verify_totp(sec, code, for_time=1000000, last_step=step_t))
        self.assertIsNone(hubsec.verify_totp(sec, "abcdef", for_time=1000000))

    def test_recovery_codes_single_use(self):
        plain, hashes = hubsec.generate_recovery_codes(8)
        self.assertEqual(len(plain), 8)
        self.assertEqual(len(hashes), 8)
        ok, rem = hubsec.consume_recovery_code(hashes, plain[2].lower().replace("-", " "))
        self.assertTrue(ok)
        self.assertEqual(len(rem), 7)
        # Reusing same code fails
        ok2, rem2 = hubsec.consume_recovery_code(rem, plain[2])
        self.assertFalse(ok2)
        self.assertEqual(len(rem2), 7)
        # Invalid format fails cleanly
        ok3, _ = hubsec.consume_recovery_code(rem, "ZZZ")
        self.assertFalse(ok3)

    def test_scoped_tokens_and_resolve_auth(self):
        raw_ro, rec_ro = hubsec.create_scoped_token("grafana-ro", "read", now=1000)
        self.assertTrue(raw_ro.startswith("rht_"))
        self.assertTrue(rec_ro["id"].startswith("tok_"))
        pub = hubsec.public_token_view(rec_ro)
        self.assertNotIn("sha256", pub)

        raw_exp, rec_exp = hubsec.create_scoped_token("temp-op", "operate", expires_at=500, now=400)
        cfg = {"api_token": "legacy_admin_secret", "tokens": [rec_ro, rec_exp]}

        a_ro = hubsec.resolve_auth(cfg, {"Authorization": "Bearer " + raw_ro}, {}, lambda c, s: False, now=1010)
        self.assertEqual(a_ro, {"scope": "read", "via": "bearer", "principal": "token:grafana-ro"})
        self.assertTrue(hubsec.scope_allows(a_ro["scope"], "read"))
        self.assertFalse(hubsec.scope_allows(a_ro["scope"], "operate"))
        self.assertFalse(hubsec.scope_allows(a_ro["scope"], "admin"))

        self.assertIsNone(hubsec.resolve_auth(cfg, {"Authorization": "Bearer " + raw_exp}, {}, lambda c, s: False, now=600))
        self.assertIsNone(hubsec.resolve_auth(cfg, {"Authorization": "Bearer wrong"}, {}, lambda c, s: False))

        a_leg = hubsec.resolve_auth(cfg, {"Authorization": "Bearer legacy_admin_secret"}, {}, lambda c, s: False)
        self.assertEqual(a_leg, {"scope": "admin", "via": "bearer", "principal": "api"})

        a_ck = hubsec.resolve_auth(cfg, {}, {"rhsession": "good"}, lambda c, s: s == "good")
        self.assertEqual(a_ck, {"scope": "admin", "via": "cookie", "principal": "admin"})

    def test_csrf_guard(self):
        ck = {"scope": "admin", "via": "cookie", "principal": "admin"}
        br = {"scope": "admin", "via": "bearer", "principal": "api"}

        # Bearer skips CSRF
        self.assertEqual(hubsec.check_csrf({"Origin": "https://evil.test", "Sec-Fetch-Site": "cross-site"}, br)[0], True)
        # Cookie CSRF rules
        self.assertFalse(hubsec.check_csrf({"Host": "hub.local", "Sec-Fetch-Site": "cross-site"}, ck)[0])
        self.assertFalse(hubsec.check_csrf({"Host": "hub.local", "Origin": "https://evil.test"}, ck)[0])
        self.assertFalse(hubsec.check_csrf({"Host": "hub.local", "Origin": "null"}, ck)[0])
        self.assertFalse(hubsec.check_csrf({"Host": "hub.local", "Referer": "https://evil.test/x"}, ck)[0])
        self.assertTrue(hubsec.check_csrf({"Host": "hub.local:8088", "Origin": "http://hub.local:8088"}, ck)[0])
        self.assertTrue(hubsec.check_csrf({"Host": "127.0.0.1:8088", "X-Forwarded-Host": "panel.example.com", "Origin": "https://panel.example.com"}, ck)[0])

    def test_audit_chain_verification_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "audit.log")
            self.assertTrue(hubsec.verify_audit_chain(p)["ok"])

            # Mixed legacy entry + chained entries
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"ts": 100, "user": "admin", "server": "hub", "action": "init", "cmd": "x", "rc": 0}) + "\n")
                prev = hubsec.GENESIS_HASH
                for idx in range(3):
                    ent = hubsec.build_chained_audit_entry("api@127.0.0.1", "rp01", "act_%d" % idx, "cmd", 0, prev, ts=200 + idx)
                    prev = ent["hash"]
                    f.write(json.dumps(ent, ensure_ascii=False) + "\n")

            res = hubsec.verify_audit_chain(p)
            self.assertTrue(res["ok"])
            self.assertEqual(res["legacy"], 1)
            self.assertEqual(res["chained"], 3)
            self.assertEqual(res["total"], 4)

            # Tamper middle chained line (line 3)
            with open(p, "r", encoding="utf-8") as f:
                lines = f.readlines()
            tampered_lines = list(lines)
            tampered_lines[2] = tampered_lines[2].replace("act_1", "act_9")
            with open(p, "w", encoding="utf-8") as f:
                f.writelines(tampered_lines)
            bad1 = hubsec.verify_audit_chain(p)
            self.assertFalse(bad1["ok"])
            self.assertEqual(bad1["broken_line"], 3)

            # Delete middle chained line -> prev_hash mismatch at next line
            with open(p, "w", encoding="utf-8") as f:
                f.writelines([lines[0], lines[1], lines[3]])
            bad2 = hubsec.verify_audit_chain(p)
            self.assertFalse(bad2["ok"])
            self.assertEqual(bad2["broken_line"], 3)

            # Append unchained line after chain started -> rejected
            with open(p, "w", encoding="utf-8") as f:
                f.writelines(lines + [json.dumps({"ts": 999, "user": "x"}) + "\n"])
            bad3 = hubsec.verify_audit_chain(p)
            self.assertFalse(bad3["ok"])
            self.assertEqual(bad3["broken_line"], 5)

    def test_prometheus_renderer(self):
        out = hubsec.render_prometheus_metrics({
            "uptime_seconds": 42,
            "inventory_counts": {"iran": 1, "node": 2},
            "overview_cache": {
                "rp01": {"role": "iran", "reachable": True, "nodes": [{"name": "de01"}]},
                "de01": {"role": "node", "reachable": True, "services": [{"name": "s1"}], "backhaul_services": []},
            },
            "drift_summary": {"error": 1, "warning": 2, "info": 0},
            "audit_total": 5,
            "login_failures_total": 3,
            "http_requests_by_method": {"GET": 10, "POST": 4, "PUT": 0, "DELETE": 1},
        })
        self.assertIn("# HELP ratholehub_up", out)
        self.assertIn("# TYPE ratholehub_up gauge", out)
        self.assertIn('ratholehub_server_nodes_total{server="rp01"} 1', out)
        self.assertIn('ratholehub_drift_issues_total{severity="error"} 1', out)
        self.assertIn('ratholehub_http_requests_total{method="POST"} 4', out)


class TestM3HubCmdsUndo(unittest.TestCase):
    def test_state_history_and_undo_commands(self):
        self.assertEqual(hubcmds.build_iran_cmd("state_history", {}), ["ratholectl", "history", "--json"])
        self.assertEqual(hubcmds.build_iran_cmd("state_undo_dry_run", {"rev": 2}), ["ratholectl", "undo", "--dry-run", "2"])
        self.assertEqual(hubcmds.build_iran_cmd("state_undo", {"rev": "1"}), ["ratholectl", "undo", "1"])
        self.assertEqual(hubcmds.build_iran_cmd("state_undo", {}), ["ratholectl", "undo", "1"])

        self.assertNotIn("state_history", hubcmds.WRITE_ACTIONS)
        self.assertNotIn("state_undo_dry_run", hubcmds.WRITE_ACTIONS)
        self.assertIn("state_undo", hubcmds.WRITE_ACTIONS)

        for bad in ("../1", "-1", "abc", "0", "21"):
            self.assertIsNone(hubcmds.build_iran_cmd("state_undo", {"rev": bad}), bad)
            self.assertIsNone(hubcmds.build_iran_cmd("state_undo_dry_run", {"rev": bad}), bad)


class TestM3HubSecurityHttp(unittest.TestCase):
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
        self.tok = "test_m3_admin_token_abcdef123456"
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

    def _raw(self, method, path, body=None, headers=None, token=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            hdrs = {"Content-Type": "application/json"}
            if token is not None:
                hdrs["Authorization"] = f"Bearer {token}"
            if headers:
                hdrs.update(headers)
            raw = json.dumps(body).encode("utf-8") if body is not None else None
            conn.request(method, path, body=raw, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8", errors="replace")
            return resp.status, dict(resp.getheaders()), data
        finally:
            conn.close()

    def _json(self, method, path, body=None, headers=None, token=None):
        st, hdrs, data = self._raw(method, path, body=body, headers=headers, token=token)
        return st, hdrs, (json.loads(data) if data else {})

    def test_scoped_tokens_and_rbac(self):
        st_ro, _, res_ro = self._json("POST", "/api/tokens", {"name": "prom", "scope": "read"}, token=self.tok)
        self.assertEqual(st_ro, 201)
        ro_tok = res_ro["token"]
        ro_id = res_ro["record"]["id"]
        self.assertTrue(ro_tok.startswith("rht_"))
        self.assertNotIn("sha256", res_ro["record"])

        st_op, _, res_op = self._json("POST", "/api/tokens", {"name": "ops", "scope": "operate"}, token=self.tok)
        self.assertEqual(st_op, 201)
        op_tok = res_op["token"]

        st_ls, _, ls = self._json("GET", "/api/tokens", token=self.tok)
        self.assertEqual(st_ls, 200)
        self.assertEqual(len(ls["tokens"]), 2)
        for item in ls["tokens"]:
            self.assertNotIn("token", item)
            self.assertNotIn("sha256", item)

        # Read token permissions
        for ep in ("/metrics", "/hub/metrics", "/api/servers", "/api/fleet/drift", "/api/audit/verify"):
            st, _, _ = self._raw("GET", ep, token=ro_tok)
            self.assertEqual(st, 200, ep)
        self.assertEqual(self._json("POST", "/api/servers/rp01/link-test", {"node": "trk01", "count": 2}, token=ro_tok)[0], 200)
        self.assertEqual(self._json("POST", "/api/servers/rp01/action", {"action": "state_history"}, token=ro_tok)[0], 200)

        for ep in ("/api/servers/rp01/mainconnect", "/api/tokens", "/api/2fa/status", "/api/config"):
            st, _, _ = self._json("GET", ep, token=ro_tok)
            self.assertEqual(st, 403, ep)
        self.assertEqual(self._json("POST", "/api/servers/rp01/action", {"action": "state_undo", "args": {"rev": "1"}}, token=ro_tok)[0], 403)
        self.assertEqual(self._json("POST", "/api/servers", {"name": "x", "role": "node", "host": "1.2.3.4"}, token=ro_tok)[0], 403)

        # Operate token permissions
        self.assertEqual(self._json("GET", "/api/servers/rp01/mainconnect", token=op_tok)[0], 200)
        self.assertEqual(self._json("POST", "/api/servers/rp01/action", {"action": "state_undo", "args": {"rev": "1"}}, token=op_tok)[0], 200)
        self.assertEqual(self._json("POST", "/api/servers", {"name": "x", "role": "node", "host": "1.2.3.4"}, token=op_tok)[0], 403)
        self.assertEqual(self._json("GET", "/api/tokens", token=op_tok)[0], 403)

        # Revoke read token -> 401 afterward; unknown token id -> 404
        self.assertEqual(self._json("DELETE", f"/api/tokens/{ro_id}", token=self.tok)[0], 200)
        self.assertEqual(self._raw("GET", "/metrics", token=ro_tok)[0], 401)
        self.assertEqual(self._json("DELETE", "/api/tokens/tok_000000000000", token=self.tok)[0], 404)

    def test_cookie_csrf_protection(self):
        st, hdrs, _ = self._json("POST", "/api/login", {"password": "pass1234"})
        self.assertEqual(st, 200)
        sc = hdrs.get("Set-Cookie") or hdrs.get("set-cookie") or ""
        cookie_val = sc.split(";", 1)[0]
        self.assertTrue(cookie_val.startswith("rhsession="))

        # Cross-site Origin blocked
        st_bad1, _, _ = self._json(
            "POST",
            "/api/servers/rp01/action",
            {"action": "state_history"},
            headers={"Cookie": cookie_val, "Origin": "https://evil.example"},
        )
        self.assertEqual(st_bad1, 403)

        # Sec-Fetch-Site: cross-site blocked
        st_bad2, _, _ = self._json(
            "POST",
            "/api/servers/rp01/action",
            {"action": "state_history"},
            headers={"Cookie": cookie_val, "Sec-Fetch-Site": "cross-site"},
        )
        self.assertEqual(st_bad2, 403)

        # Same-origin allowed
        st_ok, _, _ = self._json(
            "POST",
            "/api/servers/rp01/action",
            {"action": "state_history"},
            headers={"Cookie": cookie_val, "Origin": f"http://127.0.0.1:{self.port}"},
        )
        self.assertEqual(st_ok, 200)

    def test_2fa_full_http_lifecycle(self):
        self.assertFalse(self._json("GET", "/api/2fa/status", token=self.tok)[2]["enabled"])

        st_set, _, setup = self._json("POST", "/api/2fa/setup", {}, token=self.tok)
        self.assertEqual(st_set, 200)
        secret = setup["secret"]
        self.assertTrue(setup["otpauth_uri"].startswith("otpauth://totp/"))

        enable_code = hubsec.totp_code(secret, for_time=time.time())
        st_en, _, en = self._json("POST", "/api/2fa/enable", {"code": enable_code}, token=self.tok)
        self.assertEqual(st_en, 200)
        rec_codes = en["recovery_codes"]
        self.assertEqual(len(rec_codes), 8)

        status = self._json("GET", "/api/2fa/status", token=self.tok)[2]
        self.assertTrue(status["enabled"])
        self.assertEqual(status["recovery_remaining"], 8)
        self.assertTrue(self._json("GET", "/api/config", token=self.tok)[2]["totp_enabled"])

        # Password without TOTP -> totp_required
        st_req, _, d_req = self._json("POST", "/api/login", {"password": "pass1234"})
        self.assertEqual(st_req, 401)
        self.assertTrue(d_req["totp_required"])
        self.assertEqual(d_req["error"], "totp_required")

        # Bad TOTP -> bad totp
        st_bad, _, d_bad = self._json("POST", "/api/login", {"password": "pass1234", "totp": "000000"})
        self.assertEqual(st_bad, 401)
        self.assertTrue(d_bad["totp_required"])
        self.assertEqual(d_bad["error"], "bad totp")

        # Replay of exact step used in enable -> rejected
        st_rep, _, _ = self._json("POST", "/api/login", {"password": "pass1234", "totp": enable_code})
        self.assertEqual(st_rep, 401)

        # Single-use recovery code works once
        hub._LOGIN_FAILS.clear()
        st_rec1, _, _ = self._json("POST", "/api/login", {"password": "pass1234", "totp": rec_codes[0]})
        self.assertEqual(st_rec1, 200)
        self.assertEqual(self._json("GET", "/api/2fa/status", token=self.tok)[2]["recovery_remaining"], 7)

        st_rec_reuse, _, _ = self._json("POST", "/api/login", {"password": "pass1234", "totp": rec_codes[0]})
        self.assertEqual(st_rec_reuse, 401)

        # Disable 2FA using password + second recovery code
        st_dis, _, _ = self._json("POST", "/api/2fa/disable", {"password": "pass1234", "code": rec_codes[1]}, token=self.tok)
        self.assertEqual(st_dis, 200)
        self.assertFalse(self._json("GET", "/api/2fa/status", token=self.tok)[2]["enabled"])

        hub._LOGIN_FAILS.clear()
        self.assertEqual(self._json("POST", "/api/login", {"password": "pass1234"})[0], 200)

    def test_audit_chain_verify_and_metrics_http(self):
        self._json("POST", "/api/tokens", {"name": "m3-prom", "scope": "read"}, token=self.tok)
        self._json("GET", "/api/servers/rp01/overview", token=self.tok)
        self._json("GET", "/api/fleet/drift", token=self.tok)

        st_v, _, ver = self._json("GET", "/api/audit/verify", token=self.tok)
        self.assertEqual(st_v, 200)
        self.assertTrue(ver["ok"])
        self.assertGreaterEqual(ver["chained"], 1)
        self.assertIsNone(ver["broken_line"])

        st_m, hdrs, m_body = self._raw("GET", "/metrics", token=self.tok)
        self.assertEqual(st_m, 200)
        ctype = hdrs.get("Content-Type") or hdrs.get("content-type") or ""
        self.assertTrue(ctype.startswith("text/plain; version=0.0.4"), ctype)
        self.assertIn("ratholehub_up 1", m_body)
        self.assertIn('ratholehub_inventory_servers_total{role="iran"} 1', m_body)
        self.assertIn('ratholehub_server_nodes_total{server="rp01"}', m_body)
        self.assertIn("ratholehub_audit_entries_total", m_body)
        self.assertIn('ratholehub_http_requests_total{method="GET"}', m_body)

        # Tamper line 1 in audit.log and confirm verification catches it
        with open(self.audit, "r", encoding="utf-8") as f:
            raw_log = f.read()
        with open(self.audit, "w", encoding="utf-8") as f:
            f.write(raw_log.replace("token_create", "token_tamper", 1))

        st_v2, _, ver2 = self._json("GET", "/api/audit/verify", token=self.tok)
        self.assertEqual(st_v2, 200)
        self.assertFalse(ver2["ok"])
        self.assertEqual(ver2["broken_line"], 1)


if __name__ == "__main__":
    unittest.main()
