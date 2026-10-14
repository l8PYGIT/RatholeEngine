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

if __name__ == "__main__":
    unittest.main()
