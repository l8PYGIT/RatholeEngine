"""Portable AI-analyzable JSON & Base64url (rthprof1:...) network profile codec."""

from __future__ import annotations

import base64
import copy
import datetime
import hashlib
import json
import os
import re
import secrets
import zlib

from . import MAX_PROFILE_B64_LEN, MAX_PROFILE_JSON_BYTES, PROFILE_PREFIX, SCHEMA_VERSION, TUNER_VERSION


class ProfileValidationError(ValueError):
    """Raised when an imported or exported network profile fails validation."""


ALLOWED_QDISCS = frozenset({"default", "pfifo_fast", "fq", "fq_codel", "cake"})
ALLOWED_OFFLOADS = frozenset({"tso", "gso", "gro", "lro"})
ALLOWED_CC = frozenset({"bbr", "bbr2", "bbr3", "cubic", "hybla", "westwood", "reno", "vegas", "bic", "htcp"})

_ALLOWED_SYSCTL_ENUMS = {
    "net.core.default_qdisc": frozenset({"fq", "fq_codel", "cake", "pfifo_fast"}),
    "net.ipv4.tcp_congestion_control": ALLOWED_CC,
}

_ALLOWED_SYSCTL_INTS = {
    "net.ipv4.tcp_notsent_lowat": (4096, 4294967295),
    "net.ipv4.tcp_mtu_probing": (0, 2),
    "net.ipv4.tcp_base_mss": (512, 1460),
    "net.ipv4.tcp_min_snd_mss": (48, 1460),
    "net.ipv4.tcp_slow_start_after_idle": (0, 1),
    "net.ipv4.tcp_ecn": (0, 2),
    "net.ipv4.tcp_timestamps": (0, 1),
    "net.ipv4.tcp_fastopen": (0, 3),
    "net.ipv4.tcp_sack": (0, 1),
    "net.ipv4.tcp_dsack": (0, 1),
    "net.ipv4.tcp_autocorking": (0, 1),
    "net.ipv4.tcp_frto": (0, 2),
    "net.ipv4.tcp_early_retrans": (0, 4),
    "net.ipv4.tcp_thin_linear_timeouts": (0, 1),
    "net.ipv4.tcp_tw_reuse": (0, 2),
    "net.core.rmem_max": (4096, 67108864),
    "net.core.wmem_max": (4096, 67108864),
    "net.core.rmem_default": (4096, 67108864),
    "net.core.wmem_default": (4096, 67108864),
    "net.core.netdev_max_backlog": (1000, 262144),
    "net.core.netdev_budget": (100, 65536),
    "net.core.somaxconn": (128, 262144),
    "net.ipv4.tcp_max_syn_backlog": (128, 262144),
    "net.ipv4.udp_rmem_min": (4096, 1048576),
    "net.ipv4.udp_wmem_min": (4096, 1048576),
    "net.netfilter.nf_conntrack_max": (16384, 8388608),
}

_ALLOWED_SYSCTL_TRIPLETS = {
    "net.ipv4.tcp_rmem": (4096, 67108864),
    "net.ipv4.tcp_wmem": (4096, 67108864),
}

ALLOWED_SYSCTL_SPEC = (
    set(_ALLOWED_SYSCTL_ENUMS) | set(_ALLOWED_SYSCTL_INTS) | set(_ALLOWED_SYSCTL_TRIPLETS)
)

_FORBIDDEN_PII_KEYS = frozenset({
    "ip", "host", "peer", "peer_ip", "public_ip", "remote_ip", "local_ip",
    "domain", "sni", "token", "api_token", "secret", "password", "key",
    "private_key", "privatekey", "hmac", "ssh_host",
})

_IPV4_RE = re.compile(r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b")
_SHELL_BAD_RE = re.compile(r"[;&|`$<>\\\r\n]")
_SAFE_TAG_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,80}$")

