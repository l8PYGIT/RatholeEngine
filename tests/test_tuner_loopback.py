import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rathole-manager"))


class TestTunerLoopbackAndCLI(unittest.TestCase):
    def test_full_responder_orchestrator_loopback_and_profile_compare(self):
        from tuner.orchestrator import TunerOrchestrator
        from tuner.profile import decode_profile_b64
        from tuner.responder import TunerResponder
        from tuner.sysstate import MockSysDriver

        token = "feedface0123456789abcdef01234567"
        with tempfile.TemporaryDirectory() as td:
            resp_drv = MockSysDriver(ram_mb=2048, cpus=4, available_cc=["cubic", "bbr"], available_qdisc=["fq", "fq_codel"])
            orch_drv = MockSysDriver(ram_mb=2048, cpus=4, available_cc=["cubic", "bbr"], available_qdisc=["fq", "fq_codel"])

            responder = TunerResponder(
                bind_host="127.0.0.1",
                ctrl_port=0,
                data_port=0,
                token=token,
                idle_timeout=60,
                driver=resp_drv,
                state_dir=os.path.join(td, "resp_state"),
            )
            responder.start()
            th = threading.Thread(target=responder.serve_forever, daemon=True)
            th.start()
            try:
                events = []
                orch = TunerOrchestrator(
                    peer_host="127.0.0.1",
                    ctrl_port=responder.ctrl_port,
                    token=token,
                    mode="brutal",
                    goal="balanced",
                    tags={"iran_dc": "ir-arvan", "node_dc": "de-hetzner"},
                    out_dir=os.path.join(td, "out"),
                    driver=orch_drv,
                    state_dir=os.path.join(td, "orch_state"),
                    fast_test=True,
                    progress_cb=events.append,
                )
                result = orch.run()
                self.assertTrue(result["ok"])
                self.assertGreater(len(events), 4)
                self.assertEqual(events[0]["phase"], "connecting_peer")
                phases = [e.get("phase") for e in events]
                self.assertIn("mtu_mss_offload", phases)
                self.assertIn("carrier_matrix", phases)
                self.assertIn("finalist_soak", phases)
                c_ev = next(e for e in events if e.get("phase") == "carrier_matrix")
                s_ev = next(e for e in events if e.get("phase") == "finalist_soak")
                self.assertGreater(c_ev.get("best_so_far", 0), 0)
                self.assertGreater(s_ev.get("best_so_far", 0), 0)
                self.assertTrue(c_ev.get("pmtu"))
                self.assertGreater(len(c_ev.get("live_trials") or []), 0)
                first_row = c_ev["live_trials"][0]
                for fk in ("name", "throughput_mbps", "loaded_rtt_p95_ms", "score"):
                    self.assertIn(fk, first_row)
                prof = result["profile"]
                b64 = result["profile_b64"]
                self.assertEqual(prof["schema"], "rathole.netprofile.v1")
                self.assertTrue(b64.startswith("rthprof1:"))
                self.assertIn("baseline", result["benchmarks"])
                self.assertIn("winner", result["benchmarks"])
                self.assertGreater(len(result["benchmarks"]["top_candidates"]), 0)
                self.assertIn("raw-tcp", result["benchmarks"]["carriers"])

                # Both hosts restored cleanly to pre-flight baseline after run
                self.assertEqual(orch_drv.mtu, 1500)
                self.assertEqual(resp_drv.mtu, 1500)
                self.assertEqual(orch_drv.sysctls["net.ipv4.tcp_congestion_control"], "cubic")
                self.assertEqual(resp_drv.sysctls["net.ipv4.tcp_congestion_control"], "cubic")
                self.assertEqual(orch_drv.iptables_mangle, [])
                self.assertEqual(resp_drv.iptables_mangle, [])

                # Exported string decodes and validates strictly
                decoded = decode_profile_b64(b64)
                self.assertEqual(decoded["meta"]["tags"]["iran_dc"], "ir-arvan")

                # Re-test imported profile A/B & compare back-to-back over fresh responder session
                prof_json_path = os.path.join(td, "prof.json")
                with open(prof_json_path, "w", encoding="utf-8") as fh:
                    json.dump(prof, fh)

                responder2 = TunerResponder(
                    bind_host="127.0.0.1",
                    ctrl_port=0,
                    data_port=0,
                    token=token,
                    idle_timeout=60,
                    driver=resp_drv,
                    state_dir=os.path.join(td, "resp_state2"),
                )
                responder2.start()
                th2 = threading.Thread(target=responder2.serve_forever, daemon=True)
                th2.start()
                try:
                    orch2 = TunerOrchestrator(
                        peer_host="127.0.0.1",
                        ctrl_port=responder2.ctrl_port,
                        token=token,
                        mode="brutal",
                        goal="low-latency",
                        driver=orch_drv,
                        state_dir=os.path.join(td, "orch_state2"),
                        fast_test=True,
                    )
                    ab = orch2.test_profile(b64)
                    self.assertTrue(ab["ok"])
                    self.assertIn("baseline", ab)
                    self.assertIn("candidate", ab)
                    self.assertIn("delta", ab)
                finally:
                    responder2.stop()
                    th2.join(timeout=3.0)

                responder3 = TunerResponder(
                    bind_host="127.0.0.1",
                    ctrl_port=0,
                    data_port=0,
                    token=token,
                    idle_timeout=60,
                    driver=resp_drv,
                    state_dir=os.path.join(td, "resp_state3"),
                )
                responder3.start()
                th3 = threading.Thread(target=responder3.serve_forever, daemon=True)
                th3.start()
                try:
                    orch3 = TunerOrchestrator(
                        peer_host="127.0.0.1",
                        ctrl_port=responder3.ctrl_port,
                        token=token,
                        mode="safe",
                        goal="balanced",
                        driver=orch_drv,
                        state_dir=os.path.join(td, "orch_state3"),
                        fast_test=True,
                    )
                    cmp_res = orch3.compare_profiles([b64, prof_json_path])
                    self.assertTrue(cmp_res["ok"])
                    self.assertEqual(len(cmp_res["leaderboard"]), 3)  # baseline + 2 profiles
                finally:
                    responder3.stop()
                    th3.join(timeout=3.0)

                # CLI validate & export smoke test
                cli_path = os.path.join(os.path.dirname(__file__), "..", "rathole-manager", "rathole-tuner")
                p_val = subprocess.run(
                    [sys.executable, cli_path, "validate", b64, "--json"],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(p_val.returncode, 0, p_val.stderr)
                self.assertTrue(json.loads(p_val.stdout)["ok"])

                p_exp = subprocess.run(
                    [sys.executable, cli_path, "export", os.path.join(td, "out", "report.json"), "--format", "base64"],
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(p_exp.returncode, 0, p_exp.stderr)
                self.assertTrue(p_exp.stdout.strip().startswith("rthprof1:"))
            finally:
                responder.stop()
                th.join(timeout=3.0)

    def test_control_client_recovers_from_dropped_socket(self):
        from tuner.protocol import ControlClient
        from tuner.responder import TunerResponder
        from tuner.sysstate import MockSysDriver

        token = "feedface0123456789abcdef01234567"
        with tempfile.TemporaryDirectory() as td:
            resp = TunerResponder(
                bind_host="127.0.0.1",
                ctrl_port=0,
                data_port=0,
                token=token,
                idle_timeout=30,
                driver=MockSysDriver(),
                state_dir=td,
            )
            resp.start()
            th = threading.Thread(target=resp.serve_forever, daemon=True)
            th.start()
            client = ControlClient("127.0.0.1", resp.ctrl_port, token, timeout=5.0)
            try:
                client.connect()
                h1 = client.call("hello", {"role": "orchestrator"})
                self.assertTrue(h1.get("ok"))
                # Simulate mid-run TCP drop / reset without closing ControlClient cleanly
                client._sock.close()
                c2 = client.call("caps", {"peer_ip": ""})
                self.assertTrue(c2.get("ok"))
                self.assertIn("iface", c2.get("caps") or {})
            finally:
                client.close()
                resp.stop()
                th.join(timeout=3.0)


if __name__ == "__main__":
    unittest.main()
