#!/usr/bin/env python3
"""test_hub.py — task 8: barresi build_node_cmd adaptive allow-list + input validation"""
import sys, os, unittest, importlib.util, types
from unittest import mock

# ---- hub.py ra load mikonim bedoon ajra-ye main ----
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HUB_PATH = os.path.join(REPO_ROOT, "rathole-manager", "ratholehub", "hub.py")

def _load_hub():
    hub_dir = os.path.dirname(HUB_PATH)
    # hub.py doostat module-haye hamsaye (mesle hubcmds) ra ba sys.path-e khod peida konad
    if hub_dir not in sys.path:
        sys.path.insert(0, hub_dir)
    spec = importlib.util.spec_from_file_location("hub", HUB_PATH)
    mod = importlib.util.module_from_spec(spec)
    # stub environment so hub doesn't try to read config files
    import io
    os.environ.setdefault("RATHOLEHUB_MOCK", "1")
    os.environ.setdefault("RATHOLEHUB_CONF", "/dev/null")
    os.environ.setdefault("RATHOLEHUB_INV",  "/dev/null")
    spec.loader.exec_module(mod)
    return mod

hub = _load_hub()
build_node_cmd = hub.build_node_cmd
WRITE_ACTIONS  = hub.WRITE_ACTIONS


class TestAdaptiveAllowList(unittest.TestCase):

    # --- adaptive_off: bedoon arg ---
    def test_adaptive_off_no_args(self):
        self.assertEqual(build_node_cmd("adaptive_off", {}),
                         ["ratholenode", "adaptive", "off"])

    # --- adaptive_status: read-only ---
    def test_adaptive_status(self):
        self.assertEqual(build_node_cmd("adaptive_status", {}),
                         ["ratholenode", "adaptive", "status"])

    # --- adaptive_test: --json bayad ezafe shavad ---
    def test_adaptive_test_json(self):
        self.assertEqual(build_node_cmd("adaptive_test", {}),
                         ["ratholenode", "adaptive", "test", "--json"])

    # --- adaptive_on: motabar ---
    def test_adaptive_on_valid(self):
        self.assertEqual(
            build_node_cmd("adaptive_on", {"interval": "30", "failures": "3", "recoveries": "5"}),
            ["ratholenode", "adaptive", "on", "--interval", "30", "--failures", "3", "--recoveries", "5"],
        )

    # --- adaptive_on: injection dar interval ---
    def test_adaptive_on_injection_interval(self):
        self.assertIsNone(build_node_cmd("adaptive_on", {"interval": "30;id", "failures": "3", "recoveries": "5"}))

    # --- adaptive_on: injection dar failures ---
    def test_adaptive_on_injection_failures(self):
        self.assertIsNone(build_node_cmd("adaptive_on", {"interval": "30", "failures": "3$(id)", "recoveries": "5"}))

    # --- adaptive_on: meghdar-e ghayr-adadi ---
    def test_adaptive_on_non_numeric(self):
        self.assertIsNone(build_node_cmd("adaptive_on", {"interval": "abc", "failures": "3", "recoveries": "5"}))

    # --- adaptive_on: khaali (default-ha lazem ast) ---
    def test_adaptive_on_defaults(self):
        cmd = build_node_cmd("adaptive_on", {})
        # bayad default-ha ra estefade konad (30, 3, 5)
        self.assertIsNotNone(cmd)
        self.assertIn("--interval", cmd)
        self.assertIn("30", cmd)

    # --- adaptive_off dar WRITE_ACTIONS ast ---
    def test_adaptive_off_in_write_actions(self):
        self.assertIn("adaptive_off", WRITE_ACTIONS)

    # --- adaptive_on dar WRITE_ACTIONS ast ---
    def test_adaptive_on_in_write_actions(self):
        self.assertIn("adaptive_on", WRITE_ACTIONS)

    # --- adaptive_status NIST dar WRITE_ACTIONS (read-only) ---
    def test_adaptive_status_not_in_write_actions(self):
        self.assertNotIn("adaptive_status", WRITE_ACTIONS)

    # --- adaptive_test NIST dar WRITE_ACTIONS ---
    def test_adaptive_test_not_in_write_actions(self):
        self.assertNotIn("adaptive_test", WRITE_ACTIONS)

    # --- JSON namotabar bayad field-e amn bargardanad ---
    def test_parse_adaptive_state_malformed(self):
        """parse_adaptive_state (agar vojood darad) bayad baraye JSON namotabar safe bemanad"""
        if hasattr(hub, "parse_adaptive_state"):
            result = hub.parse_adaptive_state("not-json")
            self.assertIsNotNone(result)
            # nabayad exception biahandazad va nabayad field-e makhfi dashte bashad
            self.assertNotIn("WS_PATH", str(result))
        else:
            # tabe vojood nadarad hanooz — skip mikonim
            self.skipTest("parse_adaptive_state hanooz piade nashode (Task 8 step 2)")

    # --- hich field-e makhfi az adaptive_test CMD pass nemishavad ---
    def test_no_secret_in_adaptive_test_cmd(self):
        cmd = build_node_cmd("adaptive_test", {"WS_PATH": "/_rh/secret", "token": "abc"})
        self.assertIsNotNone(cmd)
        self.assertNotIn("/_rh/secret", cmd)
        self.assertNotIn("abc", cmd)