_SINGLE_MEM_KEYS = ("net.core.rmem_max", "net.core.wmem_max", "net.core.rmem_default", "net.core.wmem_default")
_TRIPLET_MEM_KEYS = ("net.ipv4.tcp_rmem", "net.ipv4.tcp_wmem")


def compute_ram_buffer_cap(ram_mb: int) -> int:
    """Return max safe socket buffer bytes: min(64 MiB, 10% of host RAM), floor 256 KiB."""
    ram = max(64, int(ram_mb))
    return min(67108864, max(262144, int(ram * 1024 * 1024 * 0.10)))


def clamp_config_for_ram(side_cfg: dict, ram_mb: int) -> dict:
    """Return a copy of side_cfg whose buffer sysctls fit within 10% of ram_mb."""
    out = copy.deepcopy(side_cfg or {})
    sysctl = out.get("sysctl")
    if not isinstance(sysctl, dict):
        return out
    cap = compute_ram_buffer_cap(ram_mb)
    for k in _SINGLE_MEM_KEYS:
        if k in sysctl:
            sysctl[k] = min(int(sysctl[k]), cap)
    for k in _TRIPLET_MEM_KEYS:
        if k in sysctl:
            lo, mid, hi = [int(p) for p in str(sysctl[k]).split()]
            hi = min(hi, cap)
            mid = min(mid, hi)
            lo = min(lo, mid)
            sysctl[k] = f"{lo} {mid} {hi}"
    return out


