#!/usr/bin/env python3
# monitor.py — daemon-e mostaghel (ratholemonitor.service), bot-e Telegram, va alert engine ba hysteresis.
# Faghat stdlib Python 3; hich dependency pip nadarad.
import argparse
import html
import http.client
import json
import os
import re
import signal
import sys
import threading
import time
from urllib.parse import urlparse

try:
    from tg_relay import (
        RELAY_MODES,
        TelegramClient,
        TelegramRelayManager,
        diagnose_relay,
        redact_secrets,
        valid_proxy_url,
    )
except ImportError:
    _HERE = os.path.dirname(os.path.abspath(__file__))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    from tg_relay import (
        RELAY_MODES,
        TelegramClient,
        TelegramRelayManager,
        diagnose_relay,
        redact_secrets,
        valid_proxy_url,
    )


DEFAULT_MON_CONF = os.environ.get("RATHOLEMON_CONF", "/etc/ratholehub/monitor.json")
DEFAULT_MON_STATE = os.environ.get("RATHOLEMON_STATE", "/var/lib/ratholehub/monitor-state.json")
DEFAULT_HUB_CONF = os.environ.get("RATHOLEHUB_CONF", "/etc/ratholehub/config.json")
DEFAULT_HUB_INV = os.environ.get("RATHOLEHUB_INV", "/etc/ratholehub/inventory.json")

RE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
RE_BOT_TOKEN = re.compile(r"^[^\s\x00-\x1f\x7f/\\@]{6,220}\Z")

DEFAULT_CONFIG = {
    "enabled": False,
    "bot_token": "",
    "allowed_chat_ids": [],
    "hub_url": "http://127.0.0.1:8088",
    "hub_token": "",
    "relay_mode": "auto",
    "proxy": "",
    "poll_interval_sec": 60,
    "fail_threshold": 3,
    "recover_threshold": 2,
    "cooldown_sec": 300,
    "cert_warn_days": 14,
    "allow_remote_actions": True,
    "bot_enabled": True,
    "api_base": "https://api.telegram.org",
}


def _conf_path(path=None):
    return path or os.environ.get("RATHOLEMON_CONF", DEFAULT_MON_CONF)


def _state_path(path=None):
    return path or os.environ.get("RATHOLEMON_STATE", DEFAULT_MON_STATE)


def _atomic_write_json(path, data, mode=0o600):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        try:
            os.chmod(tmp, mode)
        except OSError:
            pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_monitor_config(path=None):
    p = _conf_path(path)
    cfg = dict(DEFAULT_CONFIG)
    cfg["allowed_chat_ids"] = []
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if k in cfg:
                        cfg[k] = v
        except Exception:
            pass
    return cfg


def save_monitor_config(cfg, path=None):
    p = _conf_path(path)
    merged = dict(DEFAULT_CONFIG)
    merged["allowed_chat_ids"] = []
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            if k in merged:
                merged[k] = v
    _atomic_write_json(p, merged, mode=0o600)


def _valid_http_url(val):
    if not isinstance(val, str):
        return False
    v = val.strip()
    if not v or any(ord(c) < 32 or ord(c) == 127 or c.isspace() for c in v):
        return False
    try:
        u = urlparse(v)
        port = u.port
    except ValueError:
        return False
    if (u.scheme or "").lower() not in ("http", "https"):
        return False
    if not u.hostname:
        return False
    if port is not None and not (1 <= port <= 65535):
        return False
    return True


def _parse_chat_ids(val):
    if val is None or val == "":
        return [], None
    tokens = []
    if isinstance(val, (list, tuple)):
        tokens = [str(x).strip() for x in val]
    elif isinstance(val, str):
        tokens = [x.strip() for x in re.split(r"[\s,]+", val.strip()) if x.strip()]
    else:
        return None, "allowed_chat_ids must be a list of integers or comma-separated string"

    out = []
    seen = set()
    for tok in tokens:
        if not tok:
            continue
        if not re.match(r"^-?[0-9]{1,20}\Z", tok):
            return None, f"invalid Telegram chat id: {tok}"
        cid = int(tok)
        if cid == 0:
            return None, "Telegram chat id cannot be 0"
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    if len(out) > 50:
        return None, "too many allowed_chat_ids (max 50)"
    return out, None


