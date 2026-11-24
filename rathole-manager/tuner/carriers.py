"""Isolated ephemeral-port tunnel carrier detection and live benchmarks."""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import time

from .probes import probe_trial, probe_unloaded_rtt
from .scoring import raw_throughput

CARRIER_ORDER = ("raw-tcp", "raw-udp", "rathole", "kcp", "backhaul", "frp", "gre", "paqet")


def _find_exec(name: str, bin_dir: str = "/usr/local/bin") -> str | None:
    cand = os.path.join(bin_dir, name)
    if os.path.isfile(cand) and os.access(cand, os.X_OK):
        return cand
    found = shutil.which(name)
    if found and os.path.isfile(found) and os.access(found, os.X_OK):
        return found
    return None


def _free_tcp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def detect_installed_carriers(bin_dir: str = "/usr/local/bin") -> dict:
    """Report which real tunnel binaries exist and are executable locally."""
    bins = ("rathole", "kcptun-server", "kcptun-client", "backhaul-server", "backhaul-client", "frps", "frpc", "paqet")
    return {name: bool(_find_exec(name, bin_dir=bin_dir)) for name in bins}


def _live_probe_kcp(
    ctrl_client,
    host: str,
    data_tcp_port: int,
    data_udp_port: int,
    kcp_cli_bin: str,
    mtu: int,
    profile_name: str,
    listen_port: int,
    duration_s: float,
) -> dict | None:
    profiles = {
        "balanced": ("fast2", 10, 3),
        "lossy": ("fast2", 10, 5),
        "aggressive": ("fast3", 10, 4),
    }
    mode_k, ds, ps = profiles.get(profile_name, ("fast2", 10, 3))
    key = secrets.token_hex(12)
    started = ctrl_client.call("carrier_start", {
        "kind": "kcp",
        "listen_port": listen_port,
        "target_port": data_tcp_port,
        "mtu": mtu,
        "mode": mode_k,
        "datashard": ds,
        "parityshard": ps,
        "key": key,
    })
    if not started.get("ok"):
        return None
    local_port = _free_tcp_port()
    proc = None
    try:
        proc = subprocess.Popen(
            [
                kcp_cli_bin,
                "-r", f"{host}:{listen_port}",
                "-l", f"127.0.0.1:{local_port}",
                "-key", key, "-crypt", "aes-128",
                "-mode", mode_k, "-mtu", str(mtu),
                "-sndwnd", "2048", "-rcvwnd", "2048",
                "-datashard", str(ds), "-parityshard", str(ps),
                "-nocomp",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(0.4)
        if proc.poll() is not None:
            return None
        tr = probe_trial(
            "127.0.0.1",
            local_port,
            data_udp_port,
            duration_s=duration_s,
            streams=2,
            include_bidir=False,
            include_burst=True,
        )
        return {
            "throughput_mbps": round(raw_throughput(tr), 2),
            "loaded_rtt_p95_ms": tr["loaded_rtt_p95_ms"],
            "jitter_ms": tr["jitter_ms"],
            "retrans_pct": tr["retrans_pct"],
        }
    except Exception:
        return None
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        try:
            ctrl_client.call("carrier_stop", {})
        except Exception:
            pass


def benchmark_carriers(
    ctrl_client,
    host: str,
    data_tcp_port: int,
    data_udp_port: int,
    pmtu: int,
    udp_loss_pct: float,
    local_caps: dict,
    remote_caps: dict,
    duration_s: float = 2.0,
    isolated_port_base: int = 29920,
    dry_run: bool = False,
) -> dict:
    """Measure raw TCP/UDP and installed tunnel carrier options without disturbing live tunnels."""
    results: dict[str, dict] = {}

    tcp_res = probe_trial(
        host,
        data_tcp_port,
        data_udp_port,
        duration_s=duration_s,
        streams=4,
        include_bidir=False,
        include_burst=True,
    )
    results["raw-tcp"] = {
        "installed": True,
        "status": "tested",
        "throughput_mbps": round(raw_throughput(tcp_res), 2),
        "loaded_rtt_p95_ms": tcp_res["loaded_rtt_p95_ms"],
        "jitter_ms": tcp_res["jitter_ms"],
        "retrans_pct": tcp_res["retrans_pct"],
    }

    udp_res = probe_unloaded_rtt(host, data_tcp_port, data_udp_port, samples=12, timeout=0.8)
    results["raw-udp"] = {
        "installed": True,
        "status": "tested",
        "udp_loss_pct": udp_res["udp_loss_pct"],
        "udp_samples_ok": udp_res["udp_samples_ok"],
        "udp_samples_sent": udp_res["udp_samples_sent"],
        "throttled": udp_res["udp_loss_pct"] > 5.0,
    }

    lcores = (local_caps or {}).get("installed_cores") or {}
    rcores = (remote_caps or {}).get("installed_cores") or {}
    rec_kcp_mtu = max(1280, min(1400, int(pmtu or 1460) - 60))

    # Determine installed status and realistic recommendation metadata for each tunnel lane
    has_kcp = bool(lcores.get("kcptun-server") and rcores.get("kcptun-client"))
    has_bh = bool(lcores.get("backhaul-server") and rcores.get("backhaul-client"))
    has_frp = bool(lcores.get("frps") and rcores.get("frpc"))
    has_rh = bool(lcores.get("rathole") and rcores.get("rathole"))
    has_paqet = bool(lcores.get("paqet") and rcores.get("paqet"))

    loss_val = max(float(udp_loss_pct or 0.0), float(udp_res["udp_loss_pct"]))
    kcp_prof = "lossy" if loss_val >= 5.0 else ("aggressive" if loss_val >= 1.5 else "balanced")
    bh_prof = "lossy" if loss_val >= 5.0 else "balanced"

    results["rathole"] = {
        "installed": has_rh,
        "status": "ready" if has_rh else "not_installed",
        "recommended_variant": "noise" if udp_res["udp_loss_pct"] <= 3.0 else "ws",
    }
    kcp_entry = {
        "installed": has_kcp,
        "status": "ready" if has_kcp else "not_installed",
        "recommended_profile": kcp_prof,
        "recommended_mtu": rec_kcp_mtu,
    }
    local_kcp_cli = _find_exec("kcptun-client")
    if has_kcp and not dry_run and local_kcp_cli and ctrl_client is not None:
        live_kcp = _live_probe_kcp(
            ctrl_client, host, data_tcp_port, data_udp_port,
            local_kcp_cli, rec_kcp_mtu, kcp_prof, isolated_port_base, duration_s,
        )
        if live_kcp:
            kcp_entry["status"] = "tested"
            kcp_entry.update(live_kcp)
    results["kcp"] = kcp_entry
    results["backhaul"] = {
        "installed": has_bh,
        "status": "ready" if has_bh else "not_installed",
        "recommended_transport": "wsmux",
        "recommended_profile": bh_prof,
    }
    results["frp"] = {
        "installed": has_frp,
        "status": "ready" if has_frp else "not_installed",
        "recommended_transport": "tcp" if results["raw-udp"]["throttled"] else "quic",
    }
    results["paqet"] = {
        "installed": has_paqet,
        "status": "ready" if has_paqet else "not_installed",
        "recommended_mode": "fast2" if loss_val >= 2.0 else "fast",
    }
    return results


def recommend_best_carrier(carrier_matrix: dict) -> dict:
    """Choose the best tunnel carrier profile from measured L4/L7 telemetry."""
    udp_info = (carrier_matrix or {}).get("raw-udp") or {}
    throttled = bool(udp_info.get("throttled"))
    loss = float(udp_info.get("udp_loss_pct", 0.0) or 0.0)
    kcp = (carrier_matrix or {}).get("kcp") or {}
    bh = (carrier_matrix or {}).get("backhaul") or {}
    frp = (carrier_matrix or {}).get("frp") or {}

    if not throttled and loss >= 1.5 and kcp.get("installed"):
        return {
            "lane": "kcp",
            "profile": kcp.get("recommended_profile", "balanced"),
            "mtu": kcp.get("recommended_mtu", 1360),
        }
    if bh.get("installed"):
        return {
            "lane": "backhaul",
            "transport": bh.get("recommended_transport", "wsmux"),
            "profile": bh.get("recommended_profile", "balanced"),
        }
    if frp.get("installed"):
        return {
            "lane": "frp",
            "transport": "tcp" if throttled else frp.get("recommended_transport", "quic"),
        }
    return {"lane": "ws", "profile": "balanced"}
