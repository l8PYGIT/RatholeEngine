#!/usr/bin/env python3
# tg_relay.py — ersal-e payam-haye Telegram az masir-haye mokhtalef (direct / proxy / SSH auto-relay).
# Faghat stdlib Python 3; hich dependency khareji nadarad.
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

try:
    import ssh_proxy
except ImportError:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    import ssh_proxy


RELAY_MODES = ("auto", "direct", "proxy", "ssh_auto")
RE_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}\Z")
RE_SSH_USER = re.compile(r"^[A-Za-z0-9._-]{1,64}\Z")
_RE_URL_CREDS = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/\s@]+@")
_RE_BOT_TOKEN = re.compile(r"\bbot[0-9]{5,}:[A-Za-z0-9_-]{20,}")


class TelegramApiError(RuntimeError):
    """Telegram API returned an explicit JSON error (transport succeeded)."""

    def __init__(self, status, data):
        desc = ""
        if isinstance(data, dict):
            desc = str(data.get("description") or data.get("raw") or "")
        super().__init__(f"telegram API error {status}: {desc}".strip())
        self.status = status
        self.data = data


def _valid_host(host):
    if not host:
        return False
    if RE_HOST.match(host):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def valid_proxy_url(value):
    if not value:
        return True
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v:
        return True
    if any(ord(c) < 32 or ord(c) == 127 or c.isspace() for c in v):
        return False
    try:
        p = urlparse(v)
        port = p.port
    except ValueError:
        return False
    scheme = (p.scheme or "").lower()
    if scheme not in ("http", "https", "socks5", "socks5h"):
        return False
    if not _valid_host(p.hostname or ""):
        return False
    if port is not None and not (1 <= port <= 65535):
        return False
    if p.path not in ("", "/") or p.query or p.fragment:
        return False
    return True


def redact_secrets(text, secrets_list=()):
    s = str(text or "")
    s = _RE_URL_CREDS.sub(r"\1***@", s)
    s = _RE_BOT_TOKEN.sub("bot***", s)
    for sec in secrets_list or ():
        if not isinstance(sec, str):
            continue
        sec_s = sec.strip()
        if not sec_s:
            continue
        if "://" in sec_s:
            try:
                p = urlparse(sec_s)
                if p.password and len(p.password) >= 3:
                    s = s.replace(p.password, "***")
                if p.username and p.password:
                    s = s.replace(f"{p.username}:{p.password}@", "***@")
            except Exception:
                pass
        else:
            s = s.replace(sec_s, "***")
    return s


def _open_tunneled_socket(target_host, target_port, proxy_url="", timeout=15, proxy_ssl_context=None):
    port_i = int(target_port)
    if not proxy_url:
        return socket.create_connection((target_host, port_i), timeout=timeout)

    if not valid_proxy_url(proxy_url):
        raise ValueError("invalid proxy URL")
    parsed = urlparse(proxy_url.strip())
    scheme = (parsed.scheme or "").lower()
    proxy_host = parsed.hostname
    proxy_port = parsed.port or (1080 if "socks" in scheme else (443 if scheme == "https" else 8080))

    sock = socket.create_connection((proxy_host, proxy_port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        if scheme in ("socks5", "socks5h"):
            ssh_proxy.connect_socks5(sock, parsed, target_host, port_i)
            return sock
        if scheme in ("http", "https"):
            if scheme == "https":
                pctx = proxy_ssl_context or ssl.create_default_context()
                sock = pctx.wrap_socket(sock, server_hostname=proxy_host)
            ssh_proxy.connect_http(sock, parsed, target_host, port_i)
            return sock
        raise ValueError(f"unsupported proxy scheme: {scheme}")
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        raise


class ProxyHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, port=None, timeout=15, proxy_url="", proxy_ssl_context=None):
        super().__init__(host, port=port, timeout=timeout)
        self._proxy_url = proxy_url or ""
        self._proxy_ssl_context = proxy_ssl_context

    def connect(self):
        if not self._proxy_url:
            return super().connect()
        self.sock = _open_tunneled_socket(
            self.host,
            self.port,
            self._proxy_url,
            timeout=self.timeout,
            proxy_ssl_context=self._proxy_ssl_context,
        )


class ProxyHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port=None, context=None, timeout=15, proxy_url="", proxy_ssl_context=None):
        super().__init__(host, port=port, context=context, timeout=timeout)
        self._tls_context = context
        self._proxy_url = proxy_url or ""
        self._proxy_ssl_context = proxy_ssl_context

    def connect(self):
        if not self._proxy_url:
            return super().connect()
        raw_sock = _open_tunneled_socket(
            self.host,
            self.port,
            self._proxy_url,
            timeout=self.timeout,
            proxy_ssl_context=self._proxy_ssl_context,
        )
        ctx = self._tls_context or ssl.create_default_context()
        try:
            self.sock = ctx.wrap_socket(raw_sock, server_hostname=self.host)
        except Exception:
            try:
                raw_sock.close()
            except Exception:
                pass
            raise


