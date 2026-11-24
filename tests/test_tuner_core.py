import base64
import gzip
import json
import os
import socket
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rathole-manager"))


class TestTunerProtocol(unittest.TestCase):
    def test_sign_and_verify_roundtrip(self):
        from tuner.protocol import sign_frame, verify_frame

        tok = "0123456789abcdef0123456789abcdef"
        frame = sign_frame(tok, "caps", {"iface": "eth0"}, ts=1000)
        seen = {}
        out = verify_frame(tok, frame, seen_nonces=seen, now=1005)
        self.assertEqual(out["action"], "caps")
        self.assertEqual(out["payload"], {"iface": "eth0"})
        self.assertIn(out["nonce"], seen)

    def test_rejects_replay_stale_tamper_and_unknown_action(self):
        from tuner.protocol import ProtocolError, sign_frame, verify_frame

        tok = "a" * 32
        frame = sign_frame(tok, "hello", {"role": "orchestrator"}, ts=2000)
        seen = {}
        verify_frame(tok, frame, seen_nonces=seen, now=2002)

        with self.assertRaises(ProtocolError):
            verify_frame(tok, frame, seen_nonces=seen, now=2003)

        stale = sign_frame(tok, "hello", {}, ts=1000)
        with self.assertRaises(ProtocolError):
            verify_frame(tok, stale, seen_nonces={}, now=2000)

        tampered = dict(frame)
        tampered["nonce"] = "deadbeef" * 4
        with self.assertRaises(ProtocolError):
            verify_frame(tok, tampered, seen_nonces={}, now=2001)

        with self.assertRaises(ProtocolError):
            sign_frame(tok, "exec_shell", {"cmd": "rm -rf /"})

    def test_frame_socket_rejects_oversized_payload(self):
        from tuner.protocol import ProtocolError, recv_frame, send_frame, sign_frame

        s1, s2 = socket.socketpair()
        try:
            tok = "b" * 32
            frame = sign_frame(tok, "heartbeat", {"seq": 1}, ts=5000)
            send_frame(s1, frame)
            got = recv_frame(s2, max_bytes=65536)
            self.assertEqual(got["action"], "heartbeat")

            s1.sendall(b"\x00\x20\x00\x00")
            with self.assertRaises(ProtocolError):
                recv_frame(s2, max_bytes=1024)
        finally:
            s1.close()
            s2.close()


