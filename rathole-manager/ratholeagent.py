#!/usr/bin/env python3
"""
ratholeagent — Pure Python stdlib REST & Reverse WebSocket Agent for Rathole server and node management.
Allows managing remote servers either over inbound HTTP/HTTPS or outbound persistent Reverse WebSocket
(zero open ports required on filtered foreign nodes).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time

for _cand_dir in (os.path.dirname(os.path.abspath(__file__)), "/usr/local/share/rathole"):
    if _cand_dir and _cand_dir not in sys.path and os.path.isdir(_cand_dir):
        sys.path.insert(0, _cand_dir)

import wsutil

AGENT_VERSION = "2.0.0"
ALLOWED_BINARIES = {
    "ratholectl", "ratholenode", "systemctl", "journalctl", "jq", "tail"
}


def validate_and_exec_cmd(cmd, timeout=120, allow_test_python=False):
    """Validate argv allow-list and execute without a shell; returns (http_status, response_dict)."""
    if (not isinstance(cmd, list) or not cmd
            or any(not isinstance(arg, str) or "\0" in arg for arg in cmd)):
        return 400, {"ok": False, "error": "Field 'cmd' must be a non-empty list"}

    if type(timeout) is not int or not 1 <= timeout <= 3600:
        return 400, {"ok": False, "error": "Timeout must be an integer between 1 and 3600"}

    # timeout-e tashkhisi ra ba subprocess emal kon; binary-e dakheli ham etebarsanji mishavad.
    if cmd[0] == "timeout":
        if len(cmd) < 3 or not cmd[1].isascii() or not cmd[1].isdigit() or not 1 <= int(cmd[1]) <= 3600:
            return 400, {"ok": False, "error": "Invalid timeout wrapper"}
        timeout = min(timeout, int(cmd[1]))
        cmd = cmd[2:]

    is_cur_py = bool(allow_test_python and cmd[0] == sys.executable)
    if not is_cur_py:
        if "/" in cmd[0] or "\\" in cmd[0] or cmd[0] not in ALLOWED_BINARIES:
            return 403, {"ok": False, "error": f"Binary '{os.path.basename(cmd[0])}' is not permitted"}

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
        return 200, {
            "ok": True,
            "rc": p.returncode,
            "out": out,
            "err": err,
        }
    except subprocess.TimeoutExpired:
        return 200, {"ok": False, "rc": 124, "out": "", "err": "Execution timed out"}
    except Exception as e:
        return 500, {"ok": False, "rc": 1, "out": "", "err": str(e)}


def detect_local_egress_ip():
    """Best-effort local egress IP lookup without emitting network packets."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1.0)
            s.connect(("1.1.1.1", 80))
            ip = s.getsockname()[0]
        if ip and not ip.startswith(("127.", "0.0.0.0")):
            return ip
    except OSError:
        pass
    return ""


class AgentHandler(BaseHTTPRequestHandler):
    server_token = ""
    server_role = "node"
    allow_test_python = False
    timeout = 30

    def log_message(self, format, *args):
        # Mute verbose access logs to stdout; write only errors
        if len(args) >= 2 and str(args[1]).startswith(('4', '5')):
            sys.stderr.write(f"[agent] {self.address_string()} - {format % args}\n")

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _auth(self):
        if not self.server_token:
            self._send_json(503, {"ok": False, "error": "Agent token not configured"})
            return False
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
                "hostname": socket.gethostname(),
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
        timeout = data.get("timeout", 120)
        status, payload = validate_and_exec_cmd(
            cmd, timeout=timeout, allow_test_python=self.allow_test_python
        )
        self._send_json(status, payload)


class _AgentHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64
    tls_ctx = None

    def finish_request(self, request, client_address):
        try:
            request.settimeout(30)
            wsutil.enable_tcp_keepalive(request, idle=20, interval=10, count=3)
            if self.tls_ctx is not None:
                request = self.tls_ctx.wrap_socket(request, server_side=True)
        except OSError:
            try:
                request.close()
            except OSError:
                pass
            return
        super().finish_request(request, client_address)


