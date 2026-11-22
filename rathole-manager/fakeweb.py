#!/usr/bin/env python3
"""Per-install deterministic Nginx decoy server for fakeweb (stdlib only)."""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import email.utils
import hashlib
import html
import os
import secrets
import signal
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ANCHOR_TS = 1767225600  # 2026-01-01T00:00:00Z

NGINX_PROFILES = (
    ("nginx/1.18.0 (Ubuntu)", "old"),
    ("nginx/1.22.1", "old"),
    ("nginx/1.24.0 (Ubuntu)", "new"),
    ("nginx/1.26.2", "new"),
    ("nginx", "new"),
)

LEGACY_PLACEHOLDER_MARKERS = (
    "<title>Welcome</title>",
    "<h1>It works!</h1><p>Default web page.</p>",
)

INDEX_HTML_OLD = b"""<!DOCTYPE html>
<html>
<head>
<title>Welcome to nginx!</title>
<style>
    body {
        width: 35em;
        margin: 0 auto;
        font-family: Tahoma, Verdana, Arial, sans-serif;
    }
</style>
</head>
<body>
<h1>Welcome to nginx!</h1>
<p>If you see this page, the nginx web server is successfully installed and
working. Further configuration is required.</p>

<p>For online documentation and support please refer to
<a href="http://nginx.org/">nginx.org</a>.<br/>
Commercial support is available at
<a href="http://nginx.com/">nginx.com</a>.</p>

<p><em>Thank you for using nginx.</em></p>
</body>
</html>
"""

INDEX_HTML_NEW = b"""<!DOCTYPE html>
<html>
<head>
<title>Welcome to nginx!</title>
<style>
html { color-scheme: light dark; }
body { width: 35em; margin: 0 auto;
font-family: Tahoma, Verdana, Arial, sans-serif; }
</style>
</head>
<body>
<h1>Welcome to nginx!</h1>
<p>If you see this page, the nginx web server is successfully installed and
working. Further configuration is required.</p>

<p>For online documentation and support please refer to
<a href="http://nginx.org/">nginx.org</a>.<br/>
Commercial support is available at
<a href="http://nginx.com/">nginx.com</a>.</p>

<p><em>Thank you for using nginx.</em></p>
</body>
</html>
"""


@dataclasses.dataclass(frozen=True)
class DecoyProfile:
    server_banner: str
    variant: str
    body: bytes
    mtime: int
    last_modified: str
    etag: str
    body_404: bytes
    body_405: bytes


def resolve_seed_bytes(seed: str | None = None, seed_file: str | None = None) -> bytes:
    if seed:
        return seed.encode("utf-8")
    target_path = seed_file or os.environ.get("RATHOLE_FAKEWEB_SEED_FILE", "/etc/rathole/fakeweb.seed")
    try:
        if os.path.isfile(target_path):
            with open(target_path, "rb") as f:
                raw = f.read().strip()
            if raw:
                return hashlib.sha256(raw).digest()
        seed_dir = os.path.dirname(target_path)
        if seed_dir:
            os.makedirs(seed_dir, mode=0o700, exist_ok=True)
        tok = secrets.token_hex(32).encode("ascii")
        fd = os.open(target_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, tok + b"\n")
        finally:
            os.close(fd)
        return hashlib.sha256(tok).digest()
    except OSError:
        return os.uname().nodename.encode("utf-8") if hasattr(os, "uname") else b"rathole-fakeweb"


def _error_page(code: int, title: str, server_banner: str) -> bytes:
    html = (
        f"<html>\r\n"
        f"<head><title>{code} {title}</title></head>\r\n"
        f"<body>\r\n"
        f"<center><h1>{code} {title}</h1></center>\r\n"
        f"<hr><center>{server_banner}</center>\r\n"
        f"</body>\r\n"
        f"</html>\r\n"
    )
    return html.encode("utf-8")


