"""HMAC-authenticated length-prefixed JSON control protocol for rathole-tuner."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import socket
import struct
import threading
import time

from . import ALLOWED_ACTIONS, MAX_FRAME_BYTES


class ProtocolError(Exception):
    """Raised on malformed, unauthorized, replayed, or oversized frames."""


def canonical_json_bytes(obj) -> bytes:
    """Serialize any JSON value deterministically as compact UTF-8 bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _compute_hmac(token: str, action: str, ts: int, nonce: str, payload: dict) -> str:
    msg = (f"{ts}|{nonce}|{action}|").encode("utf-8") + canonical_json_bytes(payload)
    return hmac.new(token.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def sign_frame(
    token: str,
    action: str,
    payload: dict | None = None,
    frame_id: str | None = None,
    ts: int | None = None,
    nonce: str | None = None,
) -> dict:
    """Build and HMAC-sign a control frame for an allow-listed action."""
    if not token or not isinstance(token, str):
        raise ProtocolError("missing control token")
    if action not in ALLOWED_ACTIONS:
        raise ProtocolError(f"disallowed control action: {action!r}")
    body = {} if payload is None else payload
    if not isinstance(body, dict):
        raise ProtocolError("payload must be a dict")
    cur_ts = int(time.time()) if ts is None else int(ts)
    cur_nonce = secrets.token_hex(16) if nonce is None else str(nonce)
    fid = secrets.token_hex(8) if frame_id is None else str(frame_id)
    sig = _compute_hmac(token, action, cur_ts, cur_nonce, body)
    return {
        "id": fid,
        "action": action,
        "ts": cur_ts,
        "nonce": cur_nonce,
        "payload": body,
        "hmac": sig,
    }


def _prune_nonces(seen_nonces: dict, now_ts: int, window_s: int) -> None:
    cutoff = now_ts - window_s
    expired = [k for k, v in seen_nonces.items() if v < cutoff]
    for k in expired:
        del seen_nonces[k]


def verify_frame(
    token: str,
    frame: dict,
    seen_nonces: dict | None = None,
    now: int | None = None,
    window_s: int = 600,
) -> dict:
    """Verify action allow-list, timestamp replay window, nonce uniqueness, and HMAC."""
    if not token or not isinstance(token, str):
        raise ProtocolError("missing control token")
    if not isinstance(frame, dict):
        raise ProtocolError("frame must be a dict")
    action = frame.get("action")
    if action not in ALLOWED_ACTIONS:
        raise ProtocolError(f"disallowed control action: {action!r}")
    ts = frame.get("ts")
    nonce = frame.get("nonce")
    payload = frame.get("payload")
    sig = frame.get("hmac")
    if type(ts) is not int or not isinstance(nonce, str) or len(nonce) < 8 or len(nonce) > 128:
        raise ProtocolError("invalid timestamp or nonce")
    if not isinstance(payload, dict) or not isinstance(sig, str):
        raise ProtocolError("invalid payload or hmac field")

    cur_now = int(time.time()) if now is None else int(now)
    if abs(cur_now - ts) > window_s:
        raise ProtocolError("frame timestamp outside replay window")

    expected = _compute_hmac(token, action, ts, nonce, payload)
    if not hmac.compare_digest(expected, sig):
        raise ProtocolError("invalid frame HMAC")

    if seen_nonces is not None:
        _prune_nonces(seen_nonces, cur_now, window_s)
        if nonce in seen_nonces:
            raise ProtocolError("replayed nonce")
        seen_nonces[nonce] = cur_now
    return frame


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    chunks = []
    got = 0
    while got < n:
        part = sock.recv(n - got)
        if not part:
            raise ProtocolError("connection closed before frame completed")
        chunks.append(part)
        got += len(part)
    return b"".join(chunks)


def send_frame(sock: socket.socket, frame: dict, max_bytes: int = MAX_FRAME_BYTES) -> None:
    """Serialize frame JSON and transmit with a 4-byte uint32 big-endian length header."""
    raw = canonical_json_bytes(frame)
    if len(raw) > max_bytes:
        raise ProtocolError(f"outbound frame exceeds limit ({len(raw)} > {max_bytes})")
    sock.sendall(struct.pack("!I", len(raw)) + raw)


def recv_frame(sock: socket.socket, max_bytes: int = MAX_FRAME_BYTES) -> dict:
    """Receive one bounded length-prefixed JSON frame from socket."""
    hdr = _recv_exact(sock, 4)
    (length,) = struct.unpack("!I", hdr)
    if length == 0 or length > max_bytes:
        raise ProtocolError(f"frame size out of bounds: {length} (max {max_bytes})")
    raw = _recv_exact(sock, length)
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ProtocolError(f"invalid JSON frame: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProtocolError("decoded frame must be a JSON object")
    return obj


class ControlClient:
    """Persistent authenticated TCP client to talk to a TunerResponder."""

    def __init__(self, host: str, port: int, token: str, timeout: float = 15.0):
        self.host = host
        self.port = int(port)
        self.token = token
        self.timeout = float(timeout)
        self._sock: socket.socket | None = None
        self._seen_nonces: dict[str, int] = {}
        self._io_lock = threading.Lock()

    def connect(self) -> "ControlClient":
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            sock.settimeout(self.timeout)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass
            self._sock = sock
            return self
        except OSError as exc:
            raise ConnectionError(
                f"Cannot reach peer responder at {self.host}:{self.port} ({exc}). "
                f"Check firewall/security-group for TCP {self.port} and TCP/UDP {self.port + 1}."
            ) from exc

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def call(self, action: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        with self._io_lock:
            max_attempts = 1 if action == "shutdown" else 3
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                if self._sock is None:
                    self.connect()
                old_to = self._sock.gettimeout()
                if timeout is not None:
                    self._sock.settimeout(float(timeout))
                try:
                    req = sign_frame(self.token, action, payload or {})
                    send_frame(self._sock, req)
                    resp = recv_frame(self._sock)
                    verify_frame(self.token, resp, seen_nonces=self._seen_nonces)
                    if resp.get("id") != req["id"]:
                        raise ProtocolError("mismatched response frame id")
                    return resp.get("payload", {})
                except (socket.timeout, TimeoutError, OSError, ProtocolError) as exc:
                    last_exc = exc
                    self.close()
                    if action == "shutdown" or attempt >= max_attempts - 1:
                        raise
                    time.sleep(0.3)
                finally:
                    if self._sock is not None and timeout is not None:
                        try:
                            self._sock.settimeout(old_to)
                        except OSError:
                            pass
            if last_exc is not None:
                raise last_exc
            raise ProtocolError("control call failed")