def create_agent_server(host, port, token, role="node", tls_cert="", tls_key="", allow_test_python=False):
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Agent authentication token must be non-empty")
    class CustomHandler(AgentHandler):
        pass
    CustomHandler.server_token = token.strip()
    CustomHandler.server_role = role
    CustomHandler.allow_test_python = bool(allow_test_python)
    server = _AgentHTTPServer((host, port), CustomHandler)
    if tls_cert and tls_key and os.path.exists(tls_cert) and os.path.exists(tls_key):
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=tls_cert, keyfile=tls_key)
        server.tls_ctx = ctx
        sys.stderr.write(f"[agent] TLS/HTTPS enabled using cert={tls_cert}\n")
    return server


class ReverseAgentClient:
    """Persistent outbound RFC 6455 WebSocket client executing validated Hub commands."""

    def __init__(
        self,
        url,
        name,
        token,
        role="node",
        insecure_ssl=False,
        proxy="",
        ping_interval=20,
        allow_test_python=False,
        public_ip="",
    ):
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Reverse WebSocket URL must be non-empty")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Agent name must be non-empty for reverse mode")
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Agent authentication token must be non-empty")
        self.url = url.strip()
        self.name = name.strip()
        self.token = token.strip()
        self.role = role
        self.insecure_ssl = bool(insecure_ssl)
        self.proxy = str(proxy or "").strip()
        self.ping_interval = max(5, int(ping_interval))
        self.allow_test_python = bool(allow_test_python)
        self.public_ip = str(public_ip or "").strip()
        self.stop_event = threading.Event()
        self.connected_event = threading.Event()
        self._ws = None
        self._ws_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=16)

    def _handle_exec(self, ws, msg):
        req_id = msg.get("id")
        cmd = msg.get("cmd")
        timeout = msg.get("timeout", 120)
        status, res = validate_and_exec_cmd(
            cmd, timeout=timeout, allow_test_python=self.allow_test_python
        )
        rc = res["rc"] if "rc" in res else (1 if status >= 400 else 0)
        err_msg = res.get("err") or res.get("error") or ""
        reply = {
            "type": "result",
            "id": req_id,
            "status": status,
            "ok": bool(res.get("ok")),
            "rc": rc,
            "out": res.get("out", ""),
            "err": err_msg,
        }
        try:
            ws.send_json(reply)
        except (wsutil.WSError, OSError):
            pass

    def run_once(self):
        ws = wsutil.ws_connect(
            self.url,
            headers={
                "X-Agent-Name": self.name,
                "Authorization": f"Bearer {self.token}",
            },
            timeout=15.0,
            insecure_ssl=self.insecure_ssl,
            proxy=self.proxy,
        )
        with self._ws_lock:
            self._ws = ws
        try:
            ws.send_json({
                "type": "hello",
                "role": self.role,
                "version": AGENT_VERSION,
                "hostname": socket.gethostname(),
                "public_ip": self.public_ip or detect_local_egress_ip(),
            })
            self.connected_event.set()
            ws.settimeout(float(self.ping_interval))
            stale_limit = self.ping_interval * 3.0 + 15.0
            while not self.stop_event.is_set():
                try:
                    raw = ws.recv_message()
                except socket.timeout:
                    if time.monotonic() - ws.last_rx > stale_limit:
                        raise wsutil.WSError("keepalive timeout")
                    ws.send_ping(b"agent-hb")
                    continue
                if raw is None:
                    break
                if not isinstance(raw, str):
                    continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(msg, dict) and msg.get("type") == "exec" and isinstance(msg.get("id"), str):
                    self._pool.submit(self._handle_exec, ws, msg)
        finally:
            self.connected_event.clear()
            with self._ws_lock:
                if self._ws is ws:
                    self._ws = None
            ws.close()

    def run_forever(self):
        delay = 1.0
        while not self.stop_event.is_set():
            t0 = time.monotonic()
            try:
                self.run_once()
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                sys.stderr.write(f"[agent] reverse ws disconnected ({exc}); reconnecting...\n")
            lived = time.monotonic() - t0
            if self.stop_event.is_set():
                break
            if lived >= 10.0:
                delay = 1.0
            self.stop_event.wait(delay)
            delay = min(15.0, delay * 2.0) if lived < 10.0 else 1.0

    def stop(self):
        self.stop_event.set()
        with self._ws_lock:
            ws = self._ws
            self._ws = None
        if ws is not None:
            ws.send_close(1000, "shutdown")
            ws.close()
        self._pool.shutdown(wait=False)