class TestParseIranLs(unittest.TestCase):
    """parse_iran_ls bayad transport/sni-e sotoon-haye jadid ra begirad va ba
    khorooji-ye CLI-e ghadimi (bedoon-e in do sotoon) ham sazgar bemanad."""

    NEW = ("NAME           PORT     INBOUND      API        TRANSPORT  SNI              USER PATH\n"
           "--------------------------------------------------------------------------------\n"
           "trk01          1005     8444         -          backhaul   -                https://d/trk01\n"
           "trk02          1006     8445         9001       ws         -                https://d/trk02\n"
           "gamenode       1007     8446         -          ws         gmtrk.l1t.ir     https://d/gamenode\n"
           "noisenode      1008     8447         -          noise      -                https://d/noisenode\n")
    OLD = ("NAME           PORT     INBOUND      API        USER PATH\n"
           "--------------------------------------------------------------\n"
           "trk01          1005     8444         -          https://d/trk01\n")

    def _by_name(self, nodes):
        return {n["name"]: n for n in nodes}

    def test_new_format_transport_sni(self):
        nm = self._by_name(hub.parse_iran_ls(self.NEW))
        self.assertEqual(len(nm), 4)
        self.assertEqual(nm["trk01"]["transport"], "backhaul")
        # transport-e 'ws' = pishfarz → None (ta iranNodeMode ba noise/game eshtebah nashavad)
        self.assertIsNone(nm["trk02"]["transport"])
        self.assertIsNone(nm["trk02"]["sni"])
        self.assertEqual(nm["noisenode"]["transport"], "noise")
        self.assertEqual(nm["gamenode"]["sni"], "gmtrk.l1t.ir")
        self.assertEqual(nm["trk01"]["path"], "https://d/trk01")

    def test_old_format_still_parses(self):
        nm = self._by_name(hub.parse_iran_ls(self.OLD))
        self.assertEqual(len(nm), 1)
        self.assertEqual(nm["trk01"]["path"], "https://d/trk01")
        # CLI-e ghadimi transport/sni nadarad — nabayad KeyError bedahad
        self.assertIsNone(nm["trk01"].get("transport"))


class TestIranPerNodeActions(unittest.TestCase):
    """action-hayi ke select-e per-node-e Iran seda mizanad bayad dar allow-list
    bashand، argv-e dorost besazand va tazrigh-e name ra rad konand."""

    def test_per_node_actions_map_and_write(self):
        for act in ("noise_node_on", "noise_node_off",
                    "backhaul_node_on", "backhaul_node_off", "regen_full"):
            cmd = hub.build_iran_cmd(act, {"name": "trk02"})
            self.assertIsNotNone(cmd, act)
            if act != "regen_full":
                self.assertIn(act in WRITE_ACTIONS, (True,), act)

    def test_per_node_name_injection_rejected(self):
        for act in ("noise_node_on", "backhaul_node_on"):
            self.assertIsNone(hub.build_iran_cmd(act, {"name": "trk02; rm -rf /"}))
            self.assertIsNone(hub.build_iran_cmd(act, {"name": "trk02\n"}))


