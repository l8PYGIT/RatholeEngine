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
        mid = len(b64) // 2
        with self.assertRaises(ProfileValidationError):
            decode_profile_b64(b64[:mid] + ("A" if b64[mid] != "A" else "B") + b64[mid + 1:])
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


class TestScoringAndDiagnostics(unittest.TestCase):
    def test_goal_rankings_and_hard_fail_gate(self):
        from tuner.scoring import check_hard_fail, score_trials

        trials = [
            {
                "id": "baseline",
                "throughput_1_mbps": 120.0,
                "throughput_n_mbps": 150.0,
                "throughput_bidir_mbps": 100.0,
                "unloaded_rtt_p50_ms": 40.0,
                "loaded_rtt_p95_ms": 140.0,
                "rtt_p99_ms": 160.0,
                "rtt_p50_ms": 42.0,
                "jitter_ms": 14.0,
                "retrans_pct": 1.2,
                "udp_loss_pct": 1.0,
                "drop_delta": 0,
                "stability_cov": 0.18,
            },
            {
                "id": "low_lat_winner",
                "throughput_1_mbps": 240.0,
                "throughput_n_mbps": 280.0,
                "throughput_bidir_mbps": 200.0,
                "unloaded_rtt_p50_ms": 40.0,
                "loaded_rtt_p95_ms": 46.0,
                "rtt_p99_ms": 50.0,
                "rtt_p50_ms": 41.0,
                "jitter_ms": 1.5,
                "retrans_pct": 0.1,
                "udp_loss_pct": 0.0,
                "drop_delta": 0,
                "stability_cov": 0.04,
            },
            {
                "id": "bulk_hog",
                "throughput_1_mbps": 450.0,
                "throughput_n_mbps": 520.0,
                "throughput_bidir_mbps": 390.0,
                "unloaded_rtt_p50_ms": 40.0,
                "loaded_rtt_p95_ms": 380.0,
                "rtt_p99_ms": 420.0,
                "rtt_p50_ms": 50.0,
                "jitter_ms": 38.0,
                "retrans_pct": 2.1,
                "udp_loss_pct": 2.0,
                "drop_delta": 5,
                "stability_cov": 0.12,
            },
            {
                "id": "broken_lossy",
                "throughput_1_mbps": 600.0,
                "throughput_n_mbps": 650.0,
                "throughput_bidir_mbps": 500.0,
                "unloaded_rtt_p50_ms": 40.0,
                "loaded_rtt_p95_ms": 60.0,
                "rtt_p99_ms": 70.0,
                "rtt_p50_ms": 41.0,
                "jitter_ms": 3.0,
                "retrans_pct": 12.5,
                "udp_loss_pct": 18.0,
                "drop_delta": 0,
                "stability_cov": 0.05,
            },
        ]
        disq, reason = check_hard_fail(trials[3], trials[0])
        self.assertTrue(disq)
        self.assertTrue(reason)

        scored = {t["id"]: t for t in score_trials(trials, baseline_id="baseline")}
        self.assertTrue(scored["broken_lossy"]["disqualified"])
        self.assertEqual(scored["broken_lossy"]["scores"]["balanced"], 0.0)
        self.assertGreater(scored["low_lat_winner"]["scores"]["low-latency"], scored["bulk_hog"]["scores"]["low-latency"])
        self.assertGreater(scored["low_lat_winner"]["scores"]["anti-loss"], scored["bulk_hog"]["scores"]["anti-loss"])
        self.assertGreater(scored["bulk_hog"]["scores"]["max-throughput"], scored["baseline"]["scores"]["max-throughput"])


