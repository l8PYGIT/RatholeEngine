# hubsec.py — security helpers baraye ratholehub (stdlib only, Python 3.8+).
# Shamel: scoped tokens (read/operate/admin), RFC 6238 TOTP + recovery codes,
# CSRF check baraye cookie sessions, hash-chained audit log, va Prometheus /metrics.

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import time
from urllib.parse import quote, urlparse

SCOPES = ("read", "operate", "admin")
SCOPE_RANK = {"read": 1, "operate": 2, "admin": 3}
RE_TOKEN_NAME = re.compile(r"^[A-Za-z0-9 _.-]{1,48}\Z")
GENESIS_HASH = "0" * 64


def _hdr(headers, name):
    if not headers:
        return ""
    if hasattr(headers, "get"):
        v = headers.get(name)
        if v is not None:
            return str(v)
        target = name.lower()
        try:
            for k, val in headers.items():
                if str(k).lower() == target:
                    return "" if val is None else str(val)
        except Exception:
            pass
    return ""


def scope_allows(granted, required):
    return SCOPE_RANK.get(granted, 0) >= SCOPE_RANK.get(required, 99)


def hash_token(raw_token):
    return hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()


def create_scoped_token(name, scope, expires_at=None, now=None):
    if scope not in SCOPES:
        raise ValueError("invalid scope (expected read, operate, or admin)")
    clean_name = str(name or "").strip()
    if not RE_TOKEN_NAME.match(clean_name):
        raise ValueError("invalid token name (1..48 safe chars)")
    exp_val = None
    if expires_at is not None:
        exp_val = int(expires_at)
        if exp_val <= 0:
            raise ValueError("expires_at must be positive epoch seconds")
    ts = int(time.time() if now is None else now)
    raw = "rht_" + secrets.token_urlsafe(32)
    rec = {
        "id": "tok_" + secrets.token_hex(6),
        "name": clean_name,
        "scope": scope,
        "prefix": raw[:10],
        "sha256": hash_token(raw),
        "created_at": ts,
        "expires_at": exp_val,
    }
    return raw, rec


def public_token_view(rec):
    return {
        "id": rec.get("id", ""),
        "name": rec.get("name", ""),
        "scope": rec.get("scope", "read"),
        "prefix": rec.get("prefix", ""),
        "created_at": rec.get("created_at"),
        "expires_at": rec.get("expires_at"),
    }


def resolve_auth(cfg, headers, cookies, check_session_fn, now=None):
    """Return {'scope', 'via', 'principal'} if authenticated, else None."""
    if not isinstance(cfg, dict):
        return None
    now_ts = int(time.time() if now is None else now)
    auth = _hdr(headers, "Authorization").strip()
    if auth.lower().startswith("bearer "):
        cand = auth[7:].strip()
        if not cand:
            return None
        cfg_tok = str(cfg.get("api_token") or "")
        if cfg_tok and hmac.compare_digest(cand, cfg_tok):
            return {"scope": "admin", "via": "bearer", "principal": "api"}
        h_cand = hash_token(cand)
        matched = None
        for rec in (cfg.get("tokens") or []):
            if not isinstance(rec, dict):
                continue
            stored = str(rec.get("sha256") or "")
            if stored and hmac.compare_digest(h_cand, stored):
                matched = rec
        if matched is not None:
            exp = matched.get("expires_at")
            if exp is not None and int(exp) <= now_ts:
                return None
            scope = matched.get("scope")
            if scope not in SCOPES:
                return None
            label = matched.get("name") or matched.get("id") or "token"
            return {"scope": scope, "via": "bearer", "principal": "token:%s" % label}
        return None

    sess = (cookies or {}).get("rhsession", "")
    if sess and check_session_fn(cfg, sess):
        return {"scope": "admin", "via": "cookie", "principal": "admin"}
    return None


def check_csrf(headers, auth_info):
    """Enforce same-origin guarantees on cookie-authenticated mutations."""
    if not auth_info or auth_info.get("via") != "cookie":
        return True, ""

    sfs = _hdr(headers, "Sec-Fetch-Site").strip().lower()
    if sfs == "cross-site":
        return False, "csrf cross-site request blocked"

    allowed = set()
    host = _hdr(headers, "Host").strip().lower()
    if host:
        allowed.add(host)
    xfh = _hdr(headers, "X-Forwarded-Host").strip()
    if xfh:
        first = xfh.split(",", 1)[0].strip().lower()
        if first:
            allowed.add(first)

    origin = _hdr(headers, "Origin").strip()
    if origin:
        if origin.lower() == "null":
            return False, "csrf null origin blocked"
        netloc = urlparse(origin).netloc.lower()
        if not netloc or netloc not in allowed:
            return False, "csrf origin mismatch"
        return True, ""

    referer = _hdr(headers, "Referer").strip()
    if referer:
        netloc = urlparse(referer).netloc.lower()
        if not netloc or netloc not in allowed:
            return False, "csrf referer mismatch"

    return True, ""


