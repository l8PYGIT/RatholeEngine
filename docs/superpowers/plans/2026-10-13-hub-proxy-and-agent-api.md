# RatholeHub Proxy Support & REST Agent Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable RatholeHub to communicate through HTTP/SOCKS5 proxies and migrate from SSH-only execution to a secure, lightweight REST Agent (`rathole-agent`) for fast, censorship-resistant server management.

**Architecture:**
1. A zero-dependency Python proxy bridge (`ssh_proxy.py`) and `urllib` ProxyHandler that allow RatholeHub to route both SSH commands and HTTP API requests through any SOCKS5/HTTP proxy (e.g. Clash/v2ray/sing-box on `127.0.0.1:10808` or `127.0.0.1:7890`).
2. A lightweight, stdlib-only Python HTTP daemon (`rathole-manager/ratholeagent.py`) installed on Iran panels or foreign nodes, listening on a dedicated port (default 8089) with Bearer token authentication and executing whitelisted commands.
3. Dual-transport server execution in `hub.py`: servers can connect via `"ssh"` (with optional proxy) or `"api"` (with optional proxy), fully transparent to all UI actions.
4. UI and i18n additions for proxy configuration, connection type selection (SSH vs Agent API), and transport badges.

**Tech Stack:** Python 3 (stdlib only: `http.server`, `urllib.request`, `socket`, `subprocess`), Vanilla JavaScript, CSS variables.

**Spec:** User request: "از روی ssh مهاجرت کن به api که بشه پروکسی هم ست کرد" + Ingress UI overhaul.

## Global Constraints
- Pure Python 3 standard library only: NO `pip install`, NO third-party packages.
- Bash scripts must use `set -uo pipefail`, LF line endings, and preserve file inodes when mutating configs.
- Zero external frontend dependencies in RatholeHub UI (pure HTML/CSS/JS).
- Strict command whitelist validation with regexes from `hubcmds.py` to prevent arbitrary command injection.

---

### Task 1: Python Socket Proxy Bridge & Hub Proxy Configuration

**Files:**
- Create: `rathole-manager/ratholehub/ssh_proxy.py`
- Modify: `rathole-manager/ratholehub/hub.py`
- Test: `tests/test_proxy.py`

**Interfaces:**
- Produces: `ssh_proxy.py <proxy_url> <target_host> <target_port>`: stdio-to-socket bridge for SSH `ProxyCommand`.
- Produces in `hub.py`: `get_proxy(server=None)` -> returns proxy URL string or `""`.
- Modifies `_ssh_base(cfg, server)` to include `-o ProxyCommand=...` when proxy is active.

- [ ] **Step 1: Write the failing proxy test**

Create `tests/test_proxy.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_proxy.py`
Expected: FAIL (missing `get_proxy` and ProxyCommand injection).

- [ ] **Step 3: Implement `ssh_proxy.py` stdlib bridge**

Create `rathole-manager/ratholehub/ssh_proxy.py`:
Pure Python stdlib SOCKS5 / HTTP CONNECT tunnel that connects stdin/stdout to the target host via the proxy.
Supports `socks5://`, `socks5h://`, `http://`, `https://`.

- [ ] **Step 4: Update `hub.py` to support `proxy` in config and server inventory**

In `rathole-manager/ratholehub/hub.py`:
1. Add `get_proxy(server=None)`:
   Checks `server.get("proxy")` if present; if `"direct"`, returns `""`. Otherwise falls back to `cfg.get("proxy", "")`.
2. Update `_ssh_base(cfg, server)`:
   If `get_proxy(server)` is non-empty, adds:
   `-o ProxyCommand=python3 "{script_path}" "{proxy_url}" %h %p`
3. Expose proxy setting in `/api/config`: allowed update of `"proxy"`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests/test_proxy.py`
Expected: PASS.

---

### Task 2: Pure-Python stdlib REST Agent Daemon (`ratholeagent.py`)

**Files:**
- Create: `rathole-manager/ratholeagent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Produces: HTTP daemon listening on specified host/port.
- Endpoints:
  - `GET /api/ping` -> `{"ok": true, "version": "...", "role": "iran"|"node", "hostname": "..."}`
  - `POST /api/exec` with Bearer token -> executes whitelisted commands, returns `{"rc": 0, "out": "...", "err": "..."}`.

- [ ] **Step 1: Write test for `ratholeagent.py`**

Create `tests/test_agent.py`:
```python
import unittest, os, sys, json, threading, urllib.request, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../rathole-manager")))
import ratholeagent

class TestAgent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = "test-secret-token-12345678"
        cls.server = ratholeagent.create_agent_server("127.0.0.1", 8999, cls.token, role="node")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_ping_unauthenticated(self):
        req = urllib.request.Request("http://127.0.0.1:8999/api/ping")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("role"), "node")

    def test_exec_unauthorized_without_token(self):
        req = urllib.request.Request("http://127.0.0.1:8999/api/exec", data=b'{"action":"ls"}', headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            self.fail("Should return 401 Unauthorized")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)

    def test_exec_with_valid_token(self):
        req = urllib.request.Request(
            "http://127.0.0.1:8999/api/exec",
            data=json.dumps({"action": "version"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("rc", data)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_agent.py`
Expected: FAIL (missing `ratholeagent.py`).

- [ ] **Step 3: Implement `ratholeagent.py`**