class TestSysstateWatchdogAuditApply(unittest.TestCase):
    def test_snapshot_apply_ram_cap_mtu_floor_and_restore(self):
        from tuner.sysstate import MockSysDriver, apply_candidate, capture_snapshot, discover_capabilities, restore_snapshot

        drv = MockSysDriver(ram_mb=256, ipv6_active=True)
        caps = discover_capabilities(drv, peer_ip="198.51.100.2")
        self.assertEqual(caps["ram_mb"], 256)
        self.assertIn("bbr", caps["available_cc"])

        snap = capture_snapshot(drv, iface=caps["iface"], peer_ip="198.51.100.2")
        res = apply_candidate(
            drv,
            {
                "mtu": 900,
                "mss_clamp": 1340,
                "qdisc": {"kind": "fq", "params": {}},
                "txqueuelen": 2500,
                "offloads": {"tso": False, "gro": True},
                "route": {"initcwnd": 32, "initrwnd": 32},
                "sysctl": {
                    "net.core.rmem_max": 67108864,
                    "net.ipv4.tcp_congestion_control": "bbr",
                    "net.ipv4.tcp_notsent_lowat": 32768,
                },
            },
            iface=caps["iface"],
            peer_ip="198.51.100.2",
            session_id="sess1",
            ram_mb=256,
            ipv6_active=True,
        )
        self.assertEqual(res["errors"], [])
        self.assertEqual(drv.mtu, 1280)
        self.assertLessEqual(int(drv.sysctls["net.core.rmem_max"]), int(256 * 1024 * 1024 * 0.10))
        self.assertIn("rathole-tuner-sess1", "\n".join(drv.iptables_mangle))

        restore_snapshot(drv, snap, session_id="sess1")
        self.assertEqual(drv.mtu, snap["mtu"])
        self.assertEqual(drv.sysctls["net.core.rmem_max"], snap["sysctl"]["net.core.rmem_max"])
        self.assertEqual(drv.iptables_mangle, [])

    def test_watchdog_triggers_on_missed_heartbeat_and_respects_disarm(self):
        import tempfile
        from tuner.watchdog import WatchdogController

        with tempfile.TemporaryDirectory() as td:
            snap_file = os.path.join(td, "snap.json")
            with open(snap_file, "w", encoding="utf-8") as f:
                json.dump({"mtu": 1500, "iface": "eth0", "sysctl": {}}, f)
            marker_arm = os.path.join(td, "restored.marker")

            wd = WatchdogController(td, session_id="wdtest1")
            wd.arm(snap_file, ttl_s=0.6, mock_restore_marker=marker_arm)
            try:
                time.sleep(0.25)
                wd.heartbeat()
                self.assertFalse(os.path.exists(marker_arm))
                deadline = time.time() + 4.0
                while time.time() < deadline and not os.path.exists(marker_arm):
                    time.sleep(0.1)
                self.assertTrue(os.path.exists(marker_arm))
            finally:
                wd.disarm()

            marker_disarm = os.path.join(td, "disarmed.marker")
            wd2 = WatchdogController(td, session_id="wdtest2")
            wd2.arm(snap_file, ttl_s=0.5, mock_restore_marker=marker_disarm)
            wd2.disarm()
            time.sleep(0.8)
            self.assertFalse(os.path.exists(marker_disarm))

    def test_non_kernel_audit_detects_nginx_xray_and_governor_issues(self):
        import tempfile
        from tuner.audit import run_non_kernel_audit
        from tuner.sysstate import MockSysDriver

        with tempfile.TemporaryDirectory() as td:
            nginx_conf = os.path.join(td, "rathole.conf")
            xray_conf = os.path.join(td, "xray.json")
            with open(nginx_conf, "w", encoding="utf-8") as f:
                f.write("location /node { proxy_pass http://127.0.0.1:8080; }\n")
            with open(xray_conf, "w", encoding="utf-8") as f:
                json.dump({
                    "log": {"loglevel": "debug"},
                    "policy": {"levels": {"0": {"bufferSize": 128}}},
                    "inbounds": [{"streamSettings": {"sockopt": {"tcpNoDelay": False}}}],
                    "outbounds": [{"mux": {"enabled": True, "concurrency": 8}}],
                }, f)

            drv = MockSysDriver(cpu_governor="powersave")
            res = run_non_kernel_audit(
                drv,
                role="node",
                paths={"nginx_conf": nginx_conf, "xray_conf": xray_conf},
            )
            codes = {f["code"] for f in res["findings"]}
            self.assertIn("cpu_governor_powersave", codes)
            self.assertIn("xray_mux_enabled", codes)
            self.assertIn("xray_loglevel_debug", codes)

    def test_persistent_apply_boot_status_and_rollback(self):
        import tempfile
        from tuner.apply import apply_boot, apply_persistent, rollback_persistent, tuner_status
        from tuner.profile import build_profile
        from tuner.sysstate import MockSysDriver

        with tempfile.TemporaryDirectory() as td:
            reserved = os.path.join(td, "99-rathole-reserved-ports.conf")
            tune_conf = os.path.join(td, "99-rathole-tune.conf")
            applied_json = os.path.join(td, "applied-profile.json")
            unit_file = os.path.join(td, "rathole-net-tune.service")
            snap_dir = os.path.join(td, "snapshots")
            with open(reserved, "w", encoding="utf-8") as f:
                f.write("net.ipv4.ip_local_reserved_ports=2333,443,8088\n")

            prof = build_profile(
                meta={"name": "apply-test"},
                environment={},
                diagnostics=[],
                benchmarks={},
                iran_config={
                    "mtu": 1420,
                    "qdisc": {"kind": "fq", "params": {}},
                    "txqueuelen": 2500,
                    "route": {"initcwnd": 32},
                    "sysctl": {"net.core.default_qdisc": "fq", "net.ipv4.tcp_congestion_control": "bbr"},
                },
                node_config={"mtu": 1420, "sysctl": {"net.ipv4.tcp_congestion_control": "bbr"}},
            )
            drv = MockSysDriver(ram_mb=2048)
            paths = {
                "sysctl_tune_file": tune_conf,
                "reserved_ports_file": reserved,
                "applied_profile_file": applied_json,
                "systemd_unit_file": unit_file,
                "snapshot_dir": snap_dir,
            }
            out = apply_persistent(drv, prof, side="iran", paths=paths)
            self.assertTrue(out["ok"])
            self.assertTrue(os.path.exists(tune_conf))
            self.assertTrue(os.path.exists(applied_json))
            self.assertTrue(os.path.exists(unit_file))
            self.assertEqual(drv.mtu, 1420)
            with open(unit_file, encoding="utf-8") as fh:
                self.assertIn("rathole-tuner apply-boot", fh.read())

            drv.mtu = 1500
            apply_boot(drv, paths=paths)
            self.assertEqual(drv.mtu, 1420)

            st = tuner_status(drv, paths=paths)
            self.assertTrue(st["applied"])
            self.assertEqual(st["profile_name"], "apply-test")

            rb = rollback_persistent(drv, paths=paths)
            self.assertTrue(rb["ok"])
            self.assertFalse(os.path.exists(applied_json))
            self.assertEqual(drv.mtu, 1500)
            with open(reserved, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "net.ipv4.ip_local_reserved_ports=2333,443,8088\n")


if __name__ == "__main__":
    unittest.main()