class TestTunerProfile(unittest.TestCase):
    def _sample_profile(self):
        from tuner.profile import build_profile

        return build_profile(
            meta={
                "name": "arvan-hetzner-fast",
                "mode": "brutal",
                "goal": "balanced",
                "tags": {"iran_dc": "arvan-thr", "node_dc": "hetzner-fsn1"},
            },
            environment={
                "iran": {"kernel": "6.8.0", "cpus": 4, "ram_mb": 4096, "public_ip": "5.202.1.2"},
                "node": {"kernel": "6.8.0", "cpus": 2, "ram_mb": 2048, "domain": "node.secret.ir"},
                "pmtu": {"forward_bytes": 1460, "reverse_bytes": 1460, "blackhole_detected": False},
            },
            diagnostics=[{"code": "ok", "severity": "info", "detail": "peer 185.1.2.3 tested"}],
            benchmarks={
                "baseline": {"throughput_mbps": 100.0, "loaded_rtt_p95_ms": 140.0, "jitter_ms": 12.0, "retrans_pct": 1.2, "stability_cov": 0.2, "scores": {"balanced": 55.0}},
                "winner": {"throughput_mbps": 320.0, "loaded_rtt_p95_ms": 48.0, "jitter_ms": 3.0, "retrans_pct": 0.2, "stability_cov": 0.04, "scores": {"balanced": 92.0}},
                "top_candidates": [],
                "carriers": {},
            },
            iran_config={
                "mtu": 1460,
                "mss_clamp": 0,
                "qdisc": {"kind": "fq", "params": {}},
                "txqueuelen": 2000,
                "route": {"initcwnd": 32, "initrwnd": 32, "advmss": 1420},
                "offloads": {"tso": True, "gso": True, "gro": True},
                "sysctl": {
                    "net.core.default_qdisc": "fq",
                    "net.ipv4.tcp_congestion_control": "bbr",
                    "net.ipv4.tcp_notsent_lowat": 32768,
                    "net.core.rmem_max": 16777216,
                    "net.ipv4.tcp_rmem": "4096 131072 16777216",
                },
            },
            node_config={
                "mtu": 1460,
                "mss_clamp": 0,
                "qdisc": {"kind": "fq", "params": {}},
                "txqueuelen": 2000,
                "route": {"initcwnd": 32, "initrwnd": 32, "advmss": 1420},
                "offloads": {"tso": True, "gso": True, "gro": True},
                "sysctl": {
                    "net.core.default_qdisc": "fq",
                    "net.ipv4.tcp_congestion_control": "bbr",
                    "net.core.rmem_max": 16777216,
                },
            },
            non_kernel_recommendations={"nginx": [], "xray": [], "system": []},
        )

    def test_pii_stripping_and_b64_roundtrip(self):
        from tuner.profile import decode_profile_b64, encode_profile_b64

        prof = self._sample_profile()
        self.assertEqual(prof["schema"], "rathole.netprofile.v1")
        self.assertNotIn("public_ip", prof["environment"]["iran"])
        self.assertNotIn("domain", prof["environment"]["node"])
        self.assertNotIn("185.1.2.3", json.dumps(prof["diagnostics"]))

        b64 = encode_profile_b64(prof)
        self.assertTrue(b64.startswith("rthprof1:"))
        self.assertLessEqual(len(b64), 65536)

        decoded = decode_profile_b64(b64)
        self.assertEqual(decoded["integrity"]["sha256"], prof["integrity"]["sha256"])
        self.assertEqual(decoded["iran_config"]["mtu"], 1460)

    def test_rejects_tampered_sha_bad_sysctl_shell_and_zip_bomb(self):
        from tuner.profile import ProfileValidationError, decode_profile_b64, encode_profile_b64, validate_profile

        prof = self._sample_profile()
        bad = json.loads(json.dumps(prof))
        bad["iran_config"]["mtu"] = 1280
        with self.assertRaises(ProfileValidationError):
            validate_profile(bad, verify_sha=True)

        bad_key = json.loads(json.dumps(prof))
        bad_key["iran_config"]["sysctl"]["kernel.core_pattern"] = "|/bin/sh"
        with self.assertRaises(ProfileValidationError):
            validate_profile(bad_key, verify_sha=False)

        bad_mtu = json.loads(json.dumps(prof))
        bad_mtu["iran_config"]["mtu"] = 400
        with self.assertRaises(ProfileValidationError):
            validate_profile(bad_mtu, verify_sha=False)

        b64 = encode_profile_b64(prof)
        with self.assertRaises(ProfileValidationError):
            decode_profile_b64(b64[:-1] + ("A" if b64[-1] != "A" else "B"))

        huge_bytes = json.dumps({"schema": "rathole.netprofile.v1", "pad": "x" * 700000}).encode("utf-8")
        gz = gzip.compress(huge_bytes, compresslevel=9)
        bomb = "rthprof1:" + base64.urlsafe_b64encode(gz).decode("ascii").rstrip("=")
        with self.assertRaises(ProfileValidationError):
            decode_profile_b64(bomb)

    def test_ram_clamp_limits_buffers_to_10_pct(self):
        from tuner.profile import clamp_config_for_ram

        # 512 MiB RAM -> 10% = 53687091 bytes (~51.2 MiB); use 128 MiB -> ~13.4 MiB cap
        cfg = {
            "mtu": 1460,
            "sysctl": {
                "net.core.rmem_max": 67108864,
                "net.ipv4.tcp_rmem": "4096 131072 67108864",
            },
        }
        clamped = clamp_config_for_ram(cfg, ram_mb=128)
        cap = int(128 * 1024 * 1024 * 0.10)
        self.assertLessEqual(clamped["sysctl"]["net.core.rmem_max"], cap)
        self.assertLessEqual(int(clamped["sysctl"]["net.ipv4.tcp_rmem"].split()[2]), cap)


if __name__ == "__main__":
    unittest.main()