def validate_monitor_update(existing, patch):
    if not isinstance(patch, dict):
        return None, "invalid request body"
    cfg = dict(DEFAULT_CONFIG)
    cfg["allowed_chat_ids"] = list(DEFAULT_CONFIG["allowed_chat_ids"])
    if isinstance(existing, dict):
        for k in DEFAULT_CONFIG:
            if k in existing:
                cfg[k] = existing[k]
    cfg["allowed_chat_ids"] = list(cfg.get("allowed_chat_ids") or [])

    for bkey in ("enabled", "allow_remote_actions", "bot_enabled"):
        if bkey in patch:
            if not isinstance(patch[bkey], bool):
                return None, f"{bkey} must be boolean"
            cfg[bkey] = patch[bkey]

    if "relay_mode" in patch:
        rm = str(patch["relay_mode"] or "").strip().lower()
        if rm not in RELAY_MODES:
            return None, f"invalid relay_mode (expected {', '.join(RELAY_MODES)})"
        cfg["relay_mode"] = rm

    if "proxy" in patch:
        px = patch["proxy"]
        if px is None:
            px = ""
        if not isinstance(px, str) or not valid_proxy_url(px):
            return None, "invalid proxy URL"
        cfg["proxy"] = px.strip()

    int_bounds = {
        "poll_interval_sec": (15, 3600),
        "fail_threshold": (1, 20),
        "recover_threshold": (1, 20),
        "cooldown_sec": (30, 86400),
        "cert_warn_days": (1, 90),
    }
    for ikey, (lo, hi) in int_bounds.items():
        if ikey in patch and patch[ikey] not in (None, ""):
            raw_v = patch[ikey]
            if isinstance(raw_v, bool):
                return None, f"{ikey} must be an integer ({lo}..{hi})"
            try:
                iv = int(raw_v)
            except (TypeError, ValueError):
                return None, f"{ikey} must be an integer ({lo}..{hi})"
            if not (lo <= iv <= hi):
                return None, f"{ikey} must be {lo}..{hi}"
            cfg[ikey] = iv

    if "allowed_chat_ids" in patch:
        parsed_ids, err = _parse_chat_ids(patch["allowed_chat_ids"])
        if err:
            return None, err
        cfg["allowed_chat_ids"] = parsed_ids

    if patch.get("clear_bot_token") is True:
        cfg["bot_token"] = ""
    elif "bot_token" in patch:
        bt = patch["bot_token"]
        if bt is not None:
            if not isinstance(bt, str):
                return None, "bot_token must be a string"
            bts = bt.strip()
            if bts:
                if not RE_BOT_TOKEN.match(bts):
                    return None, "invalid bot_token format"
                cfg["bot_token"] = bts

    if "hub_token" in patch and patch["hub_token"] is not None:
        ht = str(patch["hub_token"]).strip()
        if ht:
            if any(ord(c) < 32 or ord(c) == 127 or c.isspace() for c in ht):
                return None, "invalid hub_token format"
            cfg["hub_token"] = ht

    for ukey in ("hub_url", "api_base"):
        if ukey in patch and patch[ukey] is not None:
            uv = str(patch[ukey]).strip().rstrip("/")
            if not _valid_http_url(uv):
                return None, f"invalid {ukey}"
            cfg[ukey] = uv

    return cfg, None


def public_monitor_config(cfg):
    c = dict(DEFAULT_CONFIG)
    if isinstance(cfg, dict):
        for k in DEFAULT_CONFIG:
            if k in cfg:
                c[k] = cfg[k]
    bt = str(c.pop("bot_token", "") or "")
    ht = str(c.pop("hub_token", "") or "")
    c["bot_token_set"] = bool(bt)
    c["bot_token_hint"] = (bt[:4] + "…" + bt[-4:]) if len(bt) >= 8 else ("***" if bt else "")
    c["hub_token_set"] = bool(ht)
    c["allowed_chat_ids"] = list(c.get("allowed_chat_ids") or [])
    return c


class HubApiClient:
    """Client for talking to local ratholehub REST API."""

    def __init__(self, hub_url="http://127.0.0.1:8088", hub_token="", hub_conf_path=None, timeout=15, ssl_context=None):
        self.hub_url = str(hub_url or "http://127.0.0.1:8088").rstrip("/")
        self.hub_token = str(hub_token or "").strip()
        self.hub_conf_path = hub_conf_path or os.environ.get("RATHOLEHUB_CONF", DEFAULT_HUB_CONF)
        self.timeout = float(timeout)
        self.ssl_context = ssl_context

    def resolve_token(self):
        if self.hub_token:
            return self.hub_token
        p = self.hub_conf_path
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and d.get("api_token"):
                    return str(d["api_token"]).strip()
            except Exception:
                pass
        return ""

    def _request(self, method, path, body=None):
        u = urlparse(self.hub_url)
        scheme = (u.scheme or "http").lower()
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if scheme == "https" else 80)
        base_path = u.path.rstrip("/")
        req_path = f"{base_path}{path}" if path.startswith("/") else f"{base_path}/{path}"

        tok = self.resolve_token()
        headers = {"Accept": "application/json", "Connection": "close"}
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        raw_body = None
        if body is not None:
            raw_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        if scheme == "https":
            conn = http.client.HTTPSConnection(host, port=port, timeout=self.timeout, context=self.ssl_context)
        else:
            conn = http.client.HTTPConnection(host, port=port, timeout=self.timeout)
        try:
            conn.request(method, req_path, body=raw_body, headers=headers)
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except ValueError:
                parsed = {"error": raw[:240]}
            if resp.status >= 400:
                msg = parsed.get("error") if isinstance(parsed, dict) else str(resp.status)
                raise RuntimeError(f"Hub HTTP {resp.status}: {msg}")
            return parsed
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def get_servers(self):
        res = self._request("GET", "/api/servers")
        return res if isinstance(res, list) else []

    def get_overview(self, name):
        return self._request("GET", f"/api/servers/{name}/overview")

    def get_fleet_drift(self):
        return self._request("GET", "/api/fleet/drift")

    def link_test(self, server, node=None, count=3):
        body = {"count": int(count)}
        if node:
            body["node"] = node
        return self._request("POST", f"/api/servers/{server}/link-test", body=body)

    def run_action(self, server, action, args=None):
        return self._request(
            "POST",
            f"/api/servers/{server}/action",
            body={"action": action, "args": args or {}},
        )