def http_json_request(url, method="GET", body=None, headers=None, proxy_url="", timeout=15, ssl_context=None):
    u = urlparse(url)
    scheme = (u.scheme or "").lower()
    if scheme not in ("http", "https") or not u.hostname:
        raise ValueError("invalid HTTP URL")
    port = u.port or (443 if scheme == "https" else 80)
    req_path = u.path or "/"
    if u.query:
        req_path = f"{req_path}?{u.query}"

    req_headers = dict(headers or {})
    raw_body = None
    if body is not None:
        raw_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json; charset=utf-8")
    req_headers.setdefault("User-Agent", "ratholemonitor/1.0")
    req_headers.setdefault("Connection", "close")

    if scheme == "https":
        conn = ProxyHTTPSConnection(
            u.hostname,
            port=port,
            context=ssl_context,
            timeout=timeout,
            proxy_url=proxy_url,
            proxy_ssl_context=ssl_context,
        )
    else:
        conn = ProxyHTTPConnection(
            u.hostname,
            port=port,
            timeout=timeout,
            proxy_url=proxy_url,
            proxy_ssl_context=ssl_context,
        )
    try:
        conn.request(method, req_path, body=raw_body, headers=req_headers)
        resp = conn.getresponse()
        status = int(resp.status)
        raw_text = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw_text) if raw_text.strip() else {}
            if not isinstance(parsed, dict):
                parsed = {"ok": False, "status": status, "raw": raw_text[:300]}
        except ValueError:
            parsed = {"ok": False, "status": status, "raw": raw_text[:300]}
        return status, parsed
    finally:
        try:
            conn.close()
        except Exception:
            pass


def pick_free_local_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


class SshRelayTunnel:
    """Ephemeral/managed `ssh -N -D` dynamic SOCKS5 relay through a live foreign node."""

    def __init__(self, server, ssh_key_path="", ssh_opts=None, local_port=None, startup_timeout=8.0):
        srv = server if isinstance(server, dict) else {}
        host = str(srv.get("host", "") or "").strip()
        if not host or not _valid_host(host):
            raise ValueError("invalid SSH host")
        user = str(srv.get("user", "") or "root").strip()
        if not RE_SSH_USER.match(user):
            raise ValueError("invalid SSH user")
        try:
            port = int(srv.get("port", 22) or 22)
        except (TypeError, ValueError) as e:
            raise ValueError("invalid SSH port") from e
        if not (1 <= port <= 65535):
            raise ValueError("invalid SSH port")

        self.server_name = str(srv.get("name", "") or host)
        self.host = host
        self.user = user
        self.port = port
        self.local_port = int(local_port) if local_port else pick_free_local_port()
        self._proc = None

        cmd = [
            "ssh",
            "-N",
            "-D",
            f"127.0.0.1:{self.local_port}",
            "-p",
            str(self.port),
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
        ]
        extra_opts = list(ssh_opts or [])
        has_strict = any("StrictHostKeyChecking" in str(x) for x in extra_opts)
        if not has_strict:
            cmd.extend(["-o", "StrictHostKeyChecking=accept-new"])
        for opt in extra_opts:
            opt_s = str(opt)
            if opt_s in ("-N", "-D", "-f", "-T"):
                continue
            cmd.append(opt_s)
        if ssh_key_path and os.path.isfile(str(ssh_key_path)):
            cmd.extend(["-i", str(ssh_key_path)])
        cmd.append(f"{self.user}@{self.host}")

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            shell=False,
        )
        deadline = time.monotonic() + float(startup_timeout)
        while time.monotonic() < deadline:
            rc = self._proc.poll()
            if rc is not None:
                err_txt = ""
                try:
                    err_txt = (self._proc.stderr.read() or b"").decode("utf-8", errors="replace").strip()
                except Exception:
                    pass
                self.close()
                raise RuntimeError(f"ssh relay exited (rc={rc}): {redact_secrets(err_txt[:240])}")
            try:
                probe = socket.create_connection(("127.0.0.1", self.local_port), timeout=0.4)
                probe.close()
                return
            except OSError:
                time.sleep(0.08)

        self.close()
        raise RuntimeError(f"ssh relay startup timed out ({self.server_name})")

    @property
    def proxy_url(self):
        return f"socks5h://127.0.0.1:{self.local_port}"

    def is_alive(self):
        return self._proc is not None and self._proc.poll() is None

    def close(self):
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
        except Exception:
            pass
        finally:
            try:
                if proc.stderr is not None:
                    proc.stderr.close()
            except Exception:
                pass