Create `rathole-manager/ratholeagent.py`:
- Use `http.server.ThreadingHTTPServer` and `BaseHTTPRequestHandler`.
- Validate Bearer token using constant-time comparison `hmac.compare_digest`.
- Validate action & args using `hubcmds.build_iran_cmd` / `hubcmds.build_node_cmd` to enforce strict whitelist execution.
- Execute with `subprocess.run(cmd, capture_output=True, text=True, timeout=120)`.
- CLI entrypoint: `python3 ratholeagent.py --port 8089 --token <token> --role <iran|node>`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_agent.py`
Expected: PASS.

---

### Task 3: Dual-Transport Integration in `hub.py` (API & SSH)

**Files:**
- Modify: `rathole-manager/ratholehub/hub.py`
- Modify: `rathole-manager/ratholehub/hubcmds.py`
- Test: `tests/test_hub_transports.py`

**Interfaces:**
- Updates `run_on_server(server, cmd_args, timeout=120)`:
  - If `server.get("transport") == "api"`: routes command to `run_on_agent(server, action, args, timeout)` using `urllib.request` with proxy support.
  - If `server.get("transport") == "ssh"` or unset: routes to SSH subprocess.
- Updates `/api/servers` endpoint: accepts `transport: "api"`, `api_url`, `api_token`, `proxy`.

- [ ] **Step 1: Write failing test for API transport**

Create `tests/test_hub_transports.py`:
```python
import unittest, os, sys, json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../rathole-manager/ratholehub")))
import hub

class TestHubTransports(unittest.TestCase):
    @patch("hub.urllib.request.urlopen")
    def test_run_on_server_dispatches_to_api(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"rc": 0, "out": "rathole 0.5.0", "err": ""}).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

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

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_hub_transports.py`
Expected: FAIL.

- [ ] **Step 3: Implement `run_on_agent` and dispatch in `hub.py`**

In `hub.py`:
- Add `run_on_agent(server, cmd_args, timeout=120)`:
  - Configures `urllib.request.build_opener` with `ProxyHandler` if `get_proxy(server)` is non-empty.
  - Posts JSON `{"cmd": cmd_args}` to `{api_url}/api/exec` with header `Authorization: Bearer {api_token}`.
  - Returns `{"rc": ..., "out": ..., "err": ...}`.
- Update `run_on_server`:
  ```python
  if server.get("transport") == "api":
      return run_on_agent(server, cmd_args, timeout)
  ```
- Validate `api_url` and `api_token` in server management APIs (`POST /api/servers`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests/test_hub_transports.py tests/test_hub.py`
Expected: PASS.

---

### Task 4: UI Support for Hub Proxy & Agent API Registration

**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.js`
- Modify: `rathole-manager/ratholehub/ui/i18n.js`
- Modify: `rathole-manager/ratholehub/ui/app.css`

**Interfaces:**
- Add Server Form: Connection Type selector (`SSH` / `Agent API`).
  - When `Agent API` selected: shows `API URL` (e.g. `http://ip:8089`) and `API Token`.
  - When `SSH` selected: shows Host, Port, User, Password.
  - Both show optional `Proxy` input (e.g. `socks5://127.0.0.1:10808`).
- Hub Strip: shows active Hub Proxy badge if configured, with one-click edit modal.
- Server Cards: shows `🔌 API` or `🔑 SSH` badge + `🛡️ Proxy` badge if proxied.

- [ ] **Step 1: Add i18n tokens for Proxy and Agent API**

In `rathole-manager/ratholehub/ui/i18n.js`:
Add:
`conn_type:'نوع اتصال:', conn_ssh:'SSH (کلید یا پسورد)', conn_api:'Agent API (مستقیم با توکن)',`
`api_url:'آدرس API:', api_token:'توکن امنیتی API:', proxy_opt:'پروکسی اختصاصی (اختیاری):',`
`hub_proxy:'پروکسی هاب:', hub_proxy_hint:'مثال: socks5://127.0.0.1:10808 یا http://127.0.0.1:7890'`

- [ ] **Step 2: Update Add Server form and Server Cards in `app.js`**

In `app.js`:
- Dynamically toggle SSH fields vs API fields based on selected `conn_type`.
- In `addSrv()`: include `transport`, `api_url`, `api_token`, `proxy`.
- In `drawCards()` & `updateCard()`: render badge for transport (`API` vs `SSH`) and proxy indicator.

- [ ] **Step 3: Add Proxy modal in Hub Strip**

Add button to Hub Status bar to view/edit `hub_proxy` via `POST /api/config`.

- [ ] **Step 4: Syntax and UI check**

Run: `node -c rathole-manager/ratholehub/ui/app.js; node -c rathole-manager/ratholehub/ui/i18n.js`
Expected: Clean exit (0).

---

### Task 5: Agent Installer & Service Bootstrap Script

**Files:**
- Create: `rathole-manager/install-agent.sh`
- Modify: `rathole-manager/ratholectl`
- Modify: `rathole-manager/ratholenode`
- Modify: `docs/hub.md`

**Interfaces:**
- `bash rathole-manager/install-agent.sh --port <port> --token <token>`:
  Installs systemd unit `rathole-agent.service` running `python3 /opt/rathole-manager/ratholeagent.py`.
- `ratholectl agent <start|stop|status|token>` and `ratholenode agent <start|stop|status|token>`.

- [ ] **Step 1: Create `install-agent.sh`**

Script that validates root, creates systemd service `/etc/systemd/system/rathole-agent.service`, starts and enables it.

- [ ] **Step 2: Add `agent` subcommand to `ratholectl` and `ratholenode`**

Enable quick commands to start/stop agent or print connection URL and token for adding into RatholeHub.

- [ ] **Step 3: Verification of full workflow**

Run unit tests and end-to-end simulation of mock agent and proxy.