class HysteresisTracker:
    """Tracks fail/recover streaks and mutes with persistent atomic JSON state."""

    def __init__(self, fail_threshold=3, recover_threshold=2, cooldown_sec=300, state_path=None):
        self.fail_threshold = max(1, int(fail_threshold))
        self.recover_threshold = max(1, int(recover_threshold))
        self.cooldown_sec = max(0, int(cooldown_sec))
        self.state_path = state_path
        self._lock = threading.Lock()
        self.muted_count = 0
        self._state = {"incidents": {}, "mute_until": 0}
        self._load()

    def _load(self):
        if not self.state_path or not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                incs = d.get("incidents")
                self._state["incidents"] = dict(incs) if isinstance(incs, dict) else {}
                self._state["mute_until"] = int(d.get("mute_until", 0) or 0)
        except Exception:
            pass

    def _save(self):
        if not self.state_path:
            return
        _atomic_write_json(self.state_path, self._state, mode=0o600)

    def is_muted(self, now=None):
        now_i = int(time.time() if now is None else now)
        with self._lock:
            return now_i < int(self._state.get("mute_until", 0) or 0)

    def mute_remaining_sec(self, now=None):
        now_i = int(time.time() if now is None else now)
        with self._lock:
            until = int(self._state.get("mute_until", 0) or 0)
            return max(0, until - now_i)

    def set_mute(self, minutes, now=None):
        mins = int(minutes)
        if not (1 <= mins <= 1440):
            raise ValueError("mute minutes must be 1..1440")
        now_i = int(time.time() if now is None else now)
        until = now_i + mins * 60
        with self._lock:
            self._state["mute_until"] = until
            self._save()
        return until

    def clear_mute(self):
        with self._lock:
            self._state["mute_until"] = 0
            self._save()

    def active_alerts(self):
        with self._lock:
            out = []
            for key, rec in sorted(self._state["incidents"].items()):
                if rec.get("alerting"):
                    out.append({
                        "key": key,
                        "severity": rec.get("severity", "error"),
                        "title": rec.get("title", key),
                        "detail": rec.get("detail", ""),
                        "fail_streak": int(rec.get("fail_streak", 0)),
                        "fired_at": int(rec.get("fired_at", 0)),
                    })
            return out

    def evaluate(self, observations, now=None):
        now_i = int(time.time() if now is None else now)
        obs = dict(observations or {})
        events = []

        with self._lock:
            incidents = self._state.setdefault("incidents", {})
            muted = now_i < int(self._state.get("mute_until", 0) or 0)

            all_keys = sorted(set(obs.keys()) | set(incidents.keys()))
            to_prune = []

            for key in all_keys:
                ob = obs.get(key)
                if ob is None:
                    ob = {"ok": True, "detail": "cleared"}
                rec = incidents.get(key)
                if not isinstance(rec, dict):
                    rec = {
                        "fail_streak": 0,
                        "ok_streak": 0,
                        "alerting": False,
                        "last_notified": 0,
                        "fired_at": 0,
                        "severity": "info",
                        "title": key,
                        "detail": "",
                    }
                    incidents[key] = rec

                if not ob.get("ok", True):
                    rec["fail_streak"] = int(rec.get("fail_streak", 0)) + 1
                    rec["ok_streak"] = 0
                    rec["severity"] = str(ob.get("severity") or "error")
                    rec["title"] = str(ob.get("title") or key)
                    rec["detail"] = str(ob.get("detail") or "")
                    rec["last_seen"] = now_i

                    if not rec.get("alerting") and rec["fail_streak"] >= self.fail_threshold:
                        last_notified = int(rec.get("last_notified", 0) or 0)
                        rec["alerting"] = True
                        rec["fired_at"] = now_i
                        cooldown_ok = (last_notified == 0) or ((now_i - last_notified) >= self.cooldown_sec)
                        if muted:
                            self.muted_count += 1
                        elif cooldown_ok:
                            rec["last_notified"] = now_i
                            events.append({
                                "kind": "firing",
                                "key": key,
                                "severity": rec["severity"],
                                "title": rec["title"],
                                "detail": rec["detail"],
                                "fail_streak": rec["fail_streak"],
                                "ts": now_i,
                            })
                else:
                    rec["ok_streak"] = int(rec.get("ok_streak", 0)) + 1
                    rec["fail_streak"] = 0
                    rec["last_seen"] = now_i

                    if rec.get("alerting") and rec["ok_streak"] >= self.recover_threshold:
                        rec["alerting"] = False
                        if muted:
                            self.muted_count += 1
                        else:
                            rec["last_notified"] = now_i
                            events.append({
                                "kind": "resolved",
                                "key": key,
                                "severity": "info",
                                "title": rec.get("title") or key,
                                "detail": str(ob.get("detail") or "recovered"),
                                "ok_streak": rec["ok_streak"],
                                "ts": now_i,
                            })
                        to_prune.append(key)
                    elif not rec.get("alerting") and (key not in obs or rec["ok_streak"] >= self.recover_threshold):
                        to_prune.append(key)

            for k in to_prune:
                incidents.pop(k, None)

            self._save()

        return events


