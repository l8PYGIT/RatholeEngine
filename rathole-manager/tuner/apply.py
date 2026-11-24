"""Persistent profile apply, boot restoration, status, and rollback for rathole-tuner."""

from __future__ import annotations

import datetime
import json
import os

from .profile import clamp_config_for_ram, validate_profile
from .sysstate import SysDriver, apply_candidate, capture_snapshot, discover_capabilities, restore_snapshot

DEFAULT_PATHS = {
    "sysctl_tune_file": "/etc/sysctl.d/99-rathole-tune.conf",
    "reserved_ports_file": "/etc/sysctl.d/99-rathole-reserved-ports.conf",
    "applied_profile_file": "/etc/rathole-tuner/applied-profile.json",
    "systemd_unit_file": "/etc/systemd/system/rathole-net-tune.service",
    "snapshot_dir": "/var/lib/rathole-tuner/snapshots",
}


def _resolve_paths(overrides: dict | None) -> dict:
    out = dict(DEFAULT_PATHS)
    if overrides:
        out.update(overrides)
    return out


def _parse_sysctl_conf(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = " ".join(v.strip().split())
        if k:
            out[k] = v
    return out


def _render_sysctl_conf(sysctls: dict) -> str:
    lines = ["# Managed by rathole-tuner (do not hand-edit; use rollback to revert)"]
    for k in sorted(sysctls.keys()):
        lines.append(f"{k}={sysctls[k]}")
    return "\n".join(lines) + "\n"


def _merge_sysctl_preserving_base(prev_text: str, new_sysctls: dict) -> dict:
    """Merge non-conflicting base sysctls (e.g. fs.file-max, nf_conntrack_max) with new profile."""
    merged = _parse_sysctl_conf(prev_text)
    new_map = dict(new_sysctls or {})
    # Never leave stale 25 MiB defaults if the profile sets smaller maxes or overrides maxes
    if "net.core.rmem_max" in new_map and "net.core.rmem_default" not in new_map:
        merged.pop("net.core.rmem_default", None)
    if "net.core.wmem_max" in new_map and "net.core.wmem_default" not in new_map:
        merged.pop("net.core.wmem_default", None)
    merged.update(new_map)
    return merged


def _render_systemd_unit(tuner_bin: str = "/usr/local/bin/rathole-tuner") -> str:
    return (
        "[Unit]\n"
        "Description=rathole-tuner persistent network optimization\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={tuner_bin} apply-boot\n"
        "RemainAfterExit=yes\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def apply_persistent(driver: SysDriver, profile: dict, side: str = "iran", paths: dict | None = None) -> dict:
    """Validate, snapshot, persistently apply sysctl + boot service, and activate live."""
    if side not in ("iran", "node"):
        raise ValueError(f"invalid side: {side!r}")
    p = _resolve_paths(paths)
    caps = discover_capabilities(driver)
    valid = validate_profile(profile, host_ram_mb=caps["ram_mb"], verify_sha=False)
    side_cfg = clamp_config_for_ram(valid[f"{side}_config"], caps["ram_mb"])

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    snap_path = os.path.join(p["snapshot_dir"], f"pre-apply-{ts}.json")
    snap = capture_snapshot(driver, iface=caps["iface"])
    snap["had_sysctl_tune_file"] = driver.file_exists(p["sysctl_tune_file"])
    snap["prev_sysctl_tune_content"] = driver.read_text(p["sysctl_tune_file"]) or ""
    driver.write_text(snap_path, json.dumps(snap, indent=2) + "\n", mode=0o600)

    sysctls = side_cfg.get("sysctl") or {}
    merged_sysctls = _merge_sysctl_preserving_base(snap["prev_sysctl_tune_content"], sysctls)
    driver.write_text(p["sysctl_tune_file"], _render_sysctl_conf(merged_sysctls), mode=0o644)
    driver.run(["sysctl", "--system"])

    applied_meta = {
        "profile_id": (valid.get("meta") or {}).get("id", ""),
        "profile_name": (valid.get("meta") or {}).get("name", "custom"),
        "side": side,
        "iface": caps["iface"],
        "applied_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "snapshot_path": snap_path,
        "config": side_cfg,
    }
    driver.write_text(p["applied_profile_file"], json.dumps(applied_meta, indent=2) + "\n", mode=0o600)

    res = apply_candidate(
        driver,
        side_cfg,
        iface=caps["iface"],
        session_id="persistent",
        ram_mb=caps["ram_mb"],
        ipv6_active=caps["ipv6_active"],
    )

    driver.write_text(p["systemd_unit_file"], _render_systemd_unit(), mode=0o644)
    driver.run(["systemctl", "daemon-reload"])
    driver.run(["systemctl", "enable", "rathole-net-tune.service"])
    return {
        "ok": True,
        "side": side,
        "iface": caps["iface"],
        "snapshot_path": snap_path,
        "applied": res["applied"],
        "unsupported": res["unsupported"],
    }


def apply_boot(driver: SysDriver, paths: dict | None = None) -> dict:
    """Re-apply non-sysctl network parameters stored in applied-profile.json at boot."""
    p = _resolve_paths(paths)
    raw = driver.read_text(p["applied_profile_file"])
    if not raw:
        return {"ok": False, "detail": "no applied-profile.json present"}
    doc = json.loads(raw)
    cfg = doc.get("config") or {}
    caps = discover_capabilities(driver)
    iface = doc.get("iface") or caps["iface"]
    res = apply_candidate(
        driver,
        cfg,
        iface=iface,
        session_id="persistent",
        ram_mb=caps["ram_mb"],
        ipv6_active=caps["ipv6_active"],
    )
    return {"ok": True, "iface": iface, "applied": res["applied"], "unsupported": res["unsupported"]}


def rollback_persistent(driver: SysDriver, paths: dict | None = None) -> dict:
    """Revert persistent tuning back to pre-apply snapshot without touching reserved ports."""
    p = _resolve_paths(paths)
    raw = driver.read_text(p["applied_profile_file"])
    if not raw:
        return {"ok": False, "detail": "nothing applied to rollback"}
    doc = json.loads(raw)
    snap_path = doc.get("snapshot_path") or ""
    snap_raw = driver.read_text(snap_path) if snap_path else None
    if snap_raw:
        snap = json.loads(snap_raw)
        restore_snapshot(driver, snap, session_id="persistent")
        if snap.get("had_sysctl_tune_file") and snap.get("prev_sysctl_tune_content"):
            driver.write_text(p["sysctl_tune_file"], snap["prev_sysctl_tune_content"], mode=0o644)
        else:
            driver.remove_file(p["sysctl_tune_file"])
    else:
        driver.remove_file(p["sysctl_tune_file"])

    driver.run(["sysctl", "--system"])
    driver.run(["systemctl", "disable", "--now", "rathole-net-tune.service"])
    driver.remove_file(p["applied_profile_file"])
    return {"ok": True, "restored_from": snap_path}


def tuner_status(driver: SysDriver, paths: dict | None = None) -> dict:
    """Return current host tuning capabilities, live kernel params, and persistent apply status."""
    p = _resolve_paths(paths)
    caps = discover_capabilities(driver)
    snap = capture_snapshot(driver, iface=caps["iface"])
    raw = driver.read_text(p["applied_profile_file"])
    applied_doc = json.loads(raw) if raw else None
    return {
        "applied": bool(applied_doc),
        "profile_id": (applied_doc or {}).get("profile_id"),
        "profile_name": (applied_doc or {}).get("profile_name"),
        "side": (applied_doc or {}).get("side"),
        "applied_at": (applied_doc or {}).get("applied_at"),
        "iface": (applied_doc or {}).get("iface") or caps["iface"],
        "applied_config": (applied_doc or {}).get("config"),
        "current_mtu": snap.get("mtu"),
        "current_txqueuelen": snap.get("txqueuelen"),
        "current_qdisc_live": (snap.get("qdisc") or {}).get("kind"),
        "current_route": snap.get("route") or {},
        "capabilities": caps,
        "current_sysctl": {
            "cc": driver.read_sysctl("net.ipv4.tcp_congestion_control"),
            "qdisc": driver.read_sysctl("net.core.default_qdisc"),
            "rmem_max": driver.read_sysctl("net.core.rmem_max"),
            "wmem_max": driver.read_sysctl("net.core.wmem_max"),
            "tcp_rmem": driver.read_sysctl("net.ipv4.tcp_rmem"),
            "tcp_wmem": driver.read_sysctl("net.ipv4.tcp_wmem"),
            "notsent_lowat": driver.read_sysctl("net.ipv4.tcp_notsent_lowat"),
        },
    }