class TestIpAndBackhaulModes(unittest.TestCase):
    def test_set_main_ip_with_sni(self):
        self.assertEqual(build_node_cmd("set_main", {"server": "1.2.3.4:443", "tls_hostname": "edge.example.com"}),
                         ["ratholenode", "set-main", "1.2.3.4:443", "edge.example.com"])

    def test_set_main_ip_with_self_signed_root(self):
        self.assertEqual(
            build_node_cmd("set_main", {"server": "1.2.3.4:443", "tls_hostname": "1.2.3.4",
                                        "tls_trusted_root": "/etc/rathole/ip-root-ca.crt"}),
            ["ratholenode", "set-main", "1.2.3.4:443", "1.2.3.4", "/etc/rathole/ip-root-ca.crt"],
        )

    def test_set_main_rejects_injection(self):
        self.assertIsNone(build_node_cmd("set_main", {"server": "1.2.3.4:443;id", "tls_hostname": "edge.example.com"}))
        self.assertIsNone(build_node_cmd("set_main", {"server": "1.2.3.4:443", "tls_hostname": "x;id"}))
        self.assertIsNone(build_node_cmd("set_main", {"server": "1.2.3.4:443", "tls_hostname": "1.2.3.4",
                                                        "tls_trusted_root": "/etc/rathole/ca.crt;id"}))
        self.assertIsNone(build_node_cmd("set_main", {"server": "1.2.3.4:443", "tls_trusted_root": "/etc/rathole/ca.crt"}))

    def test_backhaul_direct_ip(self):
        tok = "a" * 40
        base = {"mode": "direct_ip", "remote_addr": "1.2.3.4:3080", "token": tok, "profile": "balanced"}
        # direct-IP: har chahar transport mojaz — ws/wsmux bedoon-e ramz، wss/wssmux ba
        # gvahi-ye self-signed-e samt-e Iran (client-e backhaul an ra verify nemikonad).
        for tr in ("ws", "wsmux", "wss", "wssmux"):
            self.assertEqual(build_node_cmd("backhaul_on", dict(base, transport=tr)),
                             ["ratholenode", "backhaul", "on", "1.2.3.4:3080", tok, tr, "balanced"])
        # endpoint-e direct HATMAN bayad host:port-e sarih bashad (domain-e bedoon port rad mishavad)
        self.assertIsNone(build_node_cmd("backhaul_on", dict(base, remote_addr="d.example", transport="wssmux")))
        # nginx_tls: client be nginx:443 mizanad → faghat variant-e TLS-dar
        self.assertIsNone(build_node_cmd("backhaul_on", {"mode": "nginx_tls", "domain": "d.example",
                                                          "token": tok, "transport": "wsmux", "profile": "balanced"}))

    def test_iran_backhaul_mode(self):
        # direct-IP: server khodesh TLS ra terminate mikonad، pas wss/wssmux ham mojaz ast.
        for tr in ("ws", "wsmux", "wss", "wssmux"):
            self.assertEqual(hub.build_iran_cmd("backhaul_on", {"port": "3080", "transport": tr,
                                                                 "profile": "balanced", "mode": "direct_ip"}),
                             ["ratholectl", "backhaul", "on", "3080", tr, "balanced", "direct_ip"])
        # nginx_tls: nginx TLS ra terminate mikonad → server HATMAN bedoon-e TLS
        self.assertEqual(hub.build_iran_cmd("backhaul_on", {"port": "3080", "transport": "wsmux",
                                                             "profile": "balanced", "mode": "nginx_tls"}),
                         ["ratholectl", "backhaul", "on", "3080", "wsmux", "balanced", "nginx_tls"])
        for tr in ("wss", "wssmux"):
            self.assertIsNone(hub.build_iran_cmd("backhaul_on", {"port": "3080", "transport": tr,
                                                                  "profile": "balanced", "mode": "nginx_tls"}))
        # direct-IP rooye 443 ba nginx tadakhol darad
        self.assertIsNone(hub.build_iran_cmd("backhaul_on", {"port": "443", "transport": "wsmux",
                                                              "profile": "balanced", "mode": "direct_ip"}))