def _load_or_create_token(cli_token):
    token = (cli_token or os.environ.get("RATHOLE_AGENT_TOKEN", "")).strip()
    if token:
        return token
    token_path = "/etc/rathole-agent/token"
    if os.path.exists(token_path):
        with open(token_path, "r", encoding="utf-8") as f:
            token = f.read().strip()
        if not token:
            sys.stderr.write("[agent] ERROR: Authentication token file is empty\n")
            sys.exit(1)
    else:
        token = hashlib.sha256(os.urandom(32)).hexdigest()
        try:
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(token)
            os.chmod(token_path, 0o600)
        except Exception:
            pass
    sys.stderr.write("[agent] Authentication token loaded from protected local storage\n")
    return token


def main():
    parser = argparse.ArgumentParser(description="rathole REST & Reverse WebSocket Agent")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8089, help="Listen port (default 8089)")
    parser.add_argument("--token", default="", help="Auth Bearer token")
    parser.add_argument("--role", choices=["iran", "node"], default="node", help="Server role")
    parser.add_argument("--tls-cert", default="", help="Path to TLS certificate for HTTPS")
    parser.add_argument("--tls-key", default="", help="Path to TLS private key for HTTPS")
    parser.add_argument("--reverse", default="", help="Outbound Hub WebSocket URL (e.g. wss://dom/hub/ws/agent)")
    parser.add_argument("--name", default="", help="Registered server name in Hub (required with --reverse)")
    parser.add_argument("--insecure-ssl", action="store_true", help="Skip TLS certificate verification in reverse mode")
    parser.add_argument("--proxy", default="", help="Optional HTTP proxy URL for reverse mode")
    parser.add_argument("--ping-interval", type=int, default=20, help="WebSocket keepalive ping interval seconds")
    args = parser.parse_args()

    token = _load_or_create_token(args.token)

    rev_url = (args.reverse or os.environ.get("RATHOLE_AGENT_REVERSE_URL", "")).strip()
    if rev_url:
        rev_name = (args.name or os.environ.get("RATHOLE_AGENT_NAME", "")).strip()
        if not rev_name:
            sys.stderr.write("[agent] ERROR: --name is required when using --reverse\n")
            sys.exit(1)
        insecure = bool(args.insecure_ssl or os.environ.get("RATHOLE_AGENT_INSECURE_SSL", "") == "1")
        proxy = (args.proxy or os.environ.get("RATHOLE_AGENT_PROXY", "")).strip()
        client = ReverseAgentClient(
            url=rev_url,
            name=rev_name,
            token=token,
            role=args.role,
            insecure_ssl=insecure,
            proxy=proxy,
            ping_interval=args.ping_interval,
        )
        def _stop_handler(_signum, _frame):
            client.stop()
        for sig_name in ("SIGTERM", "SIGINT"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                signal.signal(sig, _stop_handler)
        sys.stderr.write(f"[agent] Reverse WS mode connecting to {rev_url} as '{rev_name}' (role={args.role})\n")
        try:
            client.run_forever()
        except KeyboardInterrupt:
            client.stop()
        return

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
