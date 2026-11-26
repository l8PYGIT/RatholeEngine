import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HUB_DIR = Path(__file__).resolve().parents[1] / "rathole-manager" / "ratholehub"
sys.path.insert(0, str(HUB_DIR))

import hub  # noqa: E402
import hubcmds  # noqa: E402


class _FakeHandler:
    def __init__(self, servers):
        self._servers = servers
        self.sent = None

    def _find(self, name):
        for s in self._servers:
            if s.get("name") == name:
                return s
        return None

    def _send(self, code, payload):
        self.sent = (code, payload)
        return payload


class PortManagerHubTests(unittest.TestCase):
    def test_port_actions_allowlist_and_validation(self):
        self.assertEqual(hubcmds.build_iran_cmd("port_ls", {}), ["ratholectl", "port", "ls", "--json"])
        self.assertEqual(hubcmds.build_iran_cmd("port_map", {}), ["ratholectl", "port", "map", "--json"])
        self.assertEqual(hubcmds.build_iran_cmd("port_show", {"name": "p2083"}), ["ratholectl", "port", "show", "p2083"])
        self.assertEqual(hubcmds.build_iran_cmd("port_rm", {"name": "p2083"}), ["ratholectl", "port", "rm", "p2083", "--json"])

        for w in ("port_add", "port_edit", "port_rm"):
            self.assertIn(w, hubcmds.WRITE_ACTIONS)

        cmd = hubcmds.build_iran_cmd("port_add", {
            "public_port": "2080-2085",
            "inbound": "same",
            "proto": "tcp",
            "transport": "frp",
            "proxy_protocol": True,
            "name": "rng",
            "node_server": "de01",
            "note": "کانفیگ VLESS (فوری)",
        })
        self.assertEqual(
            cmd,
            [
                "ratholectl", "port", "add", "2080-2085", "same",
                "--proto", "tcp", "--transport", "frp",
                "--name", "rng", "--proxy-protocol",
                "--node-server", "de01", "--note", "کانفیگ VLESS (فوری)", "--json",
            ],
        )

        # Compatibility & security rejections
        self.assertIsNone(hubcmds.build_iran_cmd("port_add", {"public_port": "2083", "inbound": "443", "proto": "udp", "transport": "backhaul"}))
        self.assertIsNone(hubcmds.build_iran_cmd("port_add", {"public_port": "2083", "inbound": "443", "proto": "both", "proxy_protocol": True}))
        self.assertIsNone(hubcmds.build_iran_cmd("port_add", {"public_port": "2080-2100", "inbound": "443"}))  # >20 ports
        self.assertIsNone(hubcmds.build_iran_cmd("port_add", {"public_port": "2083,2083", "inbound": "443"}))  # dup CSV
        self.assertIsNone(hubcmds.build_iran_cmd("port_add", {"public_port": "2083;id", "inbound": "443"}))
        self.assertIsNone(hubcmds.build_iran_cmd("port_add", {"public_port": "2083", "inbound": "443", "note": "bad;rm -rf"}))
        self.assertIsNone(hubcmds.build_iran_cmd("port_add", {"public_port": "2083", "inbound": "443", "proto": "both", "name": "a" * 37}))
        self.assertIsNone(hubcmds.build_iran_cmd("port_edit", {"name": "p2083"}))  # no change

        # Clear optional note / node_server safely
        edit_cmd = hubcmds.build_iran_cmd("port_edit", {
            "name": "p2083",
            "inbound": 8443,
            "proxy_protocol": False,
            "node_server": "",
            "note": "",
        })
        self.assertEqual(
            edit_cmd,
            [
                "ratholectl", "port", "edit", "p2083",
                "--inbound", "8443", "--proxy-protocol", "off",
                "--node-server", "none", "--note", "", "--json",
            ],
        )

        # Node add_svc proto support
        self.assertEqual(
            hubcmds.build_node_cmd("add_svc", {"name": "u8448", "token": "a" * 32, "inbound": 8448, "proto": "udp"}),
            ["ratholenode", "add-svc", "u8448", "a" * 32, "8448", "udp"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd("add_svc", {"name": "f9003", "token": "a" * 32, "inbound": 443, "remote_port": 9003, "proto": "both"}),
            ["ratholenode", "add-svc", "f9003", "a" * 32, "443", "9003", "both"],
        )
        self.assertIsNone(hubcmds.build_node_cmd("add_svc", {"name": "u1", "token": "a" * 32, "inbound": 8448, "proto": "icmp"}))

    def test_hub_portconnect_overview_and_mock(self):
        iran_srv = {"name": "iran01", "role": "iran", "host": "5.202.4.40"}
        node_srv = {"name": "trk01", "role": "node", "host": "198.51.100.5"}

        ov = hub.collect_server_overview(iran_srv) if hub.MOCK else None
        # Test explicit mock_run behavior regardless of global MOCK flag
        st_mock = hub.mock_run(iran_srv, ["ratholectl", "status", "--json"])
        st_data = json.loads(st_mock["out"])
        self.assertIn("port_rules", st_data)
        self.assertIn("port_map", st_data)
        self.assertTrue(all("token" not in r for r in st_data["port_rules"]))

        add_mock = json.loads(hub.mock_run(iran_srv, [
            "ratholectl", "port", "add", "2090-2091", "same", "--proto", "udp", "--transport", "kcp", "--json",
        ])["out"])
        self.assertTrue(add_mock["ok"])
        self.assertEqual([x["public_port"] for x in add_mock["created"]], [2090, 2091])

        with patch.object(hub, "run_on_server", side_effect=lambda s, cmd: hub.mock_run(s, cmd)):
            ov2 = hub.collect_server_overview(iran_srv)
            self.assertEqual(len(ov2["port_rules"]), 3)
            self.assertGreaterEqual(len(ov2["port_map"]), 5)

            h = _FakeHandler([iran_srv, node_srv])
            res = hub.Handler._portconnect(h, "iran01", "p2053")
            self.assertEqual(h.sent[0], 200)
            self.assertTrue(res["ok"])
            self.assertEqual(res["transport"], "backhaul")
            self.assertEqual(res["remote_port"], 21000)

            hub.Handler._portconnect(h, "trk01", "p2053")
            self.assertEqual(h.sent[0], 400)

            hub.Handler._portconnect(h, "iran01", "bad;cmd")
            self.assertEqual(h.sent[0], 400)


if __name__ == "__main__":
    unittest.main()