def collect_observations(hub_client, cert_warn_days=14):
    obs = {}
    meta = {"servers": [], "drift": None, "error": ""}
    try:
        servers = hub_client.get_servers()
        drift = hub_client.get_fleet_drift()
    except Exception as e:
        obs["hub:api"] = {
            "ok": False,
            "severity": "error",
            "title": "Hub API unreachable",
            "detail": str(e)[:240],
        }
        meta["error"] = str(e)
        return obs, meta

    meta["servers"] = servers
    meta["drift"] = drift
    obs["hub:api"] = {"ok": True, "severity": "info", "title": "Hub API healthy", "detail": ""}

    items = (drift or {}).get("items") or []
    unreachable = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("kind") == "unreachable":
            srv = str(it.get("server") or "")
            if srv:
                unreachable[srv] = str(it.get("message") or it.get("actual") or "unreachable")

    for s in servers:
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "")
        if not name:
            continue
        role = str(s.get("role") or "node")
        if name in unreachable:
            obs[f"server:{name}"] = {
                "ok": False,
                "severity": "error",
                "title": f"Server {name} ({role}) unreachable",
                "detail": unreachable[name],
            }
        else:
            obs[f"server:{name}"] = {
                "ok": True,
                "severity": "info",
                "title": f"Server {name} ({role}) online",
                "detail": "reachable",
            }

    for it in items:
        if not isinstance(it, dict):
            continue
        kind = str(it.get("kind") or "drift")
        if kind == "unreachable":
            continue
        sev = str(it.get("severity") or "info").lower()
        srv = str(it.get("server") or "fleet")
        svc = str(it.get("service") or "-")
        msg = str(it.get("message") or kind)
        if kind == "cert_expiring":
            # Respect configured warning threshold if days left is present
            m_days = re.search(r"([0-9]+)\s*day", str(it.get("actual") or msg))
            if m_days and int(m_days.group(1)) <= min(3, int(cert_warn_days)):
                sev = "error"
            elif m_days and int(m_days.group(1)) <= int(cert_warn_days) and sev == "info":
                sev = "warning"
        if sev in ("error", "warning"):
            obs[f"drift:{kind}:{srv}:{svc}"] = {
                "ok": False,
                "severity": sev,
                "title": f"{srv}/{svc}: {kind}",
                "detail": msg,
            }

    return obs, meta


def format_alert_event(ev):
    kind = ev.get("kind")
    sev = str(ev.get("severity") or "error").lower()
    if kind == "resolved":
        badge = "🟢 <b>RECOVERED</b>"
    elif sev == "warning":
        badge = "🟡 <b>WARNING</b>"
    else:
        badge = "🔴 <b>FIRING</b>"
    title = html.escape(str(ev.get("title") or ev.get("key") or "Alert"), quote=True)
    detail = html.escape(str(ev.get("detail") or ""), quote=True)
    lines = [f"{badge}: <code>{title}</code>"]
    if detail:
        lines.append(detail)
    return "\n".join(lines)


