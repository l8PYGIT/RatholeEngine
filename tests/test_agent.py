import unittest, os, sys, json, threading, urllib.request, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../rathole-manager")))
import ratholeagent

class TestAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = "test-secret-token-12345678"
        cls.port = 8999
        cls.server = ratholeagent.create_agent_server("127.0.0.1", cls.port, cls.token, role="node")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_ping_unauthenticated(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/ping")
        with urllib.request.urlopen(req) as resp:
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
            urllib.request.urlopen(req)
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
            urllib.request.urlopen(req)
            self.fail("Should return 403 Forbidden")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)

    def test_exec_with_valid_token(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/exec",
            data=json.dumps({"cmd": [sys.executable, "-c", "print('agent-ok')"]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data.get("rc"), 0)
            self.assertIn("agent-ok", data.get("out", ""))

if __name__ == "__main__":
    unittest.main()