class TestPrepareIpTls(unittest.TestCase):
    def _handler(self, inventory):
        handler = object.__new__(hub.Handler)
        handler._find = lambda name: next((s for s in inventory if s["name"] == name), None)
        handler._user = lambda: "test"
        handler._send = lambda code, body: {"status": code, "body": body}
        return handler

    def test_prepare_keeps_private_key_on_iran(self):
        iran = {"name": "ir1", "role": "iran", "host": "1.2.3.4"}
        node = {"name": "n1", "role": "node", "host": "5.6.7.8"}
        calls = []

        def fake_run(server, cmd):
            calls.append((server["name"], cmd))
            if cmd[1] == "ip-cert-show":
                return {"rc": 0, "out": "-----BEGIN CERTIFICATE-----\nTU9DSw==\n-----END CERTIFICATE-----\n", "err": ""}
            return {"rc": 0, "out": "ok", "err": ""}

        put = types.SimpleNamespace(returncode=0, stderr="")
        with mock.patch.object(hub, "MOCK", False), \
             mock.patch.object(hub, "run_on_server", side_effect=fake_run), \
             mock.patch.object(hub, "get_config", return_value={}), \
             mock.patch.object(hub, "_ssh_base", return_value=["ssh", "node"]), \
             mock.patch.object(hub.subprocess, "run", return_value=put) as install, \
             mock.patch.object(hub, "audit_log"):
            res = self._handler([iran, node])._prepare_ip_tls({"iran": "ir1", "node": "n1"})

        self.assertEqual(res["status"], 200)
        self.assertTrue(res["body"]["ok"])
        self.assertEqual(res["body"]["tls_trusted_root"], "/etc/rathole/ip-root-ca.crt")
        self.assertNotIn("private", str(res["body"]).lower())
        self.assertEqual(calls, [("ir1", ["ratholectl", "ip-cert", "1.2.3.4"]),
                                 ("ir1", ["ratholectl", "ip-cert-show", "1.2.3.4"])])
        remote = install.call_args.args[0]
        self.assertEqual(remote[-6:], ["install", "-D", "-m", "0644", "/dev/stdin", "/etc/rathole/ip-root-ca.crt"])
        self.assertIn("BEGIN CERTIFICATE", install.call_args.kwargs["input"])

    def test_prepare_rejects_non_ip_inventory_host(self):
        iran = {"name": "ir1", "role": "iran", "host": "iran.example.com"}
        node = {"name": "n1", "role": "node", "host": "5.6.7.8"}
        with mock.patch.object(hub, "run_on_server") as remote:
            res = self._handler([iran, node])._prepare_ip_tls({"iran": "ir1", "node": "n1"})
        self.assertEqual(res["status"], 400)
        remote.assert_not_called()


class TestUpstreamLogsStatus(unittest.TestCase):
    """upstream logs/status: read-only node actions ta upstream-ha ghabel-e ayb-yabi bashand."""

    def test_upstream_logs_and_status_argv(self):
        self.assertEqual(build_node_cmd("upstream_logs", {"id": "iranviph"}),
                         ["ratholenode", "upstream", "logs", "iranviph"])
        self.assertEqual(build_node_cmd("upstream_status", {"id": "iranviph"}),
                         ["ratholenode", "upstream", "status", "iranviph"])

    def test_upstream_logs_status_injection_rejected(self):
        self.assertIsNone(build_node_cmd("upstream_logs", {"id": "a; rm -rf /"}))
        self.assertIsNone(build_node_cmd("upstream_status", {"id": "a\n"}))

    def test_upstream_logs_status_are_read_only(self):
        self.assertNotIn("upstream_logs", WRITE_ACTIONS)
        self.assertNotIn("upstream_status", WRITE_ACTIONS)