def _load_custom_index(root: str) -> tuple[bytes, int] | None:
    if not root:
        return None
    idx = os.path.join(root, "index.html")
    if not os.path.isfile(idx):
        return None
    try:
        st = os.stat(idx)
        with open(idx, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    if not raw:
        return None
    text = raw.decode("utf-8", errors="ignore")
    if all(m in text for m in LEGACY_PLACEHOLDER_MARKERS):
        return None
    return raw, int(st.st_mtime)


def build_profile(root: str = "", seed_file: str | None = None, seed: str | None = None) -> DecoyProfile:
    seed_bytes = resolve_seed_bytes(seed=seed, seed_file=seed_file)
    digest = hashlib.sha256(seed_bytes).digest()
    banner, variant = NGINX_PROFILES[digest[0] % len(NGINX_PROFILES)]
    days_ago = 30 + (int.from_bytes(digest[1:4], "big") % 670)
    secs_off = int.from_bytes(digest[4:7], "big") % 86400
    mtime = ANCHOR_TS - (days_ago * 86400) - secs_off
    body = INDEX_HTML_OLD if variant == "old" else INDEX_HTML_NEW

    custom = _load_custom_index(root)
    if custom is not None:
        body, mtime = custom

    etag = f'"{mtime:x}-{len(body):x}"'
    last_modified = email.utils.formatdate(mtime, usegmt=True)
    return DecoyProfile(
        server_banner=banner,
        variant=variant,
        body=body,
        mtime=mtime,
        last_modified=last_modified,
        etag=etag,
        body_404=_error_page(404, "Not Found", banner),
        body_405=_error_page(405, "Not Allowed", banner),
    )


def _etag_matches(header_val: str, target_etag: str) -> bool:
    target_bare = target_etag.strip()
    if target_bare.startswith("W/"):
        target_bare = target_bare[2:].strip()
    for part in header_val.split(","):
        tok = part.strip()
        if tok == "*":
            return True
        if tok.startswith("W/"):
            tok = tok[2:].strip()
        if tok == target_bare:
            return True
    return False


def _parse_range(range_header: str, total: int) -> tuple[int, int] | None:
    if total <= 0:
        return None
    val = range_header.strip()
    if not val.lower().startswith("bytes="):
        return None
    spec = val[6:].strip()
    if "," in spec or "-" not in spec:
        return None
    start_s, end_s = spec.split("-", 1)
    start_s = start_s.strip()
    end_s = end_s.strip()
    try:
        if not start_s and not end_s:
            return None
        if not start_s:
            suffix = int(end_s)
            if suffix <= 0:
                return None
            start = max(0, total - suffix)
            end = total - 1
        elif not end_s:
            start = int(start_s)
            end = total - 1
        else:
            start = int(start_s)
            end = int(end_s)
    except ValueError:
        return None
    if start < 0 or start > end or start >= total:
        return None
    end = min(end, total - 1)
    return start, end


class DecoyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def version_string(self) -> str:
        return self.server.profile.server_banner

    def log_message(self, format: str, *args) -> None:
        if os.environ.get("FAKEWEB_VERBOSE") == "1":
            super().log_message(format, *args)

    def _send_error_page(
        self,
        status: int | HTTPStatus,
        body: bytes,
        send_body: bool = True,
        phrase: str | None = None,
    ) -> None:
        if phrase is not None:
            self.send_response(int(status), phrase)
        else:
            self.send_response(int(status))
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if send_body:
            self.wfile.write(body)
        self.close_connection = True

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        try:
            status: int | HTTPStatus = HTTPStatus(code)
            phrase = status.phrase
        except ValueError:
            status = int(code)
            phrase = html.escape(message or "Error")
        prof = getattr(self.server, "profile", None)
        banner = getattr(prof, "server_banner", "nginx")
        body = _error_page(int(code), phrase, banner)
        send_body = getattr(self, "command", None) != "HEAD" and int(code) >= 200 and int(code) not in (204, 304)
        self._send_error_page(status, body, send_body=send_body, phrase=phrase)

    def _handle_index(self, send_body: bool) -> None:
        prof: DecoyProfile = self.server.profile
        inm = self.headers.get("If-None-Match")
        if inm and _etag_matches(inm, prof.etag):
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("Last-Modified", prof.last_modified)
            self.send_header("ETag", prof.etag)
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            return

        if not inm:
            ims = self.headers.get("If-Modified-Since")
            if ims:
                try:
                    dt = email.utils.parsedate_to_datetime(ims)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                    if int(dt.timestamp()) >= prof.mtime:
                        self.send_response(HTTPStatus.NOT_MODIFIED)
                        self.send_header("Last-Modified", prof.last_modified)
                        self.send_header("ETag", prof.etag)
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.close_connection = True
                        return
                except Exception:
                    pass

        total = len(prof.body)
        rng = self.headers.get("Range")
        if rng:
            parsed = _parse_range(rng, total)
            if parsed is None:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{total}")
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                return
            start, end = parsed
            chunk = prof.body[start : end + 1]
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.send_header("Last-Modified", prof.last_modified)
            self.send_header("ETag", prof.etag)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Connection", "close")
            self.end_headers()
            if send_body:
                self.wfile.write(chunk)
            self.close_connection = True
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(total))
        self.send_header("Last-Modified", prof.last_modified)
        self.send_header("ETag", prof.etag)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Connection", "close")
        self.end_headers()
        if send_body:
            self.wfile.write(prof.body)
        self.close_connection = True

    def _dispatch_read(self, send_body: bool) -> None:
        req_path = urlparse(self.path).path
        if req_path in ("/", "/index.html"):
            self._handle_index(send_body=send_body)
        else:
            self._send_error_page(HTTPStatus.NOT_FOUND, self.server.profile.body_404, send_body=send_body)

    def do_GET(self) -> None:
        self._dispatch_read(send_body=True)

    def do_HEAD(self) -> None:
        self._dispatch_read(send_body=False)

    def _method_not_allowed(self) -> None:
        self._send_error_page(HTTPStatus.METHOD_NOT_ALLOWED, self.server.profile.body_405, send_body=True)

    def do_POST(self) -> None:
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_OPTIONS(self) -> None:
        self._method_not_allowed()


class DecoyServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], profile: DecoyProfile):
        self.profile = profile
        super().__init__(server_address, DecoyHandler)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    root: str = "/var/www/rathole-fake",
    seed_file: str | None = None,
    seed: str | None = None,
) -> DecoyServer:
    profile = build_profile(root=root, seed_file=seed_file, seed=seed)
    return DecoyServer((host, port), profile)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RatholeEngine deterministic Nginx decoy server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--root", default="/var/www/rathole-fake")
    ap.add_argument("--seed-file", default=None)
    ap.add_argument("--seed", default=None)
    args = ap.parse_args(argv)

    srv = create_server(
        host=args.host,
        port=args.port,
        root=args.root,
        seed_file=args.seed_file,
        seed=args.seed,
    )

    def _stop(_sig, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    try:
        srv.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