class TelegramRelayManager:
    """Manages direct / proxy / live foreign-node SSH SOCKS5 relay routing for Telegram API calls."""

    def __init__(
        self,
        relay_mode="auto",
        proxy_url="",
        inventory_fn=None,
        ssh_key_path="",
        ssh_opts=None,
        api_base="https://api.telegram.org",
        timeout=15,
        ssl_context=None,
        tunnel_factory=SshRelayTunnel,
        direct_recheck_sec=600,
    ):
        mode = str(relay_mode or "auto").strip().lower()
        if mode not in RELAY_MODES:
            raise ValueError(f"invalid relay_mode: {mode}")
        px = str(proxy_url or "").strip()
        if px and not valid_proxy_url(px):
            raise ValueError("invalid proxy_url")
        self.relay_mode = mode
        self.proxy_url = px
        self.inventory_fn = inventory_fn or (lambda: [])
        self.ssh_key_path = str(ssh_key_path or "")
        self.ssh_opts = list(ssh_opts or [])
        self.api_base = str(api_base or "https://api.telegram.org").rstrip("/")
        self.timeout = float(timeout)
        self.ssl_context = ssl_context
        self._tunnel_factory = tunnel_factory
        self.direct_recheck_sec = float(direct_recheck_sec)

        self._lock = threading.Lock()
        self._op_lock = threading.Lock()
        self._route_mode = "none"
        self._active_tunnel = None
        self._active_node = None
        self._active_proxy = ""
        self._last_direct_fail = 0.0

    def _ssh_candidates(self, prefer=None, avoid=None):
        inv = self.inventory_fn() or []
        out = []
        seen = set()
        for srv in inv:
            if not isinstance(srv, dict):
                continue
            if srv.get("role") != "node":
                continue
            host = str(srv.get("host", "") or "").strip()
            if not _valid_host(host):
                continue
            name = str(srv.get("name") or host)
            if name in seen:
                continue
            seen.add(name)
            out.append(srv)

        def _sort_key(srv):
            nm = str(srv.get("name") or srv.get("host"))
            if avoid and nm == avoid:
                return (2, nm)
            if prefer and nm == prefer:
                return (0, nm)
            return (1, nm)

        out.sort(key=_sort_key)
        return out

    def _call_via(self, url, payload, proxy_url, timeout, bot_token):
        method = "POST" if payload is not None else "GET"
        status, data = http_json_request(
            url,
            method=method,
            body=payload,
            proxy_url=proxy_url,
            timeout=timeout,
            ssl_context=self.ssl_context,
        )
        if not isinstance(data, dict) or "ok" not in data:
            raise RuntimeError(f"unexpected response from Telegram endpoint (status={status})")
        if not data.get("ok"):
            # HTTP 400/401/403/404/409/429 with valid Telegram JSON means network path works.
            if status in (400, 401, 403, 404, 409, 429) and "error_code" in data:
                raise TelegramApiError(status, data)
            raise RuntimeError(f"telegram error status={status}: {data.get('description') or data.get('raw') or 'unknown'}")
        return data

    def _try_ssh_auto(self, url, payload, timeout, bot_token):
        failed_node = None
        with self._lock:
            cur_tun = self._active_tunnel
            cur_node = self._active_node

        if cur_tun is not None and cur_tun.is_alive():
            try:
                res = self._call_via(url, payload, cur_tun.proxy_url, timeout, bot_token)
                with self._lock:
                    self._route_mode = "ssh_auto"
                    self._active_proxy = cur_tun.proxy_url
                return res
            except TelegramApiError:
                with self._lock:
                    self._route_mode = "ssh_auto"
                    self._active_proxy = cur_tun.proxy_url
                raise
            except Exception:
                failed_node = cur_node
                with self._lock:
                    if self._active_tunnel is cur_tun:
                        self._active_tunnel = None
                        self._active_node = None
                        self._active_proxy = ""
                cur_tun.close()
        elif cur_tun is not None:
            with self._lock:
                if self._active_tunnel is cur_tun:
                    self._active_tunnel = None
                    self._active_node = None
                    self._active_proxy = ""
            cur_tun.close()

        candidates = self._ssh_candidates(prefer=cur_node, avoid=failed_node)
        if not candidates:
            raise RuntimeError("no foreign SSH nodes available for Telegram relay")

        errors = []
        for node in candidates:
            node_name = str(node.get("name") or node.get("host"))
            tun = None
            try:
                tun = self._tunnel_factory(node, ssh_key_path=self.ssh_key_path, ssh_opts=self.ssh_opts)
                res = self._call_via(url, payload, tun.proxy_url, timeout, bot_token)
                with self._lock:
                    old = self._active_tunnel
                    self._active_tunnel = tun
                    self._active_node = node_name
                    self._active_proxy = tun.proxy_url
                    self._route_mode = "ssh_auto"
                if old is not None and old is not tun:
                    old.close()
                return res
            except TelegramApiError:
                with self._lock:
                    old = self._active_tunnel
                    self._active_tunnel = tun
                    self._active_node = node_name
                    self._active_proxy = tun.proxy_url
                    self._route_mode = "ssh_auto"
                if old is not None and old is not tun:
                    old.close()
                raise
            except Exception as e:
                if tun is not None:
                    tun.close()
                errors.append(f"{node_name}: {redact_secrets(str(e), [bot_token, self.proxy_url])}")

        raise RuntimeError("ssh_auto failed: " + "; ".join(errors))

    def request(self, bot_token, api_method, payload=None, timeout=None):
        tok = str(bot_token or "").strip()
        if not tok:
            raise ValueError("bot_token is required")
        t_out = float(self.timeout if timeout is None else timeout)
        url = f"{self.api_base}/bot{tok}/{api_method.lstrip('/')}"
        secrets = [tok, self.proxy_url]

        with self._op_lock:
            mode = self.relay_mode
            if mode == "direct":
                try:
                    res = self._call_via(url, payload, "", t_out, tok)
                    with self._lock:
                        self._route_mode = "direct"
                        self._active_node = None
                        self._active_proxy = ""
                    return res
                except TelegramApiError:
                    raise
                except Exception as e:
                    raise RuntimeError(redact_secrets(str(e), secrets)) from None

            if mode == "proxy":
                if not self.proxy_url:
                    raise RuntimeError("relay_mode='proxy' requires a non-empty proxy URL")
                try:
                    res = self._call_via(url, payload, self.proxy_url, t_out, tok)
                    with self._lock:
                        self._route_mode = "proxy"
                        self._active_node = None
                        self._active_proxy = self.proxy_url
                    return res
                except TelegramApiError:
                    raise
                except Exception as e:
                    raise RuntimeError(redact_secrets(str(e), secrets)) from None

            if mode == "ssh_auto":
                try:
                    return self._try_ssh_auto(url, payload, t_out, tok)
                except TelegramApiError:
                    raise
                except Exception as e:
                    raise RuntimeError(redact_secrets(str(e), secrets)) from None

            # mode == "auto": direct -> proxy (if set) -> ssh_auto
            errors = []
            has_alt = bool(self.proxy_url) or bool(self._ssh_candidates())
            now = time.monotonic()
            with self._lock:
                skip_direct = (
                    has_alt
                    and self._last_direct_fail > 0.0
                    and (now - self._last_direct_fail) < self.direct_recheck_sec
                )

            if not skip_direct:
                try:
                    res = self._call_via(url, payload, "", t_out, tok)
                    with self._lock:
                        old = self._active_tunnel
                        self._active_tunnel = None
                        self._active_node = None
                        self._active_proxy = ""
                        self._route_mode = "direct"
                        self._last_direct_fail = 0.0
                    if old is not None:
                        old.close()
                    return res
                except TelegramApiError:
                    raise
                except Exception as e:
                    with self._lock:
                        self._last_direct_fail = time.monotonic()
                    errors.append("direct: " + redact_secrets(str(e), secrets))

            if self.proxy_url:
                try:
                    res = self._call_via(url, payload, self.proxy_url, t_out, tok)
                    with self._lock:
                        old = self._active_tunnel
                        self._active_tunnel = None
                        self._active_node = None
                        self._active_proxy = self.proxy_url
                        self._route_mode = "proxy"
                    if old is not None:
                        old.close()
                    return res
                except TelegramApiError:
                    raise
                except Exception as e:
                    errors.append("proxy: " + redact_secrets(str(e), secrets))

            try:
                return self._try_ssh_auto(url, payload, t_out, tok)
            except TelegramApiError:
                raise
            except Exception as e:
                errors.append(redact_secrets(str(e), secrets))
                raise RuntimeError("all relay routes failed (" + " | ".join(errors) + ")") from None

    def active_route(self):
        with self._lock:
            return {
                "mode": self._route_mode,
                "node": self._active_node,
                "proxy": redact_secrets(self._active_proxy, [self._active_proxy]),
            }

    def close(self):
        with self._lock:
            tun = self._active_tunnel
            self._active_tunnel = None
            self._active_node = None
            self._active_proxy = ""
        if tun is not None:
            tun.close()


