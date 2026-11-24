"""Non-kernel configuration and system hygiene inspector (Nginx, Xray, limits, CPU)."""

from __future__ import annotations

import json
import re

from .sysstate import SysDriver


def _inspect_cpu_governor(driver: SysDriver, findings: list, sys_recs: list) -> None:
    gov = (driver.read_text("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") or "").strip()
    if gov and gov != "performance":
        findings.append({
            "code": "cpu_governor_powersave",
            "severity": "warning",
            "detail": f"CPU governor is '{gov}' instead of 'performance' (adds tail jitter on encrypted tunnels).",
        })
        sys_recs.append({
            "target": "cpu_governor",
            "current": gov,
            "recommended": "performance",
            "reason": "Eliminates CPU frequency scaling latency spikes during burst traffic.",
        })


def _inspect_limits_and_ports(driver: SysDriver, findings: list, sys_recs: list) -> None:
    fmax = driver.read_sysctl("fs.file-max")
    if fmax and fmax.isdigit() and int(fmax) < 524288:
        findings.append({
            "code": "low_file_max",
            "severity": "warning",
            "detail": f"fs.file-max={fmax} is low; raise to 2097152.",
        })
        sys_recs.append({"target": "fs.file-max", "current": int(fmax), "recommended": 2097152})

    pr = driver.read_sysctl("net.ipv4.ip_local_port_range") or ""
    parts = pr.split()
    if parts and parts[0].isdigit() and int(parts[0]) < 10000:
        findings.append({
            "code": "unsafe_ephemeral_port_range",
            "severity": "warning",
            "detail": f"ip_local_port_range starts at {parts[0]}; risk of colliding with tunnel backend ports.",
        })
        sys_recs.append({
            "target": "net.ipv4.ip_local_port_range",
            "current": pr,
            "recommended": "32768 60999",
        })


def _inspect_nginx(driver: SysDriver, path: str, findings: list, nginx_recs: list) -> None:
    txt = driver.read_text(path)
    if txt is None:
        return
    if "proxy_pass" in txt and "tcp_nodelay on" not in txt:
        findings.append({
            "code": "nginx_no_tcp_nodelay",
            "severity": "warning",
            "detail": f"{path}: 'tcp_nodelay on;' not found; enabling reduces WebSocket/stream frame latency.",
        })
        nginx_recs.append({"target": "tcp_nodelay", "recommended": "tcp_nodelay on;"})
    if "proxy_pass" in txt and "access_log off" not in txt:
        findings.append({
            "code": "nginx_access_log_enabled",
            "severity": "info",
            "detail": f"{path}: 'access_log off;' not set on data path; disabling saves disk I/O at high throughput.",
        })
        nginx_recs.append({"target": "access_log", "recommended": "access_log off;"})
    if "proxy_pass" in txt and "proxy_buffering off" not in txt:
        findings.append({
            "code": "nginx_proxy_buffering",
            "severity": "warning",
            "detail": f"{path}: 'proxy_buffering off;' missing on proxied tunnel location.",
        })
        nginx_recs.append({"target": "proxy_buffering", "recommended": "proxy_buffering off;"})


def _inspect_xray(driver: SysDriver, path: str, findings: list, xray_recs: list) -> None:
    raw = driver.read_text(path)
    if raw is None:
        return
    try:
        cfg = json.loads(raw)
    except Exception:
        return

    log_lvl = ((cfg.get("log") or {}).get("loglevel") or "").lower()
    if log_lvl in ("debug", "info"):
        findings.append({
            "code": "xray_loglevel_debug",
            "severity": "warning",
            "detail": f"{path}: loglevel='{log_lvl}' adds unnecessary CPU/disk overhead; use 'warning'.",
        })
        xray_recs.append({"target": "log.loglevel", "current": log_lvl, "recommended": "warning"})

    for out in cfg.get("outbounds") or []:
        mux = (out or {}).get("mux") or {}
        if mux.get("enabled") is True:
            findings.append({
                "code": "xray_mux_enabled",
                "severity": "warning",
                "detail": f"{path}: Xray outbound mux.enabled=true causes Head-of-Line blocking on streaming/reels.",
            })
            xray_recs.append({"target": "outbound.mux.enabled", "current": True, "recommended": False})
            break

    lvl0 = ((cfg.get("policy") or {}).get("levels") or {}).get("0") or {}
    buf = lvl0.get("bufferSize")
    if isinstance(buf, int) and buf < 256:
        findings.append({
            "code": "xray_small_buffer_size",
            "severity": "info",
            "detail": f"{path}: policy.levels.0.bufferSize={buf}; 512 KiB improves high-BDP video throughput.",
        })
        xray_recs.append({"target": "policy.levels.0.bufferSize", "current": buf, "recommended": 512})

    for inb in cfg.get("inbounds") or []:
        sockopt = ((inb or {}).get("streamSettings") or {}).get("sockopt") or {}
        if sockopt.get("tcpNoDelay") is False:
            findings.append({
                "code": "xray_tcp_nodelay_off",
                "severity": "warning",
                "detail": f"{path}: sockopt.tcpNoDelay is explicitly disabled.",
            })
            xray_recs.append({"target": "streamSettings.sockopt.tcpNoDelay", "current": False, "recommended": True})
            break


def _inspect_systemd_limits(driver: SysDriver, unit_paths: list[str], findings: list, sys_recs: list) -> None:
    for p in unit_paths:
        txt = driver.read_text(p)
        if not txt:
            continue
        m = re.search(r"LimitNOFILE\s*=\s*(\d+)", txt)
        if m and int(m.group(1)) < 65536:
            findings.append({
                "code": "systemd_low_nofile",
                "severity": "warning",
                "detail": f"{p}: LimitNOFILE={m.group(1)} < 65536.",
            })
            sys_recs.append({"target": f"{p}:LimitNOFILE", "current": int(m.group(1)), "recommended": 1048576})


def run_non_kernel_audit(driver: SysDriver, role: str = "iran", paths: dict | None = None) -> dict:
    """Inspect non-kernel configuration without making changes."""
    p = paths or {}
    findings: list[dict] = []
    nginx_recs: list[dict] = []
    xray_recs: list[dict] = []
    sys_recs: list[dict] = []

    _inspect_cpu_governor(driver, findings, sys_recs)
    _inspect_limits_and_ports(driver, findings, sys_recs)
    _inspect_nginx(driver, p.get("nginx_conf", "/etc/nginx/conf.d/rathole.conf"), findings, nginx_recs)
    _inspect_xray(driver, p.get("xray_conf", "/etc/xray/config.json"), findings, xray_recs)
    _inspect_systemd_limits(
        driver,
        p.get("unit_paths", [
            "/etc/systemd/system/rathole-server.service",
            "/etc/systemd/system/rathole-client.service",
            "/etc/systemd/system/backhaul-server.service",
            "/etc/systemd/system/backhaul-client.service",
        ]),
        findings,
        sys_recs,
    )
    return {
        "role": role,
        "findings": findings,
        "nginx_recommendations": nginx_recs,
        "xray_recommendations": xray_recs,
        "system_recommendations": sys_recs,
    }
