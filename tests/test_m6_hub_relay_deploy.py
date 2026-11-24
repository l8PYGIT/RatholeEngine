#!/usr/bin/env python3
"""Unit and live HTTP mock tests for M6: tunnel-relayed updates, Ed25519 verification, Hub deploy & Backhaul CA pinning."""

import base64
import hashlib
import http.client
import importlib.util
import io
import json
import os
import select
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HUB_DIR = os.path.join(REPO_ROOT, "rathole-manager", "ratholehub")
if HUB_DIR not in sys.path:
    sys.path.insert(0, HUB_DIR)

import hubcmds  # noqa: E402
import hubupdate  # noqa: E402


def _load_hub():
    os.environ.setdefault("RATHOLEHUB_MOCK", "1")
    spec = importlib.util.spec_from_file_location("hub", os.path.join(HUB_DIR, "hub.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hub = _load_hub()


def _make_ed25519_keypair(tmpdir):
    openssl_bin = shutil.which("openssl")
    if not openssl_bin:
        return None, None
    priv = os.path.join(tmpdir, "rel.key")
    pub = os.path.join(tmpdir, "rel.pub")
    r1 = subprocess.run([openssl_bin, "genpkey", "-algorithm", "ED25519", "-out", priv], capture_output=True, text=True)
    if r1.returncode != 0:
        return None, None
    r2 = subprocess.run([openssl_bin, "pkey", "-in", priv, "-pubout", "-out", pub], capture_output=True, text=True)
    if r2.returncode != 0:
        return None, None
    return priv, pub


def _sign_bytes_ed25519(priv_path, data_bytes):
    openssl_bin = shutil.which("openssl")
    with tempfile.NamedTemporaryFile(delete=False) as tf_in:
        tf_in.write(data_bytes)
        in_p = tf_in.name
    out_p = in_p + ".rawsig"
    try:
        r = subprocess.run(
            [openssl_bin, "pkeyutl", "-sign", "-inkey", priv_path, "-rawin", "-in", in_p, "-out", out_p],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr)
        with open(out_p, "rb") as f:
            raw = f.read()
        return base64.b64encode(raw) + b"\n"
    finally:
        for p in (in_p, out_p):
            try:
                os.remove(p)
            except OSError:
                pass


class _ConnectProxyServer:
    """Minimal stdlib HTTP CONNECT proxy supporting Basic auth for unit tests."""

    def __init__(self, expected_auth=None):
        self.expected_auth = expected_auth
        self.connects = 0
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(16)
        self.port = self.srv.getsockname()[1]
        self._stop = False
        self._th = threading.Thread(target=self._accept_loop, daemon=True)
        self._th.start()

    def _accept_loop(self):
        self.srv.settimeout(0.2)
        while not self._stop:
            try:
                cli, _ = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(cli,), daemon=True).start()

    def _handle_client(self, cli):
        up = None
        try:
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 8192:
                chunk = cli.recv(1024)
                if not chunk:
                    cli.close()
                    return
                buf += chunk
            head, rest = buf.split(b"\r\n\r\n", 1)
            lines = head.decode("latin1", errors="replace").split("\r\n")
            parts = lines[0].split()
            if len(parts) < 2 or parts[0].upper() != "CONNECT":
                cli.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                cli.close()
                return
            if self.expected_auth:
                hdrs = {k.lower().strip(): v.strip() for ln in lines[1:] if ":" in ln for k, v in [ln.split(":", 1)]}
                want = "Basic " + base64.b64encode(self.expected_auth.encode("utf-8")).decode("ascii")
                if hdrs.get("proxy-authorization") != want:
                    cli.sendall(b"HTTP/1.1 407 Proxy Auth Required\r\n\r\n")
                    cli.close()
                    return
            host, pstr = parts[1].rsplit(":", 1)
            up = socket.create_connection((host, int(pstr)), timeout=5)
            self.connects += 1
            cli.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if rest:
                up.sendall(rest)
            socks = [cli, up]
            while True:
                rlist, _, _ = select.select(socks, [], [], 2.0)
                if not rlist:
                    continue
                for s in rlist:
                    data = s.recv(8192)
                    if not data:
                        return
                    (up if s is cli else cli).sendall(data)
        except Exception:
            pass
        finally:
            for s in (cli, up):
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass

    def close(self):
        self._stop = True
        try:
            self.srv.close()
        except OSError:
            pass
        self._th.join(timeout=2)


class TestM6HubCmdsAndVerification(unittest.TestCase):
    def test_backhaul_on_optional_ca_sni_verify(self):
        tok = "a" * 32
        base = {"mode": "direct_ip", "remote_addr": "198.51.100.10:3080", "token": tok, "transport": "wssmux", "profile": "balanced"}
        # Backwards compatible without new keys
        self.assertEqual(
            hubcmds.build_node_cmd("backhaul_on", base),
            ["ratholenode", "backhaul", "on", "198.51.100.10:3080", tok, "wssmux", "balanced"],
        )
        # With tls_ca, tls_sni, tls_verify
        with_pin = dict(base, tls_ca="/etc/rathole/ip-root-ca.crt", tls_sni="cdn.example.com", tls_verify=True)
        self.assertEqual(
            hubcmds.build_node_cmd("backhaul_on", with_pin),
            [
                "ratholenode", "backhaul", "on", "198.51.100.10:3080", tok, "wssmux", "balanced",
                "--ca", "/etc/rathole/ip-root-ca.crt", "--sni", "cdn.example.com", "--verify",
            ],
        )
        # Reject injection / bad paths / bad booleans
        self.assertIsNone(hubcmds.build_node_cmd("backhaul_on", dict(base, tls_ca="/etc/rathole/../bad.crt")))
        self.assertIsNone(hubcmds.build_node_cmd("backhaul_on", dict(base, tls_sni="evil;id")))
        self.assertIsNone(hubcmds.build_node_cmd("backhaul_on", dict(base, tls_verify="maybe")))

    def test_ed25519_verification_and_sha256sums(self):
        with tempfile.TemporaryDirectory() as d:
            priv, pub = _make_ed25519_keypair(d)
            if not priv:
                self.skipTest("openssl Ed25519 unavailable on this host")
            boot = os.path.join(d, "bootstrap.sh")
            bndl = os.path.join(d, "rathole-manager.zip")
            with open(boot, "wb") as f:
                f.write(b"#!/bin/sh\necho boot\n")
            with open(bndl, "wb") as f:
                f.write(b"PK-FAKE-BUNDLE")
            with open(boot, "rb") as f:
                h_boot = hashlib.sha256(f.read()).hexdigest()
            with open(bndl, "rb") as f:
                h_bndl = hashlib.sha256(f.read()).hexdigest()
            sums = os.path.join(d, "SHA256SUMS")
            sums_bytes = f"{h_bndl}  rathole-manager.zip\n{h_boot}  bootstrap.sh\n".encode("utf-8")
            with open(sums, "wb") as f:
                f.write(sums_bytes)
            sig = os.path.join(d, "SHA256SUMS.sig")
            with open(sig, "wb") as f:
                f.write(_sign_bytes_ed25519(priv, sums_bytes))

            res = hubupdate.verify_ed25519_sig(sums, sig, pubkey_path=pub, require_sig=True)
            self.assertTrue(res["verified"])
            self.assertTrue(hubupdate.verify_sha256sums(sums, {"bootstrap.sh": boot, "rathole-manager.zip": bndl}))

            # Tamper sums -> fails even when require_sig=False
            with open(sums, "ab") as f:
                f.write(b"# tampered\n")
            with self.assertRaises(hubupdate.VerificationError):
                hubupdate.verify_ed25519_sig(sums, sig, pubkey_path=pub, require_sig=False)

            # Missing sig -> rejected when require_sig=True, allowed when require_sig=False
            with open(sums, "wb") as f:
                f.write(sums_bytes)
            os.remove(sig)
            with self.assertRaises(hubupdate.VerificationError):
                hubupdate.verify_ed25519_sig(sums, sig, pubkey_path=pub, require_sig=True)
            self.assertFalse(hubupdate.verify_ed25519_sig(sums, sig, pubkey_path=pub, require_sig=False)["verified"])


class TestM6RelayedReleaseDownloadAndDeploy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.priv, self.pub = _make_ed25519_keypair(self.tmp.name)
        self.boot_bytes = b"#!/usr/bin/env bash\necho boot-ok\n"
        self.zip_bytes = b"PK\x03\x04MOCK_RELEASE_BUNDLE_M6"
        h_boot = hashlib.sha256(self.boot_bytes).hexdigest()
        h_zip = hashlib.sha256(self.zip_bytes).hexdigest()
        self.sums_bytes = f"{h_zip}  rathole-manager.zip\n{h_boot}  bootstrap.sh\n".encode("utf-8")
        self.sig_bytes = _sign_bytes_ed25519(self.priv, self.sums_bytes) if self.priv else b""
        self.tamper_zip = False
        self.block_direct = False

        outer = self

        class ReleaseHandler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                if outer.block_direct:
                    self.send_response(503)
                    self.end_headers()
                    return
                if self.path == "/o/r/releases.atom":
                    body = b'<link href="/o/r/releases/tag/v2.2.0-beta.1"/>'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                mapping = {
                    "/o/r/releases/latest/download/bootstrap.sh": outer.boot_bytes,
                    "/o/r/releases/download/v2.2.0-beta.1/bootstrap.sh": outer.boot_bytes,
                    "/o/r/releases/latest/download/rathole-manager.zip": (b"EVIL" if outer.tamper_zip else outer.zip_bytes),
                    "/o/r/releases/download/v2.2.0-beta.1/rathole-manager.zip": outer.zip_bytes,
                    "/o/r/releases/latest/download/SHA256SUMS": outer.sums_bytes,
                    "/o/r/releases/download/v2.2.0-beta.1/SHA256SUMS": outer.sums_bytes,
                    "/o/r/releases/latest/download/SHA256SUMS.sig": outer.sig_bytes,
                    "/o/r/releases/download/v2.2.0-beta.1/SHA256SUMS.sig": outer.sig_bytes,
                }
                if self.path not in mapping or not mapping[self.path]:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = mapping[self.path]
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.rel_srv = ThreadingHTTPServer(("127.0.0.1", 0), ReleaseHandler)
        self.rel_port = self.rel_srv.server_address[1]
        self.rel_th = threading.Thread(target=self.rel_srv.serve_forever, daemon=True)
        self.rel_th.start()
        self.base_url = f"http://127.0.0.1:{self.rel_port}"

    def tearDown(self):
        self.rel_srv.shutdown()
        self.rel_srv.server_close()
        self.rel_th.join(timeout=2)
        self.tmp.cleanup()

    def test_download_verified_release_direct_proxy_and_tamper(self):
        if not self.priv:
            self.skipTest("openssl Ed25519 unavailable on this host")
        # Direct beta download + verification
        res = hubupdate.download_verified_release(
            "o/r", channel="beta", pubkey_path=self.pub, require_sig=True, base_url=self.base_url, dest_dir=os.path.join(self.tmp.name, "d1")
        )
        self.assertEqual(res["release"], "v2.2.0-beta.1")
        self.assertTrue(res["sig"]["verified"])
        with open(res["bundle_path"], "rb") as f:
            self.assertEqual(f.read(), self.zip_bytes)

        # Download over authenticated HTTP CONNECT proxy (creds redacted from result)
        proxy_srv = _ConnectProxyServer(expected_auth="uproxy:s3cr3tpass")
        try:
            res_px = hubupdate.download_verified_release(
                "o/r",
                channel="stable",
                proxy_url=f"http://uproxy:s3cr3tpass@127.0.0.1:{proxy_srv.port}",
                pubkey_path=self.pub,
                require_sig=True,
                base_url=self.base_url,
                dest_dir=os.path.join(self.tmp.name, "d2"),
            )
            self.assertGreater(proxy_srv.connects, 0)
            self.assertNotIn("s3cr3tpass", json.dumps(res_px))
        finally:
            proxy_srv.close()

        # Tampered bundle rejected immediately even though SHA256SUMS + sig valid
        self.tamper_zip = True
        with self.assertRaises(hubupdate.VerificationError):
            hubupdate.download_verified_release(
                "o/r", channel="stable", pubkey_path=self.pub, require_sig=True, base_url=self.base_url, dest_dir=os.path.join(self.tmp.name, "d3")
            )

    def test_ssh_relay_fallback_and_cleanup_plus_tar_push(self):
        if not self.priv:
            self.skipTest("openssl Ed25519 unavailable on this host")
        proxy_srv = _ConnectProxyServer()
        closed = {"count": 0}

        class FakeSshTunnel:
            def __init__(self, server, ssh_key_path="", ssh_opts=None, local_port=None):
                del server, ssh_key_path, ssh_opts, local_port
                self.proxy_url = f"http://127.0.0.1:{proxy_srv.port}"

            def close(self):
                closed["count"] += 1

        inv = [{"name": "de01", "role": "node", "host": "198.51.100.55", "ssh_user": "root", "ssh_port": 22}]
        # Override _build_candidates? Even better: first attempt direct fails because port is unreachable,
        # OR we test _build_candidates ordering + fallback when direct host fails and relay uses base_url!
        try:
            with patch.object(hubupdate.tg_relay, "SshRelayTunnel", FakeSshTunnel), \
                 patch.object(hubupdate, "_build_candidates", return_value=[
                     ("direct", "direct", "", None),
                     ("ssh_relay:de01", "ssh", "", inv[0]),
                 ]):
                # Fail direct attempt once via http_download_file side_effect only for proxy_url == ""
                orig_dl = hubupdate.http_download_file

                def _selective_dl(url, dest_path, proxy_url="", **kw):
                    if not proxy_url:
                        raise RuntimeError("direct blocked by filtering")
                    return orig_dl(url, dest_path, proxy_url=proxy_url, **kw)

                with patch.object(hubupdate, "http_download_file", side_effect=_selective_dl):
                    res = hubupdate.download_verified_release(
                        "o/r",
                        channel="stable",
                        inventory=inv,
                        pubkey_path=self.pub,
                        require_sig=True,
                        base_url=self.base_url,
                        dest_dir=os.path.join(self.tmp.name, "d4"),
                    )
                self.assertEqual(res["via"], "ssh_relay:de01")
                self.assertEqual(closed["count"], 1)
                self.assertGreater(proxy_srv.connects, 0)

                # Test tar streaming push_and_run_update
                captured = {}

                def _fake_subproc(cmd, input=None, capture_output=False, timeout=0):
                    captured["cmd"] = cmd
                    captured["tar"] = input
                    captured["timeout"] = timeout
                    m = type("R", (), {"returncode": 0, "stdout": b"updated ok", "stderr": b""})()
                    return m

                with patch.object(hubupdate.subprocess, "run", side_effect=_fake_subproc):
                    pr = hubupdate.push_and_run_update(
                        {"name": "rp01"},
                        ["ssh", "root@rp01", "--"],
                        res["bootstrap_path"],
                        res["bundle_path"],
                        res["bundle_name"],
                        "o/r",
                        "latest",
                        require_sig=True,
                    )
                self.assertEqual(pr["rc"], 0)
                with tarfile.open(fileobj=io.BytesIO(captured["tar"]), mode="r") as tf:
                    self.assertEqual(sorted(tf.getnames()), ["bootstrap.sh", "rathole-manager.zip"])
                self.assertIn('RATHOLE_REQUIRE_SIG="1"', captured["cmd"][-1])
        finally:
            proxy_srv.close()


class TestM6HubDeployAndConfigHttp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = (
            hub.CONF_PATH,
            hub.INV_PATH,
            hub.MOCK,
            hub.AUDIT_PATH,
            dict(hub._HTTP_REQS),
            dict(hub._LOGIN_FAILS),
        )
        self.conf = os.path.join(self.tmp.name, "conf.json")
        self.inv = os.path.join(self.tmp.name, "inv.json")
        self.audit = os.path.join(self.tmp.name, "audit.log")
        self.tok = "test_m6_admin_token_abcdef123456"
        with open(self.conf, "w", encoding="utf-8") as f:
            json.dump({
                "api_token": self.tok,
                "admin_password_sha256": hub._hash_password("pass1234"),
                "listen_host": "127.0.0.1",
                "listen_port": 0,
            }, f)
        with open(self.inv, "w", encoding="utf-8") as f:
            json.dump([{"name": "rp01", "role": "iran", "host": "5.202.4.40"}], f)
        hub.CONF_PATH = self.conf
        hub.INV_PATH = self.inv
        hub.MOCK = True
        hub.AUDIT_PATH = self.audit
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
        hub.CONF_PATH, hub.INV_PATH, hub.MOCK, hub.AUDIT_PATH, reqs, lf = self.orig
        hub._HTTP_REQS.clear()
        hub._HTTP_REQS.update(reqs)
        hub._LOGIN_FAILS.clear()
        hub._LOGIN_FAILS.update(lf)
        self.tmp.cleanup()

    def _req(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            hdrs = {"Content-Type": "application/json", "Authorization": f"Bearer {self.tok}"}
            raw = json.dumps(body).encode("utf-8") if body is not None else None
            conn.request(method, path, body=raw, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data) if data else {}
        finally:
            conn.close()

    def test_config_update_fields_save_and_redaction(self):
        st, d = self._req("POST", "/api/config", {
            "update_channel": "beta",
            "update_relay_mode": "relay",
            "update_proxy": "socks5h://u1:secret99@127.0.0.1:1080",
            "update_require_sig": True,
        })
        self.assertEqual(st, 200)
        self.assertTrue(d["ok"])

        st2, view = self._req("GET", "/api/config")
        self.assertEqual(st2, 200)
        self.assertEqual(view["update_channel"], "beta")
        self.assertEqual(view["update_relay_mode"], "relay")
        self.assertEqual(view["update_proxy"], "socks5h://***@127.0.0.1:1080")
        self.assertTrue(view["update_proxy_set"])
        self.assertTrue(view["update_require_sig"])
        self.assertNotIn("secret99", json.dumps(view))

        # Saving redacted display back must preserve raw stored proxy
        st3, _ = self._req("POST", "/api/config", {
            "update_channel": "stable",
            "update_proxy": "socks5h://***@127.0.0.1:1080",
        })
        self.assertEqual(st3, 200)
        with open(self.conf, encoding="utf-8") as f:
            saved_cfg = json.load(f)
        self.assertEqual(saved_cfg["update_proxy"], "socks5h://u1:secret99@127.0.0.1:1080")

        # Invalid relay mode rejected
        st4, _ = self._req("POST", "/api/config", {"update_relay_mode": "invalid"})
        self.assertEqual(st4, 400)

    def test_deploy_to_server_auto_fallback_and_api_flags(self):
        # API transport with update_proxy + update_require_sig
        api_srv = {"name": "n1", "role": "node", "transport": "api", "api_url": "http://127.0.0.1:8089", "api_token": "tok"}
        with patch.object(hub, "MOCK", False), \
             patch.object(hub, "get_config", return_value={"update_channel": "beta", "update_proxy": "socks5h://127.0.0.1:1080", "update_require_sig": True}), \
             patch.object(hub, "run_on_server", return_value={"rc": 0}) as run:
            res = hub.deploy_to_server(api_srv)
            self.assertEqual(res["rc"], 0)
            self.assertEqual(run.call_args.args[1], ["ratholenode", "update", "beta", "--proxy", "socks5h://127.0.0.1:1080", "--require-sig"])

        # SSH auto-fallback when direct curl fails with filtering error
        ssh_srv = {"name": "rp01", "role": "iran", "host": "5.202.4.40"}
        with patch.object(hub, "MOCK", False), \
             patch.object(hub, "get_config", return_value={"update_relay_mode": "auto"}), \
             patch.object(hub, "run_on_server", return_value={"rc": 1, "out": "", "err": "download install.sh az hameye mirror-ha shekast khord (filtering?)"}), \
             patch.object(hub, "_relay_deploy_to_server", return_value={"rc": 0, "out": "pushed ok", "err": ""}) as relay_fn:
            res2 = hub.deploy_to_server(ssh_srv)
            self.assertEqual(res2["rc"], 0)
            self.assertTrue(relay_fn.called)
            self.assertIn("[auto-relay]", res2["out"])

        # Explicit relay mode skips direct run_on_server
        with patch.object(hub, "MOCK", False), \
             patch.object(hub, "get_config", return_value={"update_relay_mode": "relay"}), \
             patch.object(hub, "run_on_server") as run_ssh, \
             patch.object(hub, "_relay_deploy_to_server", return_value={"rc": 0, "out": "direct relay", "err": ""}) as relay_fn:
            res3 = hub.deploy_to_server(ssh_srv)
            self.assertEqual(res3["rc"], 0)
            self.assertFalse(run_ssh.called)
            self.assertTrue(relay_fn.called)


if __name__ == "__main__":
    unittest.main()