class BotCommandRouter:
    """Pure fail-closed command & callback handler for operational Telegram control."""

    def __init__(self, hub_client, tracker, relay_mgr, allowed_chat_ids, allow_remote_actions=True):
        self.hub = hub_client
        self.tracker = tracker
        self.relay = relay_mgr
        self.allowed_chat_ids = set()
        for cid in (allowed_chat_ids or ()):
            try:
                self.allowed_chat_ids.add(int(cid))
            except (TypeError, ValueError):
                pass
        self.allow_remote_actions = bool(allow_remote_actions)

    def is_authorized(self, chat_id):
        if not self.allowed_chat_ids:
            return False
        try:
            return int(chat_id) in self.allowed_chat_ids
        except (TypeError, ValueError):
            return False

    def _main_keyboard(self):
        return {
            "inline_keyboard": [
                [
                    {"text": "📊 Status", "callback_data": "cb:status"},
                    {"text": "⚠️ Drift", "callback_data": "cb:drift"},
                ],
                [
                    {"text": "🔔 Alerts", "callback_data": "cb:alerts"},
                    {"text": "🛰 Relay", "callback_data": "cb:relay"},
                ],
            ]
        }

    def _cmd_help(self):
        txt = (
            "<b>RatholeEngine Monitor Bot</b>\n"
            "• <code>/status</code> — Fleet overview, drift summary, and alerts\n"
            "• <code>/drift</code> — Fleet drift diagnostics\n"
            "• <code>/test &lt;server&gt; [node]</code> — Bidirectional link test\n"
            "• <code>/doctor &lt;server&gt;</code> — Run server doctor check\n"
            "• <code>/restart &lt;server&gt;</code> — Restart server tunnel service\n"
            "• <code>/relay</code> — Show active Telegram relay route\n"
            "• <code>/alerts</code> — List active firing incidents\n"
            "• <code>/mute [minutes]</code> — Mute alert notifications (1..1440)\n"
            "• <code>/unmute</code> — Resume alert notifications"
        )
        return txt, self._main_keyboard()

    def _cmd_status(self):
        try:
            servers = self.hub.get_servers()
            drift = self.hub.get_fleet_drift()
        except Exception as e:
            return f"🔴 <b>Hub unreachable:</b> <code>{html.escape(str(e)[:240], quote=True)}</code>", self._main_keyboard()

        total = len(servers)
        unreach = int((drift or {}).get("servers_unreachable", 0) or 0)
        summary = (drift or {}).get("summary") or {}
        alerts = self.tracker.active_alerts()
        route = self.relay.active_route()
        muted_rem = self.tracker.mute_remaining_sec()

        lines = [
            "<b>📊 Fleet Status</b>",
            f"Servers: <b>{total - unreach}/{total}</b> online",
            (
                f"Drift: <b>{int(summary.get('error', 0))}</b> error, "
                f"<b>{int(summary.get('warning', 0))}</b> warning, "
                f"<b>{int(summary.get('info', 0))}</b> info"
            ),
            f"Active alerts: <b>{len(alerts)}</b>" + (f" (muted {muted_rem // 60}m)" if muted_rem > 0 else ""),
            f"Relay: <code>{html.escape(str(route.get('mode') or 'auto'), quote=True)}</code>"
            + (f" via <code>{html.escape(str(route['node']), quote=True)}</code>" if route.get("node") else ""),
        ]
        return "\n".join(lines), self._main_keyboard()

    def _cmd_drift(self):
        try:
            drift = self.hub.get_fleet_drift()
        except Exception as e:
            return f"🔴 <b>Drift check failed:</b> <code>{html.escape(str(e)[:240], quote=True)}</code>", None

        items = (drift or {}).get("items") or []
        if not items:
            return "✅ <b>No fleet drift detected.</b>", self._main_keyboard()

        lines = [f"<b>⚠️ Fleet Drift ({len(items)} items)</b>"]
        for it in items[:20]:
            sev = html.escape(str(it.get("severity") or "info").upper(), quote=True)
            srv = html.escape(str(it.get("server") or "-"), quote=True)
            msg = html.escape(str(it.get("message") or it.get("kind") or ""), quote=True)
            lines.append(f"• <b>[{sev}]</b> <code>{srv}</code>: {msg}")
        if len(items) > 20:
            lines.append(f"… and {len(items) - 20} more.")
        return "\n".join(lines), self._main_keyboard()

    def _cmd_alerts(self):
        alerts = self.tracker.active_alerts()
        muted_rem = self.tracker.mute_remaining_sec()
        hdr = f"<b>🔔 Active Alerts ({len(alerts)})</b>"
        if muted_rem > 0:
            hdr += f" — <i>muted for {max(1, muted_rem // 60)}m</i>"
        if not alerts:
            return f"{hdr}\n✅ No firing incidents.", self._main_keyboard()
        lines = [hdr]
        for al in alerts[:20]:
            title = html.escape(str(al.get("title") or al.get("key") or ""), quote=True)
            detail = html.escape(str(al.get("detail") or ""), quote=True)
            streak = int(al.get("fail_streak", 0))
            lines.append(f"• 🔴 <code>{title}</code> (streak={streak})" + (f" — {detail}" if detail else ""))
        return "\n".join(lines), self._main_keyboard()

    def _cmd_relay(self):
        rt = self.relay.active_route()
        mode = html.escape(str(rt.get("mode") or "none"), quote=True)
        node = html.escape(str(rt.get("node") or "-"), quote=True)
        px = html.escape(str(rt.get("proxy") or "direct"), quote=True)
        return (
            "<b>🛰 Active Telegram Relay</b>\n"
            f"Route mode: <code>{mode}</code>\n"
            f"SSH node: <code>{node}</code>\n"
            f"Proxy: <code>{px}</code>",
            self._main_keyboard(),
        )

    def _cmd_test(self, args):
        if not args:
            return "Usage: <code>/test &lt;server&gt; [node]</code>", None
        srv = args[0]
        node = args[1] if len(args) > 1 else None
        if not RE_NAME.match(srv):
            return "❌ Invalid server name.", None
        if node and not RE_NAME.match(node):
            return "❌ Invalid node name.", None
        try:
            res = self.hub.link_test(srv, node=node, count=3)
        except Exception as e:
            return f"🔴 <b>Link test failed:</b> <code>{html.escape(str(e)[:240], quote=True)}</code>", None

        verdict = html.escape(str(res.get("verdict") or "unknown"), quote=True)
        diag = html.escape(str(res.get("diagnosis") or ""), quote=True)
        ir = res.get("iran_to_node") or {}
        nd = res.get("node_to_iran") or {}
        lines = [f"<b>🧪 Link Test: <code>{html.escape(srv, quote=True)}</code></b> — Verdict: <b>{verdict}</b>"]
        if diag:
            lines.append(diag)
        if isinstance(ir, dict) and ir.get("rtt_ms"):
            rtt = ir["rtt_ms"]
            lines.append(f"Iran→Node RTT avg={html.escape(str(rtt.get('avg', '?')), quote=True)}ms loss={html.escape(str(ir.get('loss_pct', '?')), quote=True)}%")
        if isinstance(nd, dict) and nd.get("rtt_ms"):
            rtt = nd["rtt_ms"]
            lines.append(f"Node→Iran RTT avg={html.escape(str(rtt.get('avg', '?')), quote=True)}ms loss={html.escape(str(nd.get('loss_pct', '?')), quote=True)}%")
        return "\n".join(lines), None

    def _cmd_doctor(self, args):
        if len(args) != 1 or not RE_NAME.match(args[0]):
            return "Usage: <code>/doctor &lt;server&gt;</code>", None
        srv = args[0]
        try:
            res = self.hub.run_action(srv, "doctor")
        except Exception as e:
            return f"🔴 <b>Doctor failed:</b> <code>{html.escape(str(e)[:240], quote=True)}</code>", None
        out = ((res.get("out") or "") + ("\n" + res.get("err") if res.get("err") else "")).strip()
        if len(out) > 3000:
            out = out[:3000] + "\n…"
        rc = res.get("rc", "?")
        return f"<b>🩺 Doctor <code>{html.escape(srv, quote=True)}</code> (rc={html.escape(str(rc), quote=True)})</b>\n<pre>{html.escape(out, quote=True)}</pre>", None

    def _cmd_restart(self, args):
        if not self.allow_remote_actions:
            return "⛔ Remote restart actions are disabled in monitor config.", None
        if len(args) != 1 or not RE_NAME.match(args[0]):
            return "Usage: <code>/restart &lt;server&gt;</code>", None
        srv = args[0]
        try:
            res = self.hub.run_action(srv, "restart")
        except Exception as e:
            return f"🔴 <b>Restart failed:</b> <code>{html.escape(str(e)[:240], quote=True)}</code>", None
        rc = res.get("rc", "?")
        out = (res.get("out") or res.get("err") or "").strip()[:800]
        icon = "✅" if rc == 0 else "⚠️"
        return (
            f"{icon} <b>Restart <code>{html.escape(srv, quote=True)}</code> (rc={html.escape(str(rc), quote=True)})</b>"
            + (f"\n<pre>{html.escape(out, quote=True)}</pre>" if out else ""),
            None,
        )

    def _cmd_mute(self, args):
        mins = 60
        if args:
            try:
                mins = int(args[0])
            except ValueError:
                return "Usage: <code>/mute [minutes 1..1440]</code>", None
        try:
            self.tracker.set_mute(mins)
        except ValueError as e:
            return f"❌ {html.escape(str(e), quote=True)}", None
        return f"🔕 Alert notifications muted for <b>{mins}</b> minute(s).", None

    def _cmd_unmute(self):
        self.tracker.clear_mute()
        return "🔔 Alert notifications resumed.", None

    def handle_update(self, update):
        if not isinstance(update, dict):
            return []

        cq = update.get("callback_query")
        if isinstance(cq, dict):
            msg = cq.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            if not self.is_authorized(chat_id):
                return []
            data = str(cq.get("data") or "").strip()
            cq_id = str(cq.get("id") or "")
            if data == "cb:status":
                text, rm = self._cmd_status()
            elif data == "cb:drift":
                text, rm = self._cmd_drift()
            elif data == "cb:alerts":
                text, rm = self._cmd_alerts()
            elif data == "cb:relay":
                text, rm = self._cmd_relay()
            else:
                text, rm = self._cmd_help()
            return [{
                "chat_id": int(chat_id),
                "text": text,
                "reply_markup": rm,
                "callback_query_id": cq_id,
            }]

        msg = update.get("message")
        if not isinstance(msg, dict):
            return []
        chat_id = (msg.get("chat") or {}).get("id")
        if not self.is_authorized(chat_id):
            return []

        raw_text = str(msg.get("text") or "").strip()
        if not raw_text.startswith("/"):
            return []
        parts = raw_text.split()
        cmd = parts[0].split("@", 1)[0].lower()
        args = parts[1:]

        if cmd in ("/start", "/help"):
            text, rm = self._cmd_help()
        elif cmd == "/status":
            text, rm = self._cmd_status()
        elif cmd == "/drift":
            text, rm = self._cmd_drift()
        elif cmd == "/test":
            text, rm = self._cmd_test(args)
        elif cmd == "/doctor":
            text, rm = self._cmd_doctor(args)
        elif cmd == "/restart":
            text, rm = self._cmd_restart(args)
        elif cmd == "/relay":
            text, rm = self._cmd_relay()
        elif cmd == "/alerts":
            text, rm = self._cmd_alerts()
        elif cmd == "/mute":
            text, rm = self._cmd_mute(args)
        elif cmd == "/unmute":
            text, rm = self._cmd_unmute()
        else:
            text = f"Unknown command: <code>{html.escape(cmd, quote=True)}</code>. Send /help for usage."
            rm = self._main_keyboard()

        return [{
            "chat_id": int(chat_id),
            "text": text,
            "reply_markup": rm,
            "callback_query_id": None,
        }]


