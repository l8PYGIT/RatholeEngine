import unittest, os, sys, json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../rathole-manager/ratholehub")))
import hub

class TestHubTransports(unittest.TestCase):
    @patch("hub.urllib.request.build_opener")
    def test_run_on_server_dispatches_to_api(self, mock_build_opener):
        mock_opener = MagicMock()
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"rc": 0, "out": "rathole 0.5.0", "err": ""}).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_opener.open.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        server = {
            "name": "api-node",
            "role": "node",
            "transport": "api",
            "api_url": "http://198.51.100.5:8089",
            "api_token": "secret123"
        }
        # isolate proxy configuration from other test modules and host files.
        with patch("hub.get_proxy", return_value=""):
            res = hub.run_on_server(server, ["ratholenode", "version"])
        self.assertEqual(res["rc"], 0)
        self.assertIn("rathole 0.5.0", res["out"])
        
        # Verify call made to correct URL
        args, kwargs = mock_opener.open.call_args
        req = args[0]
        self.assertEqual(req.full_url, "http://198.51.100.5:8089/api/exec")
        self.assertEqual(req.headers.get("Authorization"), "Bearer secret123")

    def test_build_agent_request_payload(self):
        server = {
            "name": "node-1",
            "transport": "api",
            "api_url": "http://1.2.3.4:8089",
            "api_token": "tok999"
        }
        req = hub.build_agent_request(server, ["ratholenode", "ls"], timeout=60)
        self.assertEqual(req.full_url, "http://1.2.3.4:8089/api/exec")
        self.assertEqual(req.headers.get("Authorization"), "Bearer tok999")
        data = json.loads(req.data.decode())
        self.assertEqual(data["cmd"], ["ratholenode", "ls"])
        self.assertEqual(data["timeout"], 60)

    def test_build_agent_request_auto_prepends_http(self):
        server = {
            "name": "node-schemeless",
            "transport": "api",
            "api_url": "198.51.100.10:7001",
            "api_token": "tok123"
        }
        req = hub.build_agent_request(server, ["ratholenode", "status"])
        self.assertEqual(req.full_url, "http://198.51.100.10:7001/api/exec")

    def test_parse_carrier_statuses(self):
        # Backhaul
        bh_txt = "backhaul (SMUX core): roshan  backhaul-server ru-ye 127.0.0.1:3080\n  node-haye backhaul: trk01, trk02"
        bh = hub.parse_backhaul_status(bh_txt)
        self.assertTrue(bh["enabled"])
        self.assertEqual(bh["port"], "3080")
        self.assertEqual(bh["nodes"], ["trk01", "trk02"])

        # FRP
        frp_txt = "frp (fatedier core): roshan rooye port 7000 (tcp)"
        frp = hub.parse_frp_status(frp_txt)
        self.assertTrue(frp["enabled"])
        self.assertEqual(frp["port"], "7000")

        # GRE
        gre_txt = "gre (Linux L3): gre1 roshan va UP ast"
        gre = hub.parse_gre_status(gre_txt)
        self.assertTrue(gre["enabled"])
        self.assertEqual(gre["name"], "gre1")

    def test_hubcmds_frp_node_and_backhaul_nginx_port(self):
        from hubcmds import build_iran_cmd, build_node_cmd, WRITE_ACTIONS
        self.assertEqual(build_iran_cmd("frp_node_on", {"name": "trk01"}),
                         ["ratholectl", "frp", "node", "trk01", "on"])
        self.assertEqual(build_iran_cmd("frp_node_off", {"name": "trk01"}),
                         ["ratholectl", "frp", "node", "trk01", "off"])
        self.assertIn("frp_node_on", WRITE_ACTIONS)
        self.assertIn("frp_node_off", WRITE_ACTIONS)

        # backhaul on with domain:443 in nginx_tls mode
        cmd = build_node_cmd("backhaul_on", {
            "mode": "nginx_tls",
            "remote_addr": "viph.l8py.com:443",
            "token": "a" * 40,
            "transport": "wssmux",
            "profile": "balanced"
        })
        self.assertEqual(cmd, ["ratholenode", "backhaul", "on", "viph.l8py.com:443", "a" * 40, "wssmux", "balanced"])

if __name__ == "__main__":
    unittest.main()