class TelegramClient:
    def __init__(self, bot_token, relay_manager):
        self.bot_token = str(bot_token or "").strip()
        self.relay = relay_manager

    def get_me(self, timeout=10):
        res = self.relay.request(self.bot_token, "getMe", payload=None, timeout=timeout)
        return res.get("result") or {}

    def get_updates(self, offset=0, timeout=25):
        payload = {
            "offset": int(offset),
            "timeout": int(timeout),
            "allowed_updates": ["message", "callback_query"],
        }
        res = self.relay.request(
            self.bot_token,
            "getUpdates",
            payload=payload,
            timeout=max(float(timeout) + 10.0, 15.0),
        )
        items = res.get("result")
        return items if isinstance(items, list) else []

    def send_message(self, chat_id, text, parse_mode="HTML", reply_markup=None, timeout=15):
        chunks = _split_message(text, limit=4000)
        results = []
        last_idx = len(chunks) - 1
        for idx, chunk in enumerate(chunks):
            payload = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup is not None and idx == last_idx:
                payload["reply_markup"] = reply_markup
            res = self.relay.request(self.bot_token, "sendMessage", payload=payload, timeout=timeout)
            results.append(res.get("result") or {})
        return results

    def answer_callback_query(self, callback_query_id, text="", timeout=10):
        payload = {"callback_query_id": str(callback_query_id)}
        if text:
            payload["text"] = str(text)[:180]
        return self.relay.request(self.bot_token, "answerCallbackQuery", payload=payload, timeout=timeout)