def _read_hub_settings():
    inv_path = os.environ.get("RATHOLEHUB_INV", DEFAULT_HUB_INV)
    conf_path = os.environ.get("RATHOLEHUB_CONF", DEFAULT_HUB_CONF)
    inv = []
    ssh_key = ""
    ssh_opts = []
    if inv_path and os.path.exists(inv_path):
        try:
            with open(inv_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                inv = data
        except Exception:
            pass
    if conf_path and os.path.exists(conf_path):
        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                c = json.load(f)
            if isinstance(c, dict):
                ssh_key = str(c.get("ssh_key_path") or "")
                ssh_opts = list(c.get("ssh_opts") or [])
        except Exception:
            pass
    return inv, ssh_key, ssh_opts


def _build_runtime(cfg):
    hub_client = HubApiClient(
        hub_url=cfg.get("hub_url", "http://127.0.0.1:8088"),
        hub_token=cfg.get("hub_token", ""),
    )

    def _inv_fn():
        inv, _, _ = _read_hub_settings()
        if inv:
            return inv
        try:
            return hub_client.get_servers()
        except Exception:
            return []

    _, ssh_key, ssh_opts = _read_hub_settings()
    relay_mgr = TelegramRelayManager(
        relay_mode=cfg.get("relay_mode", "auto"),
        proxy_url=cfg.get("proxy", ""),
        inventory_fn=_inv_fn,
        ssh_key_path=ssh_key,
        ssh_opts=ssh_opts,
        api_base=cfg.get("api_base", "https://api.telegram.org"),
    )
    tracker = HysteresisTracker(
        fail_threshold=cfg.get("fail_threshold", 3),
        recover_threshold=cfg.get("recover_threshold", 2),
        cooldown_sec=cfg.get("cooldown_sec", 300),
        state_path=_state_path(),
    )
    tg_client = TelegramClient(cfg.get("bot_token", ""), relay_mgr) if cfg.get("bot_token") else None
    return hub_client, relay_mgr, tracker, tg_client


def run_once(cfg, hub_client=None, tracker=None, tg_client=None):
    own_relay = None
    if hub_client is None or tracker is None or (tg_client is None and cfg.get("bot_token")):
        hc, own_relay, tr, tc = _build_runtime(cfg)
        if hub_client is None:
            hub_client = hc
        if tracker is None:
            tracker = tr
        if tg_client is None:
            tg_client = tc

    try:
        obs, meta = collect_observations(hub_client, cert_warn_days=cfg.get("cert_warn_days", 14))
        events = tracker.evaluate(obs)
        sent = 0
        send_errors = []
        chats = list(cfg.get("allowed_chat_ids") or [])
        if tg_client is not None and chats and events:
            for ev in events:
                msg_html = format_alert_event(ev)
                for cid in chats:
                    try:
                        tg_client.send_message(cid, msg_html, parse_mode="HTML")
                        sent += 1
                    except Exception as e:
                        send_errors.append(redact_secrets(str(e), [cfg.get("bot_token"), cfg.get("proxy")]))
        return {
            "ok": not bool(meta.get("error")),
            "observations_count": len(obs),
            "events": events,
            "active_alerts": tracker.active_alerts(),
            "muted": tracker.is_muted(),
            "notifications_sent": sent,
            "send_errors": send_errors,
            "error": meta.get("error", ""),
        }
    finally:
        if own_relay is not None:
            own_relay.close()


def run_daemon(conf_path=None):
    stop_evt = threading.Event()

    def _on_sig(signum, _frame):
        sys.stderr.write(f"[ratholemonitor] received signal {signum}, stopping...\n")
        stop_evt.set()

    signal.signal(signal.SIGTERM, _on_sig)
    signal.signal(signal.SIGINT, _on_sig)

    cfg = load_monitor_config(conf_path)
    hub_client, relay_mgr, tracker, tg_client = _build_runtime(cfg)
    router = BotCommandRouter(
        hub_client,
        tracker,
        relay_mgr,
        cfg.get("allowed_chat_ids") or [],
        allow_remote_actions=cfg.get("allow_remote_actions", True),
    )

    def _bot_loop():
        offset = 0
        while not stop_evt.is_set():
            cur_cfg = load_monitor_config(conf_path)
            if not cur_cfg.get("enabled") or not cur_cfg.get("bot_enabled") or not cur_cfg.get("bot_token"):
                stop_evt.wait(5)
                continue
            router.allowed_chat_ids = set(int(x) for x in (cur_cfg.get("allowed_chat_ids") or []) if str(x).lstrip("-").isdigit())
            router.allow_remote_actions = bool(cur_cfg.get("allow_remote_actions", True))
            tg = TelegramClient(cur_cfg.get("bot_token", ""), relay_mgr)
            try:
                updates = tg.get_updates(offset=offset, timeout=20)
                for upd in updates:
                    if isinstance(upd, dict) and "update_id" in upd:
                        offset = max(offset, int(upd["update_id"]) + 1)
                    actions = router.handle_update(upd)
                    for act in actions:
                        if act.get("callback_query_id"):
                            try:
                                tg.answer_callback_query(act["callback_query_id"])
                            except Exception:
                                pass
                        tg.send_message(act["chat_id"], act["text"], parse_mode="HTML", reply_markup=act.get("reply_markup"))
            except Exception as e:
                sys.stderr.write("[ratholemonitor] bot loop: %s\n" % redact_secrets(str(e), [cur_cfg.get("bot_token"), cur_cfg.get("proxy")]))
                stop_evt.wait(5)

    bot_thread = threading.Thread(target=_bot_loop, daemon=True)
    bot_thread.start()

    try:
        while not stop_evt.is_set():
            cur_cfg = load_monitor_config(conf_path)
            relay_mgr.relay_mode = cur_cfg.get("relay_mode", "auto") if cur_cfg.get("relay_mode") in RELAY_MODES else "auto"
            relay_mgr.proxy_url = str(cur_cfg.get("proxy") or "").strip()
            tracker.fail_threshold = max(1, int(cur_cfg.get("fail_threshold", 3)))
            tracker.recover_threshold = max(1, int(cur_cfg.get("recover_threshold", 2)))
            tracker.cooldown_sec = max(0, int(cur_cfg.get("cooldown_sec", 300)))

            interval = max(15, int(cur_cfg.get("poll_interval_sec", 60) or 60))
            if cur_cfg.get("enabled"):
                tc = TelegramClient(cur_cfg.get("bot_token", ""), relay_mgr) if cur_cfg.get("bot_token") else None
                try:
                    run_once(cur_cfg, hub_client=hub_client, tracker=tracker, tg_client=tc)
                except Exception as e:
                    sys.stderr.write("[ratholemonitor] poll error: %s\n" % redact_secrets(str(e), [cur_cfg.get("bot_token"), cur_cfg.get("proxy")]))
            stop_evt.wait(interval)
    finally:
        relay_mgr.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ratholemonitor", description="Standalone monitor & Telegram bot for RatholeEngine Hub")
    parser.add_argument("--conf", default=None, help="Path to monitor.json")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("run", help="Run monitor daemon loop + Telegram bot")
    p_once = sub.add_parser("once", help="Run a single poll and hysteresis evaluation")
    p_once.add_argument("--json", action="store_true", help="Output JSON")
    p_diag = sub.add_parser("diagnose-relay", help="Probe direct, proxy, and foreign SSH node Telegram paths")
    p_diag.add_argument("--json", action="store_true", help="Output JSON")
    sub.add_parser("send-test", help="Send a test alert to allowed_chat_ids")

    args = parser.parse_args(argv)
    cmd = args.cmd or "run"
    cfg = load_monitor_config(args.conf)

    if cmd == "run":
        run_daemon(args.conf)
        return 0

    if cmd == "once":
        res = run_once(cfg)
        if getattr(args, "json", False):
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"ok={res['ok']} obs={res['observations_count']} events={len(res['events'])} active={len(res['active_alerts'])}")
        return 0 if res.get("ok") else 1

    if cmd == "diagnose-relay":
        inv, ssh_key, ssh_opts = _read_hub_settings()
        res = diagnose_relay(
            cfg.get("bot_token", ""),
            inv,
            proxy_url=cfg.get("proxy", ""),
            ssh_key_path=ssh_key,
            ssh_opts=ssh_opts,
            api_base=cfg.get("api_base", "https://api.telegram.org"),
        )
        if getattr(args, "json", False):
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(res["summary"])
            print("recommended_mode:", res["recommended_mode"], "best_ssh_node:", res["best_ssh_node"])
        return 0

    if cmd == "send-test":
        tok = str(cfg.get("bot_token") or "").strip()
        chats = list(cfg.get("allowed_chat_ids") or [])
        if not tok or not chats:
            sys.stderr.write("error: bot_token and allowed_chat_ids must be configured\n")
            return 1
        _, relay_mgr, _, tg = _build_runtime(cfg)
        try:
            for cid in chats:
                tg.send_message(cid, "🔔 <b>RatholeEngine Monitor</b>: test delivery succeeded.", parse_mode="HTML")
            rt = relay_mgr.active_route()
            print(f"ok via {rt.get('mode')} (node={rt.get('node') or '-'}) sent={len(chats)}")
            return 0
        finally:
            relay_mgr.close()

    return 1


if __name__ == "__main__":
    sys.exit(main())
