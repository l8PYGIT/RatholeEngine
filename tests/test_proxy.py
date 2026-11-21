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

    def test_proxy_and_ssh_opts_injection_rejected(self):
        handler = object.__new__(hub.Handler)
        handler._send = lambda code, body: (code, body)
        handler._user = lambda: "127.0.0.1"

        with patch.object(hub, "get_inventory", side_effect=lambda: []), \
             patch.object(hub, "set_inventory"), \
             patch.object(hub, "save_config"), \
             patch.object(hub, "audit_log"):
            for bad_proxy in [
                'socks5://127.0.0.1:1080";id;#',
                'http://$(id):8080',
                'http://127.0.0.1:8080\nProxyCommand=id',
                'ftp://127.0.0.1:21',
            ]:
                with self.subTest(bad_proxy=bad_proxy):
                    code, _ = handler._add_server({
                        "name": "evil", "role": "node", "host": "198.51.100.2",
                        "proxy": bad_proxy,
                    })
                    self.assertEqual(code, 400)
                    with patch.object(hub, "get_config", return_value={"proxy": "", "ssh_opts": []}):
                        code2, _ = handler._config_save({"proxy": bad_proxy})
                        self.assertEqual(code2, 400)
                    with self.assertRaises(ValueError):
                        hub._ssh_base({"ssh_opts": []}, {"name": "n1", "host": "198.51.100.2", "proxy": bad_proxy})

            for bad_opts in [
                ["-o", "ProxyCommand=id"],
                ["-oProxyCommand=id"],
                ["-o", "PermitLocalCommand=yes"],
                ["-o", "LocalCommand=id"],
                ["-F", "/tmp/evil_ssh_config"],
            ]:
                with self.subTest(bad_opts=bad_opts):
                    with patch.object(hub, "get_config", return_value={"proxy": "", "ssh_opts": []}):
                        code, _ = handler._config_save({"ssh_opts": bad_opts})
                        self.assertEqual(code, 400)

            for bad_key in ["/etc/passwd", "/etc/ratholehub/../shadow", "relative/id_ed25519", "/etc/ratholehub/key\nBad"]:
                with self.subTest(bad_key=bad_key):
                    with patch.object(hub, "get_config", return_value={"proxy": "", "ssh_opts": []}):
                        code, _ = handler._config_save({"ssh_key_path": bad_key})
                        self.assertEqual(code, 400)

    def test_ssh_base_uses_shlex_quote_for_proxy_command(self):
        cfg = {"ssh_opts": ["-o", "BatchMode=yes"]}
        srv = {"name": "node1", "host": "198.51.100.1", "ssh_port": 22, "ssh_user": "root", "proxy": "socks5://127.0.0.1:10808"}
        cmd = hub._ssh_base(cfg, srv)
        proxy_opt = [a for a in cmd if a.startswith("ProxyCommand=")][0]
        self.assertNotIn('"socks5://', proxy_opt)
        self.assertIn("socks5://127.0.0.1:10808", proxy_opt)

if __name__ == "__main__":
    unittest.main()
