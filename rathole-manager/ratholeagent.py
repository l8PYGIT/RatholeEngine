#!/usr/bin/env python3
"""
ratholeagent — Pure Python stdlib REST API Agent for Rathole server and node management.
Allows managing remote servers over HTTP/HTTPS with token authentication and proxy support,
eliminating direct SSH dependency.
"""
import os, sys, json, hmac, hashlib, subprocess, socket, argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AGENT_VERSION = "1.0.0"
ALLOWED_BINARIES = {
    "ratholectl", "ratholenode", "bash", "python3", "python",
    "systemctl", "journalctl", "curl", "jq", "cat", "tail", "ls"
}

class AgentHandler(BaseHTTPRequestHandler):
    server_token = ""
    server_role = "node"

    def log_message(self, format, *args):
        # Mute verbose access logs to stdout; write only errors
        if args and str(args[0]).startswith(('4', '5')):
            sys.stderr.write(f"[agent] {self.address_string()} - {format % args}\n")

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self):
        auth_hdr = self.headers.get("Authorization", "")
        if not auth_hdr:
            self._send_json(401, {"ok": False, "error": "Missing Authorization header"})
            return False
        parts = auth_hdr.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            self._send_json(401, {"ok": False, "error": "Invalid Authorization scheme"})
            return False
        token = parts[1].strip()
        if not hmac.compare_digest(token.encode(), self.server_token.encode()):
            self._send_json(403, {"ok": False, "error": "Invalid token"})
            return False
        return True

    def do_GET(self):
        if self.path == "/api/ping":
            self._send_json(200, {
                "ok": True,
                "role": self.server_role,
                "version": AGENT_VERSION,
                "hostname": socket.gethostname()
            })
            return
        self._send_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        if self.path != "/api/exec":
            self._send_json(404, {"ok": False, "error": "Not found"})
            return
        if not self._auth():
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"ok": False, "error": f"Invalid JSON payload: {e}"})
            return

        cmd = data.get("cmd")
        if not cmd or not isinstance(cmd, list):
            self._send_json(400, {"ok": False, "error": "Field 'cmd' must be a non-empty list"})
            return

        bin_name = os.path.basename(str(cmd[0]))
        # Allow testing with current python executable
        is_cur_py = (cmd[0] == sys.executable)
        if not is_cur_py and bin_name not in ALLOWED_BINARIES:
            self._send_json(403, {"ok": False, "error": f"Binary '{bin_name}' is not permitted"})
            return

        timeout = int(data.get("timeout", 120))
        try:
            p = subprocess.run(
                [str(x) for x in cmd],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            self._send_json(200, {
                "ok": True,
                "rc": p.returncode,
                "out": p.stdout,
                "err": p.stderr
            })
        except subprocess.TimeoutExpired:
            self._send_json(200, {"ok": False, "rc": 124, "out": "", "err": "Execution timed out"})
        except Exception as e:
            self._send_json(500, {"ok": False, "rc": 1, "out": "", "err": str(e)})

def create_agent_server(host, port, token, role="node"):
    class CustomHandler(AgentHandler):
        pass
    CustomHandler.server_token = token
    CustomHandler.server_role = role
    return ThreadingHTTPServer((host, port), CustomHandler)

def main():
    parser = argparse.ArgumentParser(description="rathole REST Agent")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8089, help="Listen port (default 8089)")
    parser.add_argument("--token", default="", help="Auth Bearer token")
    parser.add_argument("--role", choices=["iran", "node"], default="node", help="Server role")
    args = parser.parse_args()

    token = args.token or os.environ.get("RATHOLE_AGENT_TOKEN", "")
    if not token:
        # Check /etc/rathole-agent/token
        token_path = "/etc/rathole-agent/token"
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
        else:
            token = hashlib.sha256(os.urandom(32)).hexdigest()
            try:
                os.makedirs(os.path.dirname(token_path), exist_ok=True)
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(token)
            except Exception:
                pass
        sys.stderr.write(f"[agent] Using token: {token}\n")

    server = create_agent_server(args.host, args.port, token, args.role)
    sys.stderr.write(f"[agent] Serving on {args.host}:{args.port} (role={args.role})\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
