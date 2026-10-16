#!/usr/bin/env python3
"""test_hub_frp_gre.py — Unit tests for FRP Core and GRE Tunnel commands in hubcmds.py and hub.py"""
import sys, os, unittest, importlib.util

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HUB_PATH = os.path.join(REPO_ROOT, "rathole-manager", "ratholehub", "hub.py")

def _load_hub():
    hub_dir = os.path.dirname(HUB_PATH)
    if hub_dir not in sys.path:
        sys.path.insert(0, hub_dir)
    spec = importlib.util.spec_from_file_location("hub", HUB_PATH)
    mod = importlib.util.module_from_spec(spec)
    os.environ.setdefault("RATHOLEHUB_MOCK", "1")
    os.environ.setdefault("RATHOLEHUB_CONF", "/dev/null")
    os.environ.setdefault("RATHOLEHUB_INV",  "/dev/null")
    spec.loader.exec_module(mod)
    return mod

hub = _load_hub()
build_iran_cmd = hub.build_iran_cmd
build_node_cmd = hub.build_node_cmd
WRITE_ACTIONS  = hub.WRITE_ACTIONS
mock_run       = hub.mock_run

class TestFRPAndGREHubCmds(unittest.TestCase):
    def test_status_retains_protocol_and_does_not_match_inactive(self):
        for protocol in ('tcp', 'quic', 'kcp', 'websocket'):
            self.assertEqual(hub.parse_frp_status('halat tunnel: frp\n remote: 1.2.3.4:7000 transport: ' + protocol)['transport'], protocol)
            self.assertEqual(hub.parse_frp_status('FRP (reverse tunnel): roshan port 7000 (' + protocol + ')')['transport'], protocol)
        self.assertEqual(hub.parse_backhaul_status('backhaul client: active (transport=wssmux, profile=balanced)')['transport'], 'wssmux')
        self.assertFalse(hub.parse_backhaul_status('backhaul client: inactive')['enabled'])
        self.assertFalse(hub.parse_frp_status('frpc: inactive')['enabled'])

    def test_frp_iran_commands(self):
        self.assertEqual(build_iran_cmd("frp_status", {}), ["ratholectl", "frp", "status"])
        self.assertEqual(build_iran_cmd("frp_show", {}), ["ratholectl", "frp", "show"])
        self.assertEqual(build_iran_cmd("frp_off", {}), ["ratholectl", "frp", "off"])
        self.assertEqual(build_iran_cmd("frp_on", {"port": "7000", "token": "abcdef0123456789", "transport": "tcp"}),
                         ["ratholectl", "frp", "on", "7000", "abcdef0123456789", "tcp"])
        self.assertEqual(build_iran_cmd("frp_on", {"port": "7001", "transport": "quic"}),
                         ["ratholectl", "frp", "on", "7001", "quic"])
        # Validation checks
        self.assertIsNone(build_iran_cmd("frp_on", {"port": "7000;rm -rf /"}))
        self.assertIsNone(build_iran_cmd("frp_on", {"port": "7000", "transport": "invalid"}))
        for tr in ("tcp", "kcp", "quic", "websocket"):
            cmd = build_iran_cmd("frp_on", {"port": "7000", "token": "abcdef0123456789", "transport": tr})
            self.assertEqual(cmd, ["ratholectl", "frp", "on", "7000", "abcdef0123456789", tr])
        self.assertEqual(build_iran_cmd("frp_ready", {"name": "node1"}),
                         ["ratholectl", "frp", "ready", "node1"])

    def test_frp_node_commands(self):
        self.assertEqual(build_node_cmd("frp_status", {}), ["ratholenode", "frp", "status"])
        self.assertEqual(build_node_cmd("frp_off", {}), ["ratholenode", "frp", "off"])
        self.assertEqual(build_node_cmd("frp_on", {"remote": "5.202.4.40:7000", "token": "abcdef0123456789", "transport": "tcp"}),
                         ["ratholenode", "frp", "on", "5.202.4.40:7000", "abcdef0123456789", "tcp"])
        for tr in ("tcp", "kcp", "quic", "websocket"):
            cmd = build_node_cmd("frp_on", {"remote": "5.202.4.40:7000", "token": "abcdef0123456789", "transport": tr})
            self.assertEqual(cmd, ["ratholenode", "frp", "on", "5.202.4.40:7000", "abcdef0123456789", tr])
        # remote_port optional parameter
        self.assertEqual(build_node_cmd("frp_on", {"remote": "5.202.4.40:7000", "token": "abcdef0123456789", "transport": "tcp", "remote_port": "1001"}),
                         ["ratholenode", "frp", "on", "5.202.4.40:7000", "abcdef0123456789", "tcp", "1001"])
        # Validation checks
        self.assertIsNone(build_node_cmd("frp_on", {"remote": "bad-host", "token": "abcdef0123456789"}))
        self.assertIsNone(build_node_cmd("frp_on", {"remote": "5.202.4.40:7000", "token": "abcdef0123456789", "remote_port": "bad;port"}))

    def test_gre_iran_commands(self):
        self.assertEqual(build_iran_cmd("gre_status", {}), ["ratholectl", "gre", "status"])
        self.assertEqual(build_iran_cmd("gre_off", {}), ["ratholectl", "gre", "off"])
        self.assertEqual(build_iran_cmd("gre_off", {"name": "gre2"}), ["ratholectl", "gre", "off", "gre2"])
        self.assertEqual(build_iran_cmd("gre_on", {"remote_ip": "198.51.100.5", "tunnel_ip": "10.10.10.1", "name": "gre1"}),
                         ["ratholectl", "gre", "on", "198.51.100.5", "10.10.10.1", "gre1"])
        # Validation checks
        self.assertIsNone(build_iran_cmd("gre_on", {"remote_ip": "198.51.100.5;id"}))

    def test_gre_node_commands(self):
        self.assertEqual(build_node_cmd("gre_status", {}), ["ratholenode", "gre", "status"])
        self.assertEqual(build_node_cmd("gre_off", {}), ["ratholenode", "gre", "off"])
        self.assertEqual(build_node_cmd("gre_on", {"remote_ip": "5.202.4.40", "tunnel_ip": "10.10.10.2", "name": "gre1"}),
                         ["ratholenode", "gre", "on", "5.202.4.40", "10.10.10.2", "gre1"])
        # Validation checks
        self.assertIsNone(build_node_cmd("gre_on", {"remote_ip": "bad_ip"}))
        self.assertEqual(build_node_cmd("gre_probe", {"peer_ip": "10.10.10.1", "name": "gre1"}),
                         ["ratholenode", "gre", "probe", "10.10.10.1", "gre1"])

    def test_write_actions_contains_frp_and_gre(self):
        for act in ("frp_on", "frp_off", "gre_on", "gre_off"):
            self.assertIn(act, WRITE_ACTIONS)

    def test_mock_run_frp_and_gre(self):
        res_frp = mock_run({"role": "iran"}, ["ratholectl", "frp", "status"])
        self.assertEqual(res_frp["rc"], 0)
        self.assertIn("FRP (reverse tunnel)", res_frp["out"])

        res_gre = mock_run({"role": "iran"}, ["ratholectl", "gre", "status"])
        self.assertEqual(res_gre["rc"], 0)
        self.assertIn("GRE tunnel", res_gre["out"])

if __name__ == "__main__":
    unittest.main()