def _split_message(text, limit=4000):
    s = str(text or "")
    if len(s) <= limit:
        return [s] if s else [""]
    chunks = []
    while len(s) > limit:
        cut = s.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(s[:cut])
        s = s[cut:].lstrip("\n")
    if s:
        chunks.append(s)
    return chunks or [""]


def _probe_telegram_endpoint(api_base, bot_token="", proxy_url="", timeout=8, ssl_context=None):
    secrets = [bot_token, proxy_url]
    t0 = time.monotonic()
    tok = str(bot_token or "").strip()
    try:
        if tok:
            url = f"{api_base.rstrip('/')}/bot{tok}/getMe"
            status, data = http_json_request(
                url, method="GET", proxy_url=proxy_url, timeout=timeout, ssl_context=ssl_context
            )
            ms = round((time.monotonic() - t0) * 1000.0, 1)
            if isinstance(data, dict) and data.get("ok") is True:
                uname = str(((data.get("result") or {}).get("username")) or "")
                return True, ms, uname, ""
            desc = ""
            if isinstance(data, dict):
                desc = str(data.get("description") or data.get("raw") or "")
            return False, ms, "", redact_secrets(f"status={status} {desc}".strip(), secrets)

        u = urlparse(api_base)
        scheme = (u.scheme or "https").lower()
        host = u.hostname or "api.telegram.org"
        port = u.port or (443 if scheme == "https" else 80)
        sock = _open_tunneled_socket(host, port, proxy_url=proxy_url, timeout=timeout, proxy_ssl_context=ssl_context)
        try:
            if scheme == "https":
                ctx = ssl_context or ssl.create_default_context()
                wrapped = ctx.wrap_socket(sock, server_hostname=host)
                wrapped.close()
            else:
                sock.close()
        finally:
            try:
                sock.close()
            except Exception:
                pass
        ms = round((time.monotonic() - t0) * 1000.0, 1)
        return True, ms, "", ""
    except Exception as e:
        ms = round((time.monotonic() - t0) * 1000.0, 1)
        return False, ms, "", redact_secrets(str(e), secrets)


