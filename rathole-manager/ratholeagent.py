#!/usr/bin/env python3
"""
ratholeagent — Pure Python stdlib REST API Agent for Rathole server and node management.
Allows managing remote servers over HTTP/HTTPS with token authentication and proxy support,
eliminating direct SSH dependency.
"""
import os, sys, json, hmac, hashlib, subprocess, socket, argparse, signal
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
            try:
                length = int(self.headers.get("Content-Length", 0))
                if 0 < length <= 1048576:
                    self.rfile.read(length)
            except Exception:
                pass
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 1048576:
                raise ValueError("Payload size must be between 1 and 1048576 bytes")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"ok": False, "error": f"Invalid JSON payload: {e}"})
            return

        if not isinstance(data, dict):
            self._send_json(400, {"ok": False, "error": "Payload must be an object"})
            return
        cmd = data.get("cmd")
        if (not isinstance(cmd, list) or not cmd
                or any(not isinstance(arg, str) or "\0" in arg for arg in cmd)) :
            self._send_json(400, {"ok": False, "error": "Field 'cmd' must be a non-empty list"})
            return

        timeout = data.get("timeout", 120)
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            self._send_json(400, {"ok": False, "error": "Timeout must be an integer between 1 and 3600"})
            return
        # timeout-e tashkhisi ra ba subprocess emal kon; binary-e dakheli ham etebarsanji mishavad.
        if cmd[0] == "timeout":
            if len(cmd) < 3 or not cmd[1].isascii() or not cmd[1].isdigit() or not 1 <= int(cmd[1]) <= 3600:
                self._send_json(400, {"ok": False, "error": "Invalid timeout wrapper"})
                return
            timeout = min(timeout, int(cmd[1]))
            cmd = cmd[2:]
        bin_name = os.path.basename(cmd[0])
        # Allow testing with current python executable
        is_cur_py = (cmd[0] == sys.executable)
        if not is_cur_py and bin_name not in ALLOWED_BINARIES:
            self._send_json(403, {"ok": False, "error": f"Binary '{bin_name}' is not permitted"})
            return

        try:
            # session-e joda: timeout bayad bache-process-ha va pipe-haye anha ra ham bebndad.
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, start_new_session=(os.name == "posix")) as p:
                try:
                    out, err = p.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    if os.name == "posix":
                        try:
                            os.killpg(p.pid, getattr(signal, "SIGKILL", 9))
                        except ProcessLookupError:
                            pass
                    else:
                        p.kill()
                    p.communicate()
                    raise
            self._send_json(200, {
                "ok": True,
                "rc": p.returncode,
                "out": out,
                "err": err
            })
        except subprocess.TimeoutExpired:
            self._send_json(200, {"ok": False, "rc": 124, "out": "", "err": "Execution timed out"})
        except Exception as e:
            self._send_json(500, {"ok": False, "rc": 1, "out": "", "err": str(e)})

def create_agent_server(host, port, token, role="node", tls_cert="", tls_key=""):
    class CustomHandler(AgentHandler):
        pass
    CustomHandler.server_token = token
    CustomHandler.server_role = role
    server = ThreadingHTTPServer((host, port), CustomHandler)
    if tls_cert and tls_key and os.path.exists(tls_cert) and os.path.exists(tls_key):
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=tls_cert, keyfile=tls_key)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        sys.stderr.write(f"[agent] TLS/HTTPS enabled using cert={tls_cert}\n")
    return server

def main():
    parser = argparse.ArgumentParser(description="rathole REST Agent")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8089, help="Listen port (default 8089)")
    parser.add_argument("--token", default="", help="Auth Bearer token")
    parser.add_argument("--role", choices=["iran", "node"], default="node", help="Server role")
    parser.add_argument("--tls-cert", default="", help="Path to TLS certificate for HTTPS")
    parser.add_argument("--tls-key", default="", help="Path to TLS private key for HTTPS")
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
        sys.stderr.write("[agent] Authentication token loaded from protected local storage\n")

    tls_cert = args.tls_cert or os.environ.get("RATHOLE_AGENT_TLS_CERT", "")
    tls_key = args.tls_key or os.environ.get("RATHOLE_AGENT_TLS_KEY", "")
    if not tls_cert and os.path.exists("/etc/rathole-agent/cert.pem"):
        tls_cert = "/etc/rathole-agent/cert.pem"
    if not tls_key and os.path.exists("/etc/rathole-agent/key.pem"):
        tls_key = "/etc/rathole-agent/key.pem"

    server = create_agent_server(args.host, args.port, token, args.role, tls_cert, tls_key)
    proto = "https" if (tls_cert and tls_key and os.path.exists(tls_cert) and os.path.exists(tls_key)) else "http"
    sys.stderr.write(f"[agent] Serving on {proto}://{args.host}:{args.port} (role={args.role})\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
