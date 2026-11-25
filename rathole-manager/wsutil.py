#!/usr/bin/env python3
"""
wsutil — Pure Python stdlib RFC 6455 WebSocket helpers (server accept + client connect).
Supports ws://, wss:// (SNI + optional insecure_ssl), HTTP CONNECT proxy, ping/pong,
TCP keepalive, and concurrent thread-safe JSON/text frame delivery.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import ssl
import struct
import threading
import time
from urllib.parse import unquote, urlparse

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT = 0x0
OP_TEXT = 0x1
OP_BIN = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

MAX_FRAME_BYTES = 4 * 1024 * 1024
_MAX_HTTP_HDR_BYTES = 16 * 1024


class WSError(Exception):
    """Raised on WebSocket handshake, framing, or transport errors."""


def enable_tcp_keepalive(sock: socket.socket, idle: int = 20, interval: int = 10, count: int = 3) -> None:
    """Enable TCP_NODELAY and aggressive TCP keepalives (portable across OSes)."""
    if sock is None:
        return
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        pass
    for opt_name, val in (
        ("TCP_KEEPIDLE", idle),
        ("TCP_KEEPINTVL", interval),
        ("TCP_KEEPCNT", count),
    ):
        opt = getattr(socket, opt_name, None)
        if opt is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, opt, int(val))
            except OSError:
                pass


def _xor_mask(data: bytes, mask_key: bytes) -> bytes:
    """Fast RFC 6455 XOR masking/unmasking for arbitrary payload sizes."""
    n = len(data)
    if n == 0:
        return b""
    repeated = (mask_key * ((n + 3) // 4))[:n]
    masked_int = int.from_bytes(data, "big") ^ int.from_bytes(repeated, "big")
    return masked_int.to_bytes(n, "big")


def _compute_accept(sec_key: str) -> str:
    digest = hashlib.sha1((sec_key.strip() + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


class WSConn:
    """Thread-safe RFC 6455 WebSocket connection wrapper."""

    def __init__(
        self,
        sock: socket.socket,
        reader=None,
        prefill: bytes = b"",
        mask_outgoing: bool = False,
    ) -> None:
        self.sock = sock
        self.reader = reader
        self._buf = bytearray(prefill or b"")
        self.mask_outgoing = bool(mask_outgoing)
        self.write_lock = threading.Lock()
        self.last_rx = time.monotonic()
        self.closed = False

    def settimeout(self, secs: float | None) -> None:
        try:
            self.sock.settimeout(secs)
        except OSError:
            pass

    def _read_exact(self, n: int) -> bytes:
        if n <= 0:
            return b""
        out = bytearray()
        if self._buf:
            take = min(n, len(self._buf))
            out.extend(self._buf[:take])
            del self._buf[:take]
        while len(out) < n:
            need = n - len(out)
            if self.reader is not None:
                chunk = self.reader.read(need)
            else:
                chunk = self.sock.recv(need)
            if not chunk:
                raise WSError("connection closed")
            out.extend(chunk)
        return bytes(out)

    def _build_frame(self, opcode: int, payload: bytes, fin: bool = True) -> bytes:
        n = len(payload)
        if n > MAX_FRAME_BYTES:
            raise WSError(f"outgoing frame too large: {n} > {MAX_FRAME_BYTES}")
        b0 = (0x80 if fin else 0x00) | (opcode & 0x0F)
        mask_bit = 0x80 if self.mask_outgoing else 0x00
        header = bytearray()
        header.append(b0)
        if n < 126:
            header.append(mask_bit | n)
        elif n < 65536:
            header.append(mask_bit | 126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack("!Q", n))
        if self.mask_outgoing:
            mask_key = os.urandom(4)
            header.extend(mask_key)
            return bytes(header) + _xor_mask(payload, mask_key)
        return bytes(header) + payload

    def send_frame(self, opcode: int, payload: bytes = b"") -> None:
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("payload must be bytes")
        raw = bytes(payload)
        frame = self._build_frame(opcode, raw, fin=True)
        with self.write_lock:
            if self.closed:
                raise WSError("connection closed")
            try:
                self.sock.sendall(frame)
            except OSError as exc:
                self.closed = True
                raise WSError(f"send failed: {exc}") from exc

    def send_text(self, text: str) -> None:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        self.send_frame(OP_TEXT, text.encode("utf-8"))

    def send_json(self, obj) -> None:
        self.send_text(json.dumps(obj, ensure_ascii=False))

    def send_ping(self, payload: bytes = b"hb") -> None:
        self.send_frame(OP_PING, payload[:125])

    def send_pong(self, payload: bytes = b"") -> None:
        self.send_frame(OP_PONG, payload[:125])

    def send_close(self, code: int = 1000, reason: str = "") -> None:
        body = struct.pack("!H", int(code)) + reason.encode("utf-8", errors="ignore")[:123]
        try:
            frame = self._build_frame(OP_CLOSE, body, fin=True)
            with self.write_lock:
                if not self.closed:
                    self.sock.sendall(frame)
        except OSError:
            pass
        finally:
            self.closed = True

    def _read_single_frame(self) -> tuple[bool, int, bytes]:
        hdr = self._read_exact(2)
        b0, b1 = hdr[0], hdr[1]
        fin = bool(b0 & 0x80)
        if b0 & 0x70:
            raise WSError("unsupported WebSocket reserved bits")
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        if length > MAX_FRAME_BYTES:
            raise WSError(f"incoming frame exceeds limit: {length} > {MAX_FRAME_BYTES}")
        if opcode >= 0x8 and (not fin or length > 125):
            raise WSError("invalid WebSocket control frame")
        mask_key = self._read_exact(4) if masked else b""
        payload = self._read_exact(length)
        if masked:
            payload = _xor_mask(payload, mask_key)
        self.last_rx = time.monotonic()
        return fin, opcode, payload

    def recv_message(self) -> str | bytes | None:
        """Read next complete text/binary message; handles ping/pong/close & fragmentation."""
        frag_opcode: int | None = None
        frag_buf = bytearray()
        while True:
            fin, opcode, payload = self._read_single_frame()
            if opcode == OP_PING:
                try:
                    self.send_pong(payload)
                except WSError:
                    pass
                continue
            if opcode == OP_PONG:
                continue
            if opcode == OP_CLOSE:
                if not self.closed:
                    self.send_close(1000)
                self.closed = True
                return None

            if opcode in (OP_TEXT, OP_BIN):
                if frag_opcode is not None:
                    raise WSError("unexpected data frame while fragmented message incomplete")
                if fin:
                    if opcode == OP_TEXT:
                        return payload.decode("utf-8")
                    return payload
                frag_opcode = opcode
                frag_buf.extend(payload)
                if len(frag_buf) > MAX_FRAME_BYTES:
                    raise WSError("fragmented message exceeds maximum frame size")
                continue

            if opcode == OP_CONT:
                if frag_opcode is None:
                    raise WSError("unexpected continuation frame")
                if len(frag_buf) + len(payload) > MAX_FRAME_BYTES:
                    raise WSError("fragmented message exceeds maximum frame size")
                frag_buf.extend(payload)
                if fin:
                    data = bytes(frag_buf)
                    op = frag_opcode
                    frag_opcode = None
                    frag_buf.clear()
                    if op == OP_TEXT:
                        return data.decode("utf-8")
                    return data
                continue

            raise WSError(f"unsupported opcode: {opcode}")

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def ws_accept_handshake(handler) -> WSConn:
    """Validate incoming HTTP Upgrade request and complete RFC 6455 101 Switching Protocols."""
    upgrade = str(handler.headers.get("Upgrade", "") or "").strip()
    sec_key = str(handler.headers.get("Sec-WebSocket-Key", "") or "").strip()
    if "websocket" not in upgrade.lower() or not sec_key:
        raise WSError("missing WebSocket Upgrade headers")

    accept = _compute_accept(sec_key)
    enable_tcp_keepalive(handler.connection)
    resp = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    ).encode("ascii")
    handler.wfile.write(resp)
    handler.wfile.flush()
    handler.close_connection = True
    return WSConn(handler.connection, reader=handler.rfile, mask_outgoing=False)


def _format_host_header(hostname: str, port: int, default_port: int) -> str:
    h = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    if port != default_port:
        return f"{h}:{port}"
    return h


def _read_http_head(sock: socket.socket) -> tuple[bytes, bytes]:
    buf = bytearray()
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise WSError("connection closed during HTTP handshake")
        buf.extend(chunk)
        if len(buf) > _MAX_HTTP_HDR_BYTES:
            raise WSError("HTTP handshake header exceeds 16 KiB limit")
    idx = buf.index(b"\r\n\r\n")
    return bytes(buf[:idx]), bytes(buf[idx + 4:])


def _open_proxy_tunnel(proxy_url: str, target_host: str, target_port: int, timeout: float) -> socket.socket:
    parsed = urlparse(proxy_url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise WSError(f"unsupported proxy scheme '{scheme}' (use http:// proxy)")
    if not parsed.hostname:
        raise WSError("invalid proxy hostname")
    p_port = parsed.port or (443 if scheme == "https" else 80)
    sock = socket.create_connection((parsed.hostname, p_port), timeout=timeout)
    try:
        if scheme == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=parsed.hostname)
        tgt = _format_host_header(target_host, target_port, -1)
        lines = [
            f"CONNECT {tgt} HTTP/1.1",
            f"Host: {tgt}",
        ]
        if parsed.username is not None:
            user = unquote(parsed.username)
            pw = unquote(parsed.password or "")
            creds = base64.b64encode(f"{user}:{pw}".encode("utf-8")).decode("ascii")
            lines.append(f"Proxy-Authorization: Basic {creds}")
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
        head, _ = _read_http_head(sock)
        status_line = head.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
        parts = status_line.split(" ", 2)
        if len(parts) < 2 or parts[1] != "200":
            raise WSError(f"proxy CONNECT rejected: {status_line}")
        return sock
    except Exception:
        try:
            sock.close()
        except OSError:
            pass
        raise


def ws_connect(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    insecure_ssl: bool = False,
    proxy: str = "",
) -> WSConn:
    """Connect to a ws:// or wss:// endpoint and perform RFC 6455 client handshake."""
    raw_url = str(url or "").strip()
    if any(ord(ch) < 32 for ch in raw_url):
        raise WSError("control characters not allowed in WebSocket URL")
    parsed = urlparse(raw_url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("ws", "wss") or not parsed.hostname:
        raise WSError(f"invalid WebSocket URL: {raw_url!r}")

    hostname = parsed.hostname
    default_port = 443 if scheme == "wss" else 80
    try:
        port = parsed.port or default_port
    except ValueError as exc:
        raise WSError(f"invalid port in WebSocket URL: {exc}") from exc

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    px = str(proxy or "").strip()
    if px.lower() in ("direct", "none", "off"):
        px = ""
    if px:
        sock = _open_proxy_tunnel(px, hostname, port, timeout=timeout)
    else:
        sock = socket.create_connection((hostname, port), timeout=timeout)

    try:
        if scheme == "wss":
            ctx = ssl.create_default_context()
            if insecure_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(sock, server_hostname=hostname)

        enable_tcp_keepalive(sock)
        sec_key = base64.b64encode(os.urandom(16)).decode("ascii")
        req_lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {_format_host_header(hostname, port, default_port)}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {sec_key}",
            "Sec-WebSocket-Version: 13",
        ]
        for hk, hv in (headers or {}).items():
            ks, vs = str(hk), str(hv)
            if any(c in ks or c in vs for c in ("\r", "\n", "\0")):
                raise WSError("invalid characters in WebSocket request header")
            req_lines.append(f"{ks}: {vs}")
        sock.sendall(("\r\n".join(req_lines) + "\r\n\r\n").encode("utf-8"))

        head_bytes, leftover = _read_http_head(sock)
        head_lines = head_bytes.decode("latin-1", errors="replace").split("\r\n")
        status_line = head_lines[0] if head_lines else ""
        parts = status_line.split(" ", 2)
        if len(parts) < 2 or parts[1] != "101":
            raise WSError(f"WebSocket upgrade failed: {status_line}")

        resp_hdrs: dict[str, str] = {}
        for ln in head_lines[1:]:
            if ":" in ln:
                k, v = ln.split(":", 1)
                resp_hdrs[k.strip().lower()] = v.strip()

        expected_accept = _compute_accept(sec_key)
        got_accept = resp_hdrs.get("sec-websocket-accept", "")
        if not hmac.compare_digest(got_accept.encode("ascii"), expected_accept.encode("ascii")):
            raise WSError("invalid Sec-WebSocket-Accept from server")

        return WSConn(sock, prefill=leftover, mask_outgoing=True)
    except Exception:
        try:
            sock.close()
        except OSError:
            pass
        raise