class TestUpstreamCarrier(unittest.TestCase):
    """hamel-e per-upstream: har upstream mesl-e tunnel-e asli ws/kcp/plain/noise darad."""

    def test_plain_argv(self):
        self.assertEqual(build_node_cmd("upstream_plain_on", {"id": "u1", "remote": "1.2.3.4:8880"}),
                         ["ratholenode", "upstream", "plain", "u1", "on", "1.2.3.4:8880"])
        self.assertEqual(build_node_cmd("upstream_plain_off", {"id": "u1"}),
                         ["ratholenode", "upstream", "plain", "u1", "off"])

    def test_noise_argv_and_pubkey_validation(self):
        pk = "A" * 44
        self.assertEqual(build_node_cmd("upstream_noise_on",
                                        {"id": "u1", "remote": "1.2.3.4:2334", "pubkey": pk}),
                         ["ratholenode", "upstream", "noise", "u1", "on", "1.2.3.4:2334", pk])
        # pubkey-e namotabar bayad rad shavad
        self.assertIsNone(build_node_cmd("upstream_noise_on",
                                         {"id": "u1", "remote": "1.2.3.4:2334", "pubkey": "x"}))

    def test_ws_reset_argv(self):
        self.assertEqual(build_node_cmd("upstream_ws", {"id": "u1"}),
                         ["ratholenode", "upstream", "ws", "u1"])

    def test_carrier_actions_reject_injection(self):
        for act in ("upstream_plain_off", "upstream_noise_off", "upstream_ws"):
            self.assertIsNone(build_node_cmd(act, {"id": "u1; rm -rf /"}))
        self.assertIsNone(build_node_cmd("upstream_plain_on",
                                         {"id": "u1", "remote": "1.2.3.4:80; id"}))

    def test_carrier_actions_are_writes(self):
        for act in ("upstream_plain_on", "upstream_plain_off",
                    "upstream_noise_on", "upstream_noise_off", "upstream_ws"):
            self.assertIn(act, WRITE_ACTIONS, act)


class TestDualCoreActions(unittest.TestCase):
    def test_backhaul_service_argv_and_write(self):
        tok = "a" * 40
        self.assertEqual(build_node_cmd("add_bh_svc", {"name": "bulk", "token": tok, "inbound": "1201"}),
                         ["ratholenode", "backhaul", "add-svc", "bulk", tok, "1201"])
        self.assertEqual(build_node_cmd("rm_bh_svc", {"name": "bulk"}),
                         ["ratholenode", "backhaul", "rm-svc", "bulk"])
        self.assertIn("add_bh_svc", WRITE_ACTIONS)
        self.assertIn("rm_bh_svc", WRITE_ACTIONS)

    def test_backhaul_service_rejects_injection(self):
        self.assertIsNone(build_node_cmd("add_bh_svc", {"name": "x;id", "token": "a" * 40, "inbound": "1201"}))
        self.assertIsNone(build_node_cmd("rm_bh_svc", {"name": "x\n"}))

    def test_backhaul_ls_cmd(self):
        self.assertEqual(build_node_cmd("backhaul_ls", {}), ["ratholenode", "backhaul", "ls"])

    def test_add_svc_with_remote_port(self):
        tok = "a" * 40
        self.assertEqual(build_node_cmd("add_svc", {"name": "bulk", "token": tok, "inbound": "1201", "remote_port": "1001"}),
                         ["ratholenode", "add-svc", "bulk", tok, "1201", "1001"])
        self.assertEqual(build_node_cmd("add_svc", {"name": "bulk", "token": tok, "inbound": "1201"}),
                         ["ratholenode", "add-svc", "bulk", tok, "1201"])
        self.assertIsNone(build_node_cmd("add_svc", {"name": "bulk", "token": tok, "inbound": "1201", "remote_port": "1001;rm"}))