def diagnose_relay(
    bot_token,
    inventory,
    proxy_url="",
    ssh_key_path="",
    ssh_opts=None,
    api_base="https://api.telegram.org",
    timeout=8,
    ssl_context=None,
    tunnel_factory=SshRelayTunnel,
):
    tok = str(bot_token or "").strip()
    px = str(proxy_url or "").strip()
    base = str(api_base or "https://api.telegram.org").rstrip("/")
    secrets = [tok, px]

    ok_d, ms_d, uname_d, err_d = _probe_telegram_endpoint(
        base, bot_token=tok, proxy_url="", timeout=timeout, ssl_context=ssl_context
    )
    direct_res = {"ok": ok_d, "latency_ms": ms_d, "bot_username": uname_d, "error": err_d}

    if px:
        if valid_proxy_url(px):
            ok_p, ms_p, _, err_p = _probe_telegram_endpoint(
                base, bot_token=tok, proxy_url=px, timeout=timeout, ssl_context=ssl_context
            )
        else:
            ok_p, ms_p, err_p = False, 0.0, "invalid proxy URL"
        proxy_res = {
            "configured": True,
            "proxy": redact_secrets(px, [px]),
            "ok": ok_p,
            "latency_ms": ms_p,
            "error": redact_secrets(err_p, secrets),
        }
    else:
        proxy_res = {"configured": False, "proxy": "", "ok": False, "latency_ms": 0.0, "error": ""}

    ssh_results = []
    seen = set()
    for srv in (inventory or []):
        if len(ssh_results) >= 5:
            break
        if not isinstance(srv, dict) or srv.get("role") != "node":
            continue
        host = str(srv.get("host", "") or "").strip()
        if not _valid_host(host):
            continue
        name = str(srv.get("name") or host)
        if name in seen:
            continue
        seen.add(name)

        tun = None
        t0 = time.monotonic()
        try:
            tun = tunnel_factory(srv, ssh_key_path=ssh_key_path, ssh_opts=ssh_opts)
            ok_n, ms_n, _, err_n = _probe_telegram_endpoint(
                base, bot_token=tok, proxy_url=tun.proxy_url, timeout=timeout, ssl_context=ssl_context
            )
            ssh_results.append({
                "name": name,
                "host": host,
                "ok": ok_n,
                "latency_ms": ms_n,
                "error": redact_secrets(err_n, secrets),
            })
        except Exception as e:
            ssh_results.append({
                "name": name,
                "host": host,
                "ok": False,
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 1),
                "error": redact_secrets(str(e), secrets),
            })
        finally:
            if tun is not None:
                tun.close()

    working_nodes = [n for n in ssh_results if n["ok"]]
    working_nodes.sort(key=lambda x: x["latency_ms"])
    best_ssh = working_nodes[0]["name"] if working_nodes else None

    if direct_res["ok"]:
        rec_mode = "direct"
        summary = f"Direct Telegram reachability succeeded ({direct_res['latency_ms']} ms)."
    elif proxy_res["ok"]:
        rec_mode = "proxy"
        summary = f"Direct failed; configured proxy reached Telegram ({proxy_res['latency_ms']} ms)."
    elif best_ssh:
        rec_mode = "ssh_auto"
        summary = f"Direct failed; {len(working_nodes)}/{len(ssh_results)} foreign SSH nodes reached Telegram (fastest: {best_ssh})."
    else:
        rec_mode = "none"
        summary = "Direct, proxy, and foreign SSH node probes all failed to reach Telegram."

    return {
        "direct": direct_res,
        "proxy": proxy_res,
        "ssh_nodes": ssh_results,
        "recommended_mode": rec_mode,
        "best_ssh_node": best_ssh,
        "summary": summary,
    }
