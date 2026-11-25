import unittest, os, sys, json, threading, urllib.request, time, signal, io
from unittest.mock import patch, Mock, mock_open

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../rathole-manager")))
import ratholeagent

class TestAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = "test-secret-token-12345678"
        cls.port = 0
        cls.server = ratholeagent.create_agent_server(
            "127.0.0.1", cls.port, cls.token, role="node", allow_test_python=True
        )
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def post_payload(self, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/exec", data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.token}"})
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_startup_does_not_log_file_token(self):
        server = Mock()
        server.serve_forever.side_effect = KeyboardInterrupt
        output = io.StringIO()
        with patch.object(sys, 'argv', ['ratholeagent']), patch.dict(os.environ, {}, clear=True), patch.object(ratholeagent.os.path, 'exists', return_value=True), patch('builtins.open', mock_open(read_data='root-secret-token')), patch.object(ratholeagent, 'create_agent_server', return_value=server), patch.object(sys, 'stderr', output):
            ratholeagent.main()
        self.assertNotIn('root-secret-token', output.getvalue())

    def test_timeout_kills_process_group(self):
        process = Mock(pid=1234)
        process.communicate.side_effect = [ratholeagent.subprocess.TimeoutExpired('cmd', 1), ('', '')]
        process.__enter__ = Mock(return_value=process)
        process.__exit__ = Mock(return_value=False)
        with patch.object(ratholeagent.os, 'name', 'posix'), patch.object(ratholeagent.os, 'killpg', create=True) as killpg, patch.object(ratholeagent.subprocess, 'Popen', return_value=process) as popen:
            status, result = self.post_payload({'cmd':['ratholectl'], 'timeout':1})
        self.assertEqual(status, 200)
        self.assertEqual(result['rc'], 124)
        self.assertTrue(popen.call_args.kwargs['start_new_session'])
        killpg.assert_called_once_with(1234, getattr(signal, "SIGKILL", 9))
        self.assertEqual(process.communicate.call_count, 2)

    @unittest.skipUnless(os.name == 'posix', 'POSIX process groups require Linux/macOS')
    def test_spawned_child_does_not_hold_timeout_response_open(self):
        script = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)"
        started = time.monotonic()
        status, result = self.post_payload({'cmd':[sys.executable,'-c',script], 'timeout':1})
        self.assertEqual(status, 200)
        self.assertEqual(result['rc'], 124)
        self.assertLess(time.monotonic()-started, 4)

    def test_timeout_wrapper(self):
        status, result = self.post_payload({"cmd": ["timeout", "5", sys.executable, "-c", "print('bounded')"]})
        self.assertEqual(status, 200)
        self.assertEqual(result["rc"], 0)
        self.assertIn("bounded", result["out"])

    def test_invalid_execution_payloads(self):
        for payload in [[], None, {"cmd": [None]}, {"cmd": ["ratholectl"], "timeout": "bad"},
                        {"cmd": ["ratholectl"], "timeout": 0}, {"cmd": ["ratholectl"], "timeout": 3601},
                        {"cmd": ["timeout", "-1", "ratholectl"]}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.post_payload(payload)[0], 400)
        self.assertEqual(self.post_payload({"cmd": ["timeout", "5", "forbidden-binary"]})[0], 403)

    def test_ping_unauthenticated(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/ping")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("role"), "node")

    def test_exec_unauthorized_without_token(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/exec",
            data=b'{"cmd":["echo","hello"]}',
            headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Should return 401 Unauthorized")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_exec_forbidden_with_wrong_token(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/exec",
            data=b'{"cmd":["echo","hello"]}',
            headers={"Content-Type": "application/json", "Authorization": "Bearer wrong-token"}
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Should return 403 Forbidden")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)

    def test_exec_with_valid_token(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/exec",
            data=json.dumps({"cmd": [sys.executable, "-c", "print('agent-ok')"]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("rc"), 0)
            self.assertIn("agent-ok", data.get("out", ""))

    def test_default_agent_blocks_shells_and_path_traversal(self):
        srv = ratholeagent.create_agent_server("127.0.0.1", 0, "sec-tok-123", role="node")
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            for bad_cmd in [
                ["bash", "-c", "id"],
                ["python3", "-c", "print(1)"],
                [sys.executable, "-c", "print(1)"],
                ["curl", "http://127.0.0.1"],
                ["cat", "/etc/passwd"],
                ["/tmp/evil/ratholectl", "ls"],
                ["../ratholectl", "ls"],
            ]:
                with self.subTest(bad_cmd=bad_cmd):
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/exec",
                        data=json.dumps({"cmd": bad_cmd}).encode(),
                        headers={"Content-Type": "application/json", "Authorization": "Bearer sec-tok-123"},
                    )
                    try:
                        urllib.request.urlopen(req, timeout=5)
                        self.fail(f"Expected 403 for {bad_cmd}")
                    except urllib.error.HTTPError as e:
                        self.assertEqual(e.code, 403)
        finally:
            srv.shutdown()
            srv.server_close()
            t.join(timeout=5)

    def test_empty_token_rejected(self):
        with self.assertRaises(ValueError):
            ratholeagent.create_agent_server("127.0.0.1", 0, "", role="node")
        with self.assertRaises(ValueError):
            ratholeagent.create_agent_server("127.0.0.1", 0, "   ", role="node")

        h = object.__new__(ratholeagent.AgentHandler)
        h.server_token = ""
        h.headers = {"Authorization": "Bearer "}
        sent = []
        h._send_json = lambda code, body: sent.append((code, body))
        self.assertFalse(h._auth())
        self.assertGreaterEqual(sent[0][0], 400)

    def test_log_message_logs_4xx_5xx(self):
        h = object.__new__(ratholeagent.AgentHandler)
        h.address_string = lambda: "127.0.0.1"
        err = io.StringIO()
        with patch.object(sys, "stderr", err):
            h.log_message('"%s" %s %s', "POST /api/exec HTTP/1.1", "403", "-")
            h.log_message('"%s" %s %s', "GET /api/ping HTTP/1.1", "200", "-")
        self.assertIn("403", err.getvalue())
        self.assertNotIn("200", err.getvalue())

    def test_hardened_server_backlog_and_broken_pipe_handling(self):
        self.assertGreaterEqual(ratholeagent._AgentHTTPServer.request_queue_size, 64)
        h = object.__new__(ratholeagent.AgentHandler)
        h.send_response = lambda _s: None
        h.send_header = lambda _k, _v: None
        h.end_headers = lambda: None
        broken_wfile = Mock()
        broken_wfile.write.side_effect = BrokenPipeError("client gone")
        h.wfile = broken_wfile
        # Must swallow client disconnect cleanly without raising
        h._send_json(200, {"ok": True})

if __name__ == "__main__":
    unittest.main()