def generate_totp_secret():
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def totp_code(secret_b32, for_time=None, period=30, digits=6):
    s = str(secret_b32 or "").strip().upper().replace(" ", "")
    pad = (-len(s)) % 8
    key = base64.b32decode(s + ("=" * pad), casefold=True)
    ts = time.time() if for_time is None else float(for_time)
    counter = int(ts // period)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    val = (struct.unpack(">I", digest[off : off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(val).zfill(digits)


def verify_totp(secret_b32, code, for_time=None, period=30, window=1, last_step=None):
    clean = re.sub(r"[\s-]", "", str(code or ""))
    if not re.match(r"^[0-9]{6}\Z", clean) or not secret_b32:
        return None
    ts = time.time() if for_time is None else float(for_time)
    base_step = int(ts // period)
    for off in range(-int(window), int(window) + 1):
        step = base_step + off
        if step < 0:
            continue
        if last_step is not None and step <= int(last_step):
            continue
        expected = totp_code(secret_b32, for_time=step * period, period=period)
        if hmac.compare_digest(expected, clean):
            return step
    return None


def totp_provisioning_uri(secret_b32, account="admin", issuer="RatholeHub"):
    label = "%s:%s" % (quote(issuer, safe=""), quote(account, safe=""))
    return "otpauth://totp/%s?secret=%s&issuer=%s&algorithm=SHA1&digits=6&period=30" % (
        label,
        quote(str(secret_b32 or "").strip().upper(), safe=""),
        quote(issuer, safe=""),
    )


def generate_recovery_codes(count=8):
    plain = []
    hashes = []
    for _ in range(int(count)):
        raw = secrets.token_hex(4).upper()
        plain.append("%s-%s" % (raw[:4], raw[4:]))
        hashes.append(hashlib.sha256(raw.encode("ascii")).hexdigest())
    return plain, hashes


def consume_recovery_code(stored_hashes, code):
    norm = re.sub(r"[\s-]", "", str(code or "")).upper()
    cur = list(stored_hashes or [])
    if not re.match(r"^[A-F0-9]{8}\Z", norm):
        return False, cur
    h_cand = hashlib.sha256(norm.encode("ascii")).hexdigest()
    match_idx = None
    for idx, stored in enumerate(cur):
        if isinstance(stored, str) and hmac.compare_digest(h_cand, stored):
            match_idx = idx
    if match_idx is None:
        return False, cur
    rem = cur[:match_idx] + cur[match_idx + 1 :]
    return True, rem


def compute_audit_hash(entry):
    payload = {k: v for k, v in entry.items() if k != "hash"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def last_audit_hash(audit_path):
    try:
        with open(audit_path, "r", encoding="utf-8", errors="replace") as f:
            last_line = ""
            for ln in f:
                s = ln.strip()
                if s:
                    last_line = s
        if not last_line:
            return GENESIS_HASH
        obj = json.loads(last_line)
        h = obj.get("hash") if isinstance(obj, dict) else None
        if isinstance(h, str) and re.match(r"^[a-f0-9]{64}\Z", h):
            return h
    except Exception:
        pass
    return GENESIS_HASH


def build_chained_audit_entry(user, server, action, cmd, rc, prev_hash, ts=None):
    entry = {
        "ts": int(time.time() if ts is None else ts),
        "user": user,
        "server": server,
        "action": action,
        "cmd": cmd,
        "rc": rc,
        "prev_hash": prev_hash or GENESIS_HASH,
    }
    entry["hash"] = compute_audit_hash(entry)
    return entry


def verify_audit_chain(audit_path):
    if not audit_path or not os.path.exists(audit_path):
        return {
            "ok": True, "total": 0, "chained": 0, "legacy": 0,
            "broken_line": None, "error": None, "head_hash": GENESIS_HASH,
        }
    chained = 0
    legacy = 0
    expected_prev = GENESIS_HASH
    try:
        with open(audit_path, "r", encoding="utf-8", errors="replace") as f:
            for lineno, raw in enumerate(f, 1):
                s = raw.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                    if not isinstance(obj, dict):
                        raise ValueError("not object")
                except Exception:
                    return {
                        "ok": False, "total": chained + legacy, "chained": chained, "legacy": legacy,
                        "broken_line": lineno, "error": "invalid json", "head_hash": expected_prev,
                    }
                if "hash" not in obj and "prev_hash" not in obj:
                    if chained == 0:
                        legacy += 1
                        continue
                    return {
                        "ok": False, "total": chained + legacy, "chained": chained, "legacy": legacy,
                        "broken_line": lineno, "error": "unchained entry after chain start", "head_hash": expected_prev,
                    }
                if str(obj.get("prev_hash", "")) != expected_prev:
                    return {
                        "ok": False, "total": chained + legacy, "chained": chained, "legacy": legacy,
                        "broken_line": lineno, "error": "prev_hash mismatch", "head_hash": expected_prev,
                    }
                good_hash = compute_audit_hash(obj)
                if not hmac.compare_digest(str(obj.get("hash", "")), good_hash):
                    return {
                        "ok": False, "total": chained + legacy, "chained": chained, "legacy": legacy,
                        "broken_line": lineno, "error": "hash mismatch (tampered)", "head_hash": expected_prev,
                    }
                expected_prev = good_hash
                chained += 1
    except OSError as e:
        return {
            "ok": False, "total": chained + legacy, "chained": chained, "legacy": legacy,
            "broken_line": None, "error": str(e), "head_hash": expected_prev,
        }
    return {
        "ok": True, "total": chained + legacy, "chained": chained, "legacy": legacy,
        "broken_line": None, "error": None, "head_hash": expected_prev,
    }


def _prom_esc(val):
    return str(val or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_prometheus_metrics(stats):
    st = stats or {}
    lines = [
        "# HELP ratholehub_up Hub HTTP control plane health (1 = up).",
        "# TYPE ratholehub_up gauge",
        "ratholehub_up 1",
        "# HELP ratholehub_uptime_seconds Seconds since Hub process started.",
        "# TYPE ratholehub_uptime_seconds gauge",
        "ratholehub_uptime_seconds %d" % int(st.get("uptime_seconds", 0)),
        "# HELP ratholehub_inventory_servers_total Configured servers by role.",
        "# TYPE ratholehub_inventory_servers_total gauge",
    ]
    inv_counts = st.get("inventory_counts") or {}
    for role in ("iran", "node"):
        lines.append('ratholehub_inventory_servers_total{role="%s"} %d' % (_prom_esc(role), int(inv_counts.get(role, 0))))

    cache = st.get("overview_cache") or {}
    lines.extend([
        "# HELP ratholehub_server_reachable Cached reachability per server (1 = reachable).",
        "# TYPE ratholehub_server_reachable gauge",
    ])
    for sname in sorted(cache):
        ov = cache[sname] or {}
        role = ov.get("role") or "unknown"
        lines.append(
            'ratholehub_server_reachable{server="%s",role="%s"} %d'
            % (_prom_esc(sname), _prom_esc(role), 0 if ov.get("reachable") is False else 1)
        )

    lines.extend([
        "# HELP ratholehub_server_nodes_total Cached configured nodes on Iran panel.",
        "# TYPE ratholehub_server_nodes_total gauge",
    ])
    for sname in sorted(cache):
        ov = cache[sname] or {}
        if ov.get("role") == "iran" and ov.get("reachable") is not False:
            lines.append('ratholehub_server_nodes_total{server="%s"} %d' % (_prom_esc(sname), len(ov.get("nodes") or [])))

    lines.extend([
        "# HELP ratholehub_server_services_total Cached configured services on foreign node.",
        "# TYPE ratholehub_server_services_total gauge",
    ])
    for sname in sorted(cache):
        ov = cache[sname] or {}
        if ov.get("role") != "iran" and ov.get("reachable") is not False:
            cnt = len(ov.get("services") or []) + len(ov.get("backhaul_services") or [])
            lines.append('ratholehub_server_services_total{server="%s"} %d' % (_prom_esc(sname), cnt))

    drift = st.get("drift_summary")
    lines.extend([
        "# HELP ratholehub_drift_issues_total Last observed fleet drift issues by severity.",
        "# TYPE ratholehub_drift_issues_total gauge",
    ])
    for sev in ("error", "warning", "info"):
        val = int((drift or {}).get(sev, 0)) if isinstance(drift, dict) else 0
        lines.append('ratholehub_drift_issues_total{severity="%s"} %d' % (sev, val))

    lines.extend([
        "# HELP ratholehub_audit_entries_total Total entries recorded in Hub audit log.",
        "# TYPE ratholehub_audit_entries_total gauge",
        "ratholehub_audit_entries_total %d" % int(st.get("audit_total", 0)),
        "# HELP ratholehub_login_failures_total Failed login attempts since Hub start.",
        "# TYPE ratholehub_login_failures_total counter",
        "ratholehub_login_failures_total %d" % int(st.get("login_failures_total", 0)),
        "# HELP ratholehub_http_requests_total HTTP requests served by method since Hub start.",
        "# TYPE ratholehub_http_requests_total counter",
    ])
    reqs = st.get("http_requests_by_method") or {}
    for meth in ("GET", "POST", "PUT", "DELETE"):
        lines.append('ratholehub_http_requests_total{method="%s"} %d' % (meth, int(reqs.get(meth, 0))))

    return "\n".join(lines) + "\n"
