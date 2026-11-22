#!/usr/bin/env python3
"""Unit tests for M1: deterministic fakeweb.py decoy server & hubcmds.py extensions."""

import http.client
import importlib.util
import os
import sys
import tempfile
import threading
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FAKEWEB_PATH = os.path.join(REPO_ROOT, "rathole-manager", "fakeweb.py")
HUBCMDS_PATH = os.path.join(REPO_ROOT, "rathole-manager", "ratholehub", "hubcmds.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fakeweb = _load("fakeweb", FAKEWEB_PATH)
hubcmds = _load("hubcmds", HUBCMDS_PATH)


class TestFakewebDecoy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.srv = fakeweb.create_server("127.0.0.1", 0, root=self.tmp.name, seed="node-alpha-secret")
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def _req(self, method, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, headers=headers or {})
            resp = conn.getresponse()
            body = resp.read()
            return resp.status, dict(resp.getheaders()), body
        finally:
            conn.close()

    def test_index_has_authentic_nginx_headers_and_no_python_banner(self):
        status, hdrs, body = self._req("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("nginx", hdrs.get("Server", "").lower())
        self.assertNotIn("Python", hdrs.get("Server", ""))
        self.assertNotIn("BaseHTTP", hdrs.get("Server", ""))
        self.assertIn("Last-Modified", hdrs)
        self.assertIn("ETag", hdrs)
        self.assertEqual(hdrs.get("Accept-Ranges"), "bytes")
        self.assertEqual(int(hdrs.get("Content-Length", "-1")), len(body))
        self.assertIn(b"Welcome to nginx!", body)

    def test_conditional_requests_return_304(self):
        _, hdrs, _ = self._req("GET", "/")
        etag = hdrs["ETag"]
        lmod = hdrs["Last-Modified"]

        status, h304, b304 = self._req("GET", "/", {"If-None-Match": etag})
        self.assertEqual(status, 304)
        self.assertEqual(b304, b"")
        self.assertEqual(h304["ETag"], etag)

        status2, _, b304_2 = self._req("GET", "/", {"If-Modified-Since": lmod})
        self.assertEqual(status2, 304)
        self.assertEqual(b304_2, b"")

    def test_head_and_range_requests(self):
        _, hdrs, full_body = self._req("GET", "/index.html")
        status_h, hdrs_h, body_h = self._req("HEAD", "/")
        self.assertEqual(status_h, 200)
        self.assertEqual(body_h, b"")
        self.assertEqual(int(hdrs_h["Content-Length"]), len(full_body))
        self.assertEqual(hdrs_h["ETag"], hdrs["ETag"])

        status_r, hdrs_r, body_r = self._req("GET", "/", {"Range": "bytes=0-14"})
        self.assertEqual(status_r, 206)
        self.assertEqual(body_r, full_body[:15])
        self.assertEqual(hdrs_r["Content-Range"], f"bytes 0-14/{len(full_body)}")

        status_416, hdrs_416, _ = self._req("GET", "/", {"Range": "bytes=999999-1000000"})
        self.assertEqual(status_416, 416)
        self.assertEqual(hdrs_416["Content-Range"], f"bytes */{len(full_body)}")

    def test_unknown_paths_including_channel_return_nginx_404_and_post_405(self):
        for p in ("/channel", "/tunnel", "/_rh/deadbeef", "/robots.txt"):
            st, hdrs, body = self._req("GET", p)
            self.assertEqual(st, 404)
            self.assertIn(b"404 Not Found", body)
            self.assertIn(hdrs["Server"].encode("utf-8"), body)

        st_post, _, body_post = self._req("POST", "/")
        self.assertEqual(st_post, 405)
        self.assertIn(b"405 Not Allowed", body_post)

    def test_identity_is_stable_across_restarts_and_differs_across_seeds(self):
        p1a = fakeweb.build_profile(root=self.tmp.name, seed="seed-one")
        p1b = fakeweb.build_profile(root=self.tmp.name, seed="seed-one")
        p2 = fakeweb.build_profile(root=self.tmp.name, seed="seed-two")
        self.assertEqual((p1a.server_banner, p1a.last_modified, p1a.etag), (p1b.server_banner, p1b.last_modified, p1b.etag))
        self.assertNotEqual((p1a.server_banner, p1a.last_modified, p1a.etag), (p2.server_banner, p2.last_modified, p2.etag))

    def test_custom_index_is_preserved_and_legacy_placeholder_ignored(self):
        idx = os.path.join(self.tmp.name, "index.html")
        with open(idx, "wb") as f:
            f.write(b"<!doctype html><html><head><title>Welcome</title></head><body><h1>It works!</h1><p>Default web page.</p></body></html>")
        p_leg = fakeweb.build_profile(root=self.tmp.name, seed="seed-one")
        self.assertIn(b"Welcome to nginx!", p_leg.body)

        with open(idx, "wb") as f:
            f.write(b"<html><body>Custom Landing Page</body></html>")
        p_custom = fakeweb.build_profile(root=self.tmp.name, seed="seed-one")
        self.assertEqual(p_custom.body, b"<html><body>Custom Landing Page</body></html>")

    def test_seed_file_auto_created_and_stable_and_trace_returns_nginx_error(self):
        seed_path = os.path.join(self.tmp.name, "sub", "fakeweb.seed")
        self.assertFalse(os.path.exists(seed_path))
        p_first = fakeweb.build_profile(root=self.tmp.name, seed_file=seed_path)
        self.assertTrue(os.path.isfile(seed_path))
        p_second = fakeweb.build_profile(root=self.tmp.name, seed_file=seed_path)
        self.assertEqual(
            (p_first.server_banner, p_first.last_modified, p_first.etag, p_first.body),
            (p_second.server_banner, p_second.last_modified, p_second.etag, p_second.body),
        )

        st, hdrs, body = self._req("TRACE", "/")
        self.assertEqual(st, 501)
        self.assertIn("nginx", hdrs.get("Server", "").lower())
        self.assertNotIn("Python", hdrs.get("Server", ""))
        self.assertNotIn("BaseHTTP", hdrs.get("Server", ""))
        self.assertNotIn(b"Python", body)
        self.assertNotIn(b"BaseHTTP", body)
        self.assertIn(b"501 Not Implemented", body)


class TestM1HubCmds(unittest.TestCase):
    def test_gre_ipv4_ipv6_key_mtu_and_validation(self):
        self.assertEqual(
            hubcmds.build_iran_cmd("gre_on", {"remote_ip": "198.51.100.5", "tunnel_ip": "10.10.10.1", "name": "gre1"}),
            ["ratholectl", "gre", "on", "198.51.100.5", "10.10.10.1", "gre1"],
        )
        self.assertEqual(
            hubcmds.build_iran_cmd("gre_on", {
                "remote_ip": "2001:db8::2",
                "tunnel_ip": "fd00::1",
                "name": "gre6",
                "gre_key": 41007,
                "mtu": 1420,
            }),
            ["ratholectl", "gre", "on", "2001:db8::2", "fd00::1", "gre6", "--key", "41007", "--mtu", "1420"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd("gre_on", {"remote_ip": "2001:db8::1", "tunnel_ip": "fd00::2", "name": "gre6", "gre_key": "41007"}),
            ["ratholenode", "gre", "on", "2001:db8::1", "fd00::2", "gre6", "--key", "41007"],
        )
        self.assertEqual(hubcmds.build_iran_cmd("gre_probe", {"peer_ip": "10.10.10.2", "name": "gre1"}),
                         ["ratholectl", "gre", "probe", "10.10.10.2", "gre1"])
        self.assertEqual(hubcmds.build_iran_cmd("gre_auto_mtu", {"peer_ip": "10.10.10.2", "name": "gre1"}),
                         ["ratholectl", "gre", "auto-mtu", "10.10.10.2", "gre1"])
        self.assertEqual(hubcmds.build_node_cmd("gre_auto_mtu", {"peer_ip": "fd00::1", "name": "gre6"}),
                         ["ratholenode", "gre", "auto-mtu", "fd00::1", "gre6"])

        self.assertIsNone(hubcmds.build_iran_cmd("gre_on", {"remote_ip": "198.51.100.5;id"}))
        self.assertIsNone(hubcmds.build_iran_cmd("gre_on", {"remote_ip": "198.51.100.5", "mtu": "200"}))
        self.assertIsNone(hubcmds.build_iran_cmd("gre_on", {"remote_ip": "198.51.100.5", "gre_key": "99999999999"}))
        self.assertEqual(
            hubcmds.build_iran_cmd("gre_on", {"remote_ip": "198.51.100.5", "gre_key": "007", "mtu": "0900"}),
            ["ratholectl", "gre", "on", "198.51.100.5", "10.10.10.1", "gre1", "--key", "7", "--mtu", "900"],
        )
        self.assertEqual(
            hubcmds.build_node_cmd("gre_on", {"remote_ip": "198.51.100.1", "gre_key": "0042", "mtu": "0800"}),
            ["ratholenode", "gre", "on", "198.51.100.1", "10.10.10.2", "gre1", "--key", "42", "--mtu", "800"],
        )

    def test_proxy_protocol_and_backup_actions(self):
        self.assertEqual(hubcmds.build_iran_cmd("game_proxy_protocol", {"mode": "on"}),
                         ["ratholectl", "game", "proxy-protocol", "on"])
        self.assertEqual(hubcmds.build_iran_cmd("frp_proxy_protocol", {"version": "v2"}),
                         ["ratholectl", "frp", "proxy-protocol", "v2"])
        self.assertEqual(hubcmds.build_node_cmd("frp_proxy_protocol", {"version": "off"}),
                         ["ratholenode", "frp", "proxy-protocol", "off"])
        self.assertIsNone(hubcmds.build_iran_cmd("game_proxy_protocol", {"mode": "on;rm"}))
        self.assertIsNone(hubcmds.build_node_cmd("frp_proxy_protocol", {"version": "v9"}))

        self.assertEqual(hubcmds.build_iran_cmd("restore_test", {"path": "/root/bak.tar.gz"}),
                         ["ratholectl", "restore", "--test", "/root/bak.tar.gz"])
        self.assertEqual(hubcmds.build_node_cmd("restore_test", {"path": "/root/node.tar.gz"}),
                         ["ratholenode", "restore", "--test", "/root/node.tar.gz"])
        self.assertIsNone(hubcmds.build_iran_cmd("restore_test", {"path": "/root/../etc/passwd"}))
        self.assertEqual(hubcmds.build_iran_cmd("backup_offsite_status", {}),
                         ["ratholectl", "backup", "offsite", "show"])
        self.assertEqual(hubcmds.build_node_cmd("backup_offsite_status", {}),
                         ["ratholenode", "backup", "offsite", "show"])

        for w in ("gre_auto_mtu", "game_proxy_protocol", "frp_proxy_protocol"):
            self.assertIn(w, hubcmds.WRITE_ACTIONS)
        for ro in ("restore_test", "backup_offsite_status", "gre_probe"):
            self.assertNotIn(ro, hubcmds.WRITE_ACTIONS)


if __name__ == "__main__":
    unittest.main()
