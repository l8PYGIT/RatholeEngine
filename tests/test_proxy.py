import unittest
import os, sys, json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../rathole-manager/ratholehub")))
import hub

class TestProxy(unittest.TestCase):
    def test_get_proxy_global_and_server_override(self):
        with patch.object(hub, 'get_config', return_value={"proxy": "socks5://127.0.0.1:10808"}):
            self.assertEqual(hub.get_proxy({"name": "srv1"}), "socks5://127.0.0.1:10808")
            self.assertEqual(hub.get_proxy({"name": "srv2", "proxy": "http://127.0.0.1:7890"}), "http://127.0.0.1:7890")
            self.assertEqual(hub.get_proxy({"name": "srv3", "proxy": "direct"}), "")

    def test_ssh_base_includes_proxy_command(self):
        with patch.object(hub, 'get_config', return_value={"proxy": "socks5://127.0.0.1:10808", "ssh_opts": []}):
            server = {"name": "node1", "host": "198.51.100.1", "ssh_port": 22, "ssh_user": "root"}
            ssh_cmd = hub._ssh_base(hub.get_config(), server)
            proxy_opts = [arg for arg in ssh_cmd if "ProxyCommand=" in arg]
            self.assertTrue(len(proxy_opts) > 0, "ProxyCommand must be present in SSH arguments when proxy configured")
            self.assertIn("ssh_proxy.py", proxy_opts[0])

if __name__ == "__main__":
    unittest.main()