def sanitize_pii(obj):
    """Deep-copy obj while stripping IPs, domains, and credential keys."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if str(k).lower() in _FORBIDDEN_PII_KEYS:
                continue
            cleaned[k] = sanitize_pii(v)
        return cleaned
    if isinstance(obj, list):
        return [sanitize_pii(x) for x in obj]
    if isinstance(obj, str):
        return _IPV4_RE.sub("<redacted-ip>", obj)
    return obj


def _canonical_without_integrity(profile: dict) -> bytes:
    payload = {k: v for k, v in profile.items() if k != "integrity"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_integrity_sha256(profile: dict) -> str:
    """Compute SHA-256 digest of the canonical profile payload excluding 'integrity'."""
    return hashlib.sha256(_canonical_without_integrity(profile)).hexdigest()


def _validate_int_range(name: str, val, lo: int, hi: int) -> int:
    if isinstance(val, bool) or not isinstance(val, int) or val < lo or val > hi:
        raise ProfileValidationError(f"{name} must be integer in [{lo}, {hi}], got {val!r}")
    return val


def _validate_sysctl_map(sysctl: dict, side: str) -> dict:
    if not isinstance(sysctl, dict):
        raise ProfileValidationError(f"{side}.sysctl must be a dict")
    cleaned = {}
    for k, v in sysctl.items():
        if not isinstance(k, str) or k not in ALLOWED_SYSCTL_SPEC:
            raise ProfileValidationError(f"{side}.sysctl key not allowed: {k!r}")
        if isinstance(v, str) and _SHELL_BAD_RE.search(v):
            raise ProfileValidationError(f"{side}.sysctl[{k}] contains forbidden characters")
        if k in _ALLOWED_SYSCTL_ENUMS:
            sv = str(v).strip()
            if sv not in _ALLOWED_SYSCTL_ENUMS[k]:
                raise ProfileValidationError(f"{side}.sysctl[{k}] invalid enum {sv!r}")
            cleaned[k] = sv
        elif k in _ALLOWED_SYSCTL_INTS:
            lo, hi = _ALLOWED_SYSCTL_INTS[k]
            iv = int(v) if isinstance(v, str) and v.isdigit() else v
            cleaned[k] = _validate_int_range(f"{side}.sysctl[{k}]", iv, lo, hi)
        else:
            lo, hi = _ALLOWED_SYSCTL_TRIPLETS[k]
            parts = str(v).split()
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                raise ProfileValidationError(f"{side}.sysctl[{k}] must be 3 space-separated ints")
            nums = [int(p) for p in parts]
            if any(x < lo or x > hi for x in nums) or not (nums[0] <= nums[1] <= nums[2]):
                raise ProfileValidationError(f"{side}.sysctl[{k}] ordering/range invalid: {nums}")
            cleaned[k] = f"{nums[0]} {nums[1]} {nums[2]}"
    return cleaned


def _validate_side_config(cfg: dict, side: str) -> dict:
    if not isinstance(cfg, dict):
        raise ProfileValidationError(f"{side} must be a dict")
    out = {}
    if "mtu" in cfg and cfg["mtu"] is not None:
        out["mtu"] = _validate_int_range(f"{side}.mtu", cfg["mtu"], 576, 1500)
    if "mss_clamp" in cfg and cfg["mss_clamp"] is not None:
        mv = _validate_int_range(f"{side}.mss_clamp", cfg["mss_clamp"], 0, 1460)
        if mv != 0 and mv < 536:
            raise ProfileValidationError(f"{side}.mss_clamp must be 0 or in [536, 1460]")
        out["mss_clamp"] = mv
    if "txqueuelen" in cfg and cfg["txqueuelen"] is not None:
        out["txqueuelen"] = _validate_int_range(f"{side}.txqueuelen", cfg["txqueuelen"], 100, 20000)
    if "qdisc" in cfg and cfg["qdisc"] is not None:
        qd = cfg["qdisc"]
        if not isinstance(qd, dict) or qd.get("kind") not in ALLOWED_QDISCS:
            raise ProfileValidationError(f"{side}.qdisc invalid: {qd!r}")
        params = qd.get("params") or {}
        if not isinstance(params, dict):
            raise ProfileValidationError(f"{side}.qdisc.params must be a dict")
        clean_params = {}
        if "bandwidth_mbps" in params and params["bandwidth_mbps"] is not None:
            clean_params["bandwidth_mbps"] = _validate_int_range(
                f"{side}.qdisc.params.bandwidth_mbps", params["bandwidth_mbps"], 1, 100000
            )
        out["qdisc"] = {"kind": qd["kind"], "params": clean_params}
    if "route" in cfg and cfg["route"] is not None:
        rt = cfg["route"]
        if not isinstance(rt, dict):
            raise ProfileValidationError(f"{side}.route must be a dict")
        clean_rt = {}
        for rk in ("initcwnd", "initrwnd"):
            if rk in rt and rt[rk] is not None:
                clean_rt[rk] = _validate_int_range(f"{side}.route.{rk}", rt[rk], 4, 128)
        if "advmss" in rt and rt["advmss"] is not None:
            adv = _validate_int_range(f"{side}.route.advmss", rt["advmss"], 0, 1460)
            if adv != 0 and adv < 536:
                raise ProfileValidationError(f"{side}.route.advmss must be 0 or in [536, 1460]")
            clean_rt["advmss"] = adv
        out["route"] = clean_rt
    if "offloads" in cfg and cfg["offloads"] is not None:
        offs = cfg["offloads"]
        if not isinstance(offs, dict):
            raise ProfileValidationError(f"{side}.offloads must be a dict")
        clean_offs = {}
        for ok, ov in offs.items():
            if ok not in ALLOWED_OFFLOADS or type(ov) is not bool:
                raise ProfileValidationError(f"{side}.offloads[{ok!r}] invalid")
            clean_offs[ok] = ov
        out["offloads"] = clean_offs
    if "sysctl" in cfg and cfg["sysctl"] is not None:
        out["sysctl"] = _validate_sysctl_map(cfg["sysctl"], side)
    if "recommended_carrier" in cfg and cfg["recommended_carrier"] is not None:
        rc = cfg["recommended_carrier"]
        if not isinstance(rc, dict):
            raise ProfileValidationError(f"{side}.recommended_carrier must be a dict")
        for k, v in rc.items():
            if isinstance(v, str) and _SHELL_BAD_RE.search(v):
                raise ProfileValidationError(f"{side}.recommended_carrier contains unsafe chars")
        out["recommended_carrier"] = copy.deepcopy(rc)
    return out


def validate_profile(profile: dict, host_ram_mb: int | None = None, verify_sha: bool = True) -> dict:
    """Validate structure, integrity SHA-256, and strict allow-list constraints."""
    if not isinstance(profile, dict):
        raise ProfileValidationError("profile must be a JSON object")
    if profile.get("schema") != SCHEMA_VERSION:
        raise ProfileValidationError(f"unsupported schema: {profile.get('schema')!r}")
    if "iran_config" not in profile or "node_config" not in profile:
        raise ProfileValidationError("profile missing iran_config or node_config")

    if verify_sha:
        integ = profile.get("integrity")
        if not isinstance(integ, dict) or not isinstance(integ.get("sha256"), str):
            raise ProfileValidationError("missing integrity.sha256")
        expected = compute_integrity_sha256(profile)
        if not re.fullmatch(r"[0-9a-f]{64}", integ["sha256"]) or expected != integ["sha256"]:
            raise ProfileValidationError("integrity sha256 mismatch")

    cleaned = copy.deepcopy(profile)
    cleaned["iran_config"] = _validate_side_config(cleaned["iran_config"], "iran_config")
    cleaned["node_config"] = _validate_side_config(cleaned["node_config"], "node_config")
    if host_ram_mb is not None:
        cleaned["iran_config"] = clamp_config_for_ram(cleaned["iran_config"], host_ram_mb)
        cleaned["node_config"] = clamp_config_for_ram(cleaned["node_config"], host_ram_mb)
    return cleaned


def build_profile(
    meta: dict,
    environment: dict,
    diagnostics: list,
    benchmarks: dict,
    iran_config: dict,
    node_config: dict,
    non_kernel_recommendations: dict | None = None,
    strip_pii: bool = True,
) -> dict:
    """Construct a complete canonical rathole.netprofile.v1 object with SHA-256."""
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    raw_meta = dict(meta or {})
    raw_meta.setdefault("id", f"prof_{ts_tag}_{secrets.token_hex(3)}")
    raw_meta.setdefault("name", "custom-profile")
    raw_meta.setdefault("created_at", now_iso)
    raw_meta.setdefault("tuner_version", TUNER_VERSION)
    raw_meta.setdefault("mode", "brutal")
    raw_meta.setdefault("goal", "balanced")
    raw_meta.setdefault("tags", {})

    doc = {
        "schema": SCHEMA_VERSION,
        "meta": raw_meta,
        "environment": environment or {},
        "diagnostics": diagnostics or [],
        "benchmarks": benchmarks or {},
        "iran_config": _validate_side_config(iran_config or {}, "iran_config"),
        "node_config": _validate_side_config(node_config or {}, "node_config"),
        "non_kernel_recommendations": non_kernel_recommendations or {"nginx": [], "xray": [], "system": []},
    }
    if strip_pii:
        doc = sanitize_pii(doc)
    doc["integrity"] = {"sha256": compute_integrity_sha256(doc)}
    return validate_profile(doc, verify_sha=True)


def encode_profile_b64(profile: dict) -> str:
    """Validate and encode a profile into compact rthprof1:<base64url(gzip)> form."""
    valid = validate_profile(profile, verify_sha=False)
    if "integrity" not in valid or valid["integrity"].get("sha256") != compute_integrity_sha256(valid):
        valid["integrity"] = {"sha256": compute_integrity_sha256(valid)}
    raw = json.dumps(valid, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    comp = zlib.compressobj(level=9, wbits=31)
    gz = comp.compress(raw) + comp.flush()
    b64 = base64.urlsafe_b64encode(gz).decode("ascii").rstrip("=")
    token = PROFILE_PREFIX + b64
    if len(token) > MAX_PROFILE_B64_LEN:
        raise ProfileValidationError(f"encoded profile exceeds max length ({len(token)} > {MAX_PROFILE_B64_LEN})")
    return token


def _safe_gunzip(gz_bytes: bytes, max_bytes: int = MAX_PROFILE_JSON_BYTES) -> bytes:
    decomp = zlib.decompressobj(wbits=31)
    out = decomp.decompress(gz_bytes, max_bytes + 1)
    if len(out) > max_bytes or decomp.unconsumed_tail:
        raise ProfileValidationError(f"decompressed profile exceeds {max_bytes} bytes limit")
    tail = decomp.flush()
    if len(out) + len(tail) > max_bytes:
        raise ProfileValidationError(f"decompressed profile exceeds {max_bytes} bytes limit")
    if decomp.unused_data:
        raise ProfileValidationError("trailing bytes after gzip profile archive")
    return out + tail


def decode_profile_b64(text: str, verify_sha: bool = True) -> dict:
    """Decode and strictly validate an rthprof1:... Base64url profile string."""
    s = str(text or "").strip()
    if not s.startswith(PROFILE_PREFIX):
        raise ProfileValidationError("profile string must start with 'rthprof1:'")
    if len(s) > MAX_PROFILE_B64_LEN:
        raise ProfileValidationError("encoded profile exceeds maximum size")
    body = s[len(PROFILE_PREFIX):]
    if not body or not re.fullmatch(r"[A-Za-z0-9_-]+", body):
        raise ProfileValidationError("invalid base64url characters in profile")
    pad = "=" * ((4 - len(body) % 4) % 4)
    try:
        gz = base64.urlsafe_b64decode((body + pad).encode("ascii"))
    except Exception as exc:
        raise ProfileValidationError(f"base64url decode failed: {exc}") from exc
    if base64.urlsafe_b64encode(gz).decode("ascii").rstrip("=") != body:
        raise ProfileValidationError("non-canonical base64url padding bits")
    try:
        raw = _safe_gunzip(gz, MAX_PROFILE_JSON_BYTES)
        obj = json.loads(raw.decode("utf-8"))
    except ProfileValidationError:
        raise
    except Exception as exc:
        raise ProfileValidationError(f"corrupt profile archive or JSON: {exc}") from exc
    return validate_profile(obj, verify_sha=verify_sha)


def load_profile_any(spec: str, verify_sha: bool = True) -> dict:
    """Load and validate a profile from rthprof1:... string, JSON string, or file path."""
    s = str(spec or "").strip()
    if not s:
        raise ProfileValidationError("empty profile specification")
    if s.startswith(PROFILE_PREFIX):
        return decode_profile_b64(s, verify_sha=verify_sha)
    if s.startswith("{"):
        if len(s.encode("utf-8")) > MAX_PROFILE_JSON_BYTES:
            raise ProfileValidationError("profile JSON exceeds max size")
        try:
            obj = json.loads(s)
        except Exception as exc:
            raise ProfileValidationError(f"invalid profile JSON: {exc}") from exc
        if "integrity" not in obj and not verify_sha:
            return validate_profile(obj, verify_sha=False)
        if "integrity" not in obj:
            obj["integrity"] = {"sha256": compute_integrity_sha256(obj)}
        return validate_profile(obj, verify_sha=verify_sha)
    if not os.path.isfile(s):
        raise ProfileValidationError(f"profile file not found: {s}")
    if os.path.getsize(s) > MAX_PROFILE_JSON_BYTES:
        raise ProfileValidationError("profile file exceeds max size")
    with open(s, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
    if content.startswith(PROFILE_PREFIX):
        return decode_profile_b64(content, verify_sha=verify_sha)
    return load_profile_any(content, verify_sha=verify_sha)