class TestLoginRateLimit(unittest.TestCase):
    def setUp(self):
        hub.login_reset("1.2.3.4")
        hub.login_reset("test-client")
        hub.login_reset("new-ip")
        hub.login_reset("old-ip-1")
        hub.login_reset("old-ip-2")


    def test_login_rate_limit_blocks_after_max(self):
        ip = "1.2.3.4"
        for _ in range(5):
            self.assertTrue(hub.login_allowed(ip))
            hub.login_record_fail(ip)
        self.assertFalse(hub.login_allowed(ip))
        hub.login_reset(ip)
        self.assertTrue(hub.login_allowed(ip))

    def test_login_rate_limit_pruning(self):
        with hub._login_lock:
            # Insert expired entries
            hub._LOGIN_FAILS["old-ip-1"] = [100.0]
            hub._LOGIN_FAILS["old-ip-2"] = [200.0]
        # Calling login_allowed should prune expired keys
        self.assertTrue(hub.login_allowed("new-ip"))
        with hub._login_lock:
            self.assertNotIn("old-ip-1", hub._LOGIN_FAILS)
            self.assertNotIn("old-ip-2", hub._LOGIN_FAILS)


class TestIranPublicHostAndLs(unittest.TestCase):
    def test_iran_public_host_bypasses_loopback_with_fallback(self):
        server = {"name": "iran", "host": "127.0.0.1"}
        with mock.patch.object(hub, "run_on_server", return_value={"rc": 1, "out": ""}):
            res = hub.iran_public_host(server, fallback="45.234.54.9")
            self.assertEqual(res, "45.234.54.9")

    def test_iran_public_host_preserves_public_ip(self):
        server = {"name": "iran", "host": "198.51.100.5"}
        res = hub.iran_public_host(server, fallback="45.234.54.9")
        self.assertEqual(res, "198.51.100.5")

    def test_iran_public_host_queries_status_when_loopback_and_no_fallback(self):
        server = {"name": "iran", "host": "127.0.0.1"}
        with mock.patch.object(hub, "run_on_server") as mock_run:
            mock_run.return_value = {"rc": 0, "out": '{"public_ip":"45.234.54.9","domain":"iran.example.com"}'}
            res = hub.iran_public_host(server, fallback="127.0.0.1")
            self.assertEqual(res, "45.234.54.9")

    def test_iran_public_host_uses_reported_address_before_private_ssh_host(self):
        server = {"name": "iran", "host": "10.1.2.3"}
        with mock.patch.object(hub, "run_on_server", return_value={"rc": 0, "out": '{"public_ip":"45.234.54.9"}'}):
            self.assertEqual(hub.iran_public_host(server), "45.234.54.9")

    def test_iran_public_host_uses_manual_override(self):
        server = {"name": "iran", "host": "10.1.2.3", "public_ip": "45.234.54.10"}
        with mock.patch.object(hub, "run_on_server") as remote:
            self.assertEqual(hub.iran_public_host(server), "45.234.54.10")
            remote.assert_not_called()

    def test_iran_public_host_ignores_private_detected_ip_when_ssh_host_is_public(self):
        server = {"name": "iran", "host": "45.234.54.9"}
        with mock.patch.object(hub, "run_on_server", return_value={"rc": 0, "out": '{"public_ip":"10.1.2.3"}'}):
            self.assertEqual(hub.iran_public_host(server), "45.234.54.9")

    def test_parse_iran_ls_includes_inbound_port(self):
        text = "trknetlen 1001 1001 - ws - /"
        nodes = hub.parse_iran_ls(text)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["name"], "trknetlen")
        self.assertEqual(nodes[0]["inbound"], "1001")
        self.assertEqual(nodes[0]["inbound_port"], "1001")


if __name__ == "__main__":
    unittest.main(verbosity=2)


