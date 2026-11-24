"""5-dimensional composite scorer and Hard-Fail Gate for rathole-tuner."""

from __future__ import annotations

import copy
import math

GOAL_WEIGHTS = {
    "balanced": {"T": 0.30, "L": 0.25, "J": 0.15, "R": 0.15, "S": 0.15},
    "low-latency": {"T": 0.15, "L": 0.35, "J": 0.25, "R": 0.15, "S": 0.10},
    "max-throughput": {"T": 0.45, "L": 0.15, "J": 0.10, "R": 0.15, "S": 0.15},
    "anti-loss": {"T": 0.20, "L": 0.15, "J": 0.15, "R": 0.30, "S": 0.20},
}


def raw_throughput(metrics: dict) -> float:
    """Compute weighted raw capacity from 1-stream, N-stream, and bidir throughput."""
    t1 = float(metrics.get("throughput_1_mbps", metrics.get("throughput_mbps", 0.0)) or 0.0)
    tn = float(metrics.get("throughput_n_mbps", t1) or 0.0)
    tb = float(metrics.get("throughput_bidir_mbps", t1) or 0.0)
    return 0.40 * t1 + 0.40 * tn + 0.20 * tb


def check_hard_fail(metrics: dict, baseline: dict | None = None) -> tuple[bool, str | None]:
    """Return (disqualified, reason) if a candidate breached reliability gates."""
    if metrics.get("aborted") or metrics.get("disconnected"):
        return True, "connection_aborted"
    udp_loss = float(metrics.get("udp_loss_pct", 0.0) or 0.0)
    base_udp = float((baseline or {}).get("udp_loss_pct", 0.0) or 0.0)
    if baseline is not None and udp_loss > 15.0 and udp_loss > base_udp + 10.0:
        return True, f"udp_loss_regressed ({udp_loss:.1f}% vs {base_udp:.1f}%)"
    retrans = float(metrics.get("retrans_pct", 0.0) or 0.0)
    base_retrans = float((baseline or {}).get("retrans_pct", 0.0) or 0.0)
    if retrans > 10.0 and retrans > 2.0 * base_retrans:
        return True, f"retrans_gt_10pct_and_2x_baseline ({retrans:.1f}% vs {base_retrans:.1f}%)"
    if raw_throughput(metrics) <= 0.0 and float(metrics.get("throughput_mbps", 0.0) or 0.0) <= 0.0:
        return True, "zero_throughput"
    return False, None


def _subscores(metrics: dict, max_raw_t: float, ignore_udp_loss: bool = False) -> dict:
    raw_t = raw_throughput(metrics)
    t_score = max(0.0, min(100.0, (100.0 * raw_t / max_raw_t) if max_raw_t > 0.0 else 0.0))

    unloaded = float(metrics.get("unloaded_rtt_p50_ms", metrics.get("rtt_p50_ms", 20.0)) or 20.0)
    loaded = float(metrics.get("loaded_rtt_p95_ms", unloaded) or unloaded)
    bloat = max(0.0, loaded - unloaded)
    ratio = bloat / max(10.0, unloaded)
    l_score = max(0.0, min(100.0, 100.0 / (1.0 + 0.65 * ratio + max(0.0, (loaded - 80.0) / 350.0))))

    p50 = float(metrics.get("rtt_p50_ms", unloaded) or unloaded)
    p99 = float(metrics.get("rtt_p99_ms", loaded) or loaded)
    tail = max(0.0, p99 - p50)
    jitter = max(0.0, float(metrics.get("jitter_ms", 0.0) or 0.0))
    j_score = max(0.0, min(100.0, 100.0 * math.exp(-(jitter / 35.0 + tail / 120.0))))

    retrans = max(0.0, float(metrics.get("retrans_pct", 0.0) or 0.0))
    udp_loss = 0.0 if ignore_udp_loss else max(0.0, float(metrics.get("udp_loss_pct", 0.0) or 0.0))
    drops = max(0, int(metrics.get("drop_delta", 0) or 0))
    r_score = max(0.0, min(100.0, 100.0 - (retrans * 4.5 + udp_loss * 5.0 + min(25.0, drops * 2.0))))

    cov = max(0.0, min(1.0, float(metrics.get("stability_cov", 0.0) or 0.0)))
    s_score = max(0.0, min(100.0, 100.0 * (1.0 - cov)))

    return {
        "T": round(t_score, 2),
        "L": round(l_score, 2),
        "J": round(j_score, 2),
        "R": round(r_score, 2),
        "S": round(s_score, 2),
    }


def score_trials(trials: list[dict], baseline_id: str = "baseline") -> list[dict]:
    """Evaluate Hard-Fail Gate, 5D subscores, and 4 goal scores across all trials."""
    if not trials:
        return []
    out = [copy.deepcopy(t) for t in trials]
    base = next((t for t in out if t.get("id") == baseline_id), out[0])
    ignore_udp = float(base.get("udp_loss_pct", 0.0) or 0.0) >= 95.0

    alive_raw_t = []
    for t in out:
        disq, reason = check_hard_fail(t, None if t is base else base)
        t["disqualified"] = disq
        t["disqualify_reason"] = reason
        if not disq:
            alive_raw_t.append(raw_throughput(t))

    max_raw_t = max(alive_raw_t) if alive_raw_t else 1.0
    if max_raw_t <= 0.0:
        max_raw_t = 1.0

    for t in out:
        if t["disqualified"]:
            t["subscores"] = {"T": 0.0, "L": 0.0, "J": 0.0, "R": 0.0, "S": 0.0}
            t["scores"] = {g: 0.0 for g in GOAL_WEIGHTS}
            continue
        subs = _subscores(t, max_raw_t, ignore_udp_loss=ignore_udp)
        t["subscores"] = subs
        t["scores"] = {
            goal: round(sum(subs[dim] * w for dim, w in weights.items()), 2)
            for goal, weights in GOAL_WEIGHTS.items()
        }
    return out


def diagnose_findings(
    baseline: dict,
    winner: dict,
    pmtu_info: dict,
    audit_iran: dict | None = None,
    audit_node: dict | None = None,
) -> list[dict]:
    """Generate structured diagnostic insights comparing baseline, PMTU, winner, and audits."""
    findings = []
    fwd_mtu = int((pmtu_info or {}).get("forward_bytes", 1500) or 1500)
    rev_mtu = int((pmtu_info or {}).get("reverse_bytes", 1500) or 1500)
    if (pmtu_info or {}).get("udp_blocked"):
        findings.append({
            "code": "udp_blocked",
            "severity": "warning",
            "detail": f"UDP probes are filtered/blocked on this path; PMTU defaulted safely to {min(fwd_mtu, rev_mtu)} bytes and TCP carriers (ws/backhaul/frp-tcp) are recommended.",
        })
    elif (pmtu_info or {}).get("blackhole_detected"):
        findings.append({
            "code": "pmtu_blackhole",
            "severity": "warning",
            "detail": f"PMTU restriction detected (forward={fwd_mtu}, reverse={rev_mtu}); MSS/MTU clamp prevents stalled flows.",
        })
    elif min(fwd_mtu, rev_mtu) < 1500:
        findings.append({
            "code": "reduced_pmtu",
            "severity": "info",
            "detail": f"Effective path MTU is {min(fwd_mtu, rev_mtu)} bytes; tuning aligns interface/route MSS accordingly.",
        })

    unloaded = float((baseline or {}).get("unloaded_rtt_p50_ms", 0.0) or 0.0)
    base_loaded = float((baseline or {}).get("loaded_rtt_p95_ms", 0.0) or 0.0)
    win_loaded = float((winner or {}).get("loaded_rtt_p95_ms", 0.0) or 0.0)
    if base_loaded - unloaded >= 45.0:
        findings.append({
            "code": "bufferbloat_high",
            "severity": "warning",
            "detail": f"Baseline loaded RTT spiked +{base_loaded - unloaded:.1f}ms under load (winner loaded p95={win_loaded:.1f}ms).",
        })

    udp_loss = float((baseline or {}).get("udp_loss_pct", 0.0) or 0.0)
    if udp_loss >= 3.0 and not (pmtu_info or {}).get("udp_blocked"):
        findings.append({
            "code": "udp_loss_elevated",
            "severity": "warning",
            "detail": f"Path shows {udp_loss:.1f}% UDP packet loss; FEC-enabled carriers (kcp/paqet) or tcp carriers are preferred.",
        })

    base_t = raw_throughput(baseline or {})
    win_t = raw_throughput(winner or {})
    if (winner or {}).get("id") == "baseline":
        findings.append({
            "code": "baseline_already_optimal",
            "severity": "info",
            "detail": "Current baseline outperformed or matched all tested kernel profiles without throughput regression; no aggressive kernel change needed.",
        })
    elif base_t > 0 and win_t > base_t * 1.15:
        gain = ((win_t - base_t) / base_t) * 100.0
        findings.append({
            "code": "throughput_gain",
            "severity": "info",
            "detail": f"Optimal profile improved weighted throughput by +{gain:.1f}% ({base_t:.1f} -> {win_t:.1f} Mbps).",
        })

    for role_label, audit_res in (("iran", audit_iran), ("node", audit_node)):
        for item in (audit_res or {}).get("findings", []):
            if item.get("severity") in ("error", "warning"):
                findings.append({
                    "code": f"{role_label}_{item.get('code', 'audit')}",
                    "severity": item["severity"],
                    "detail": item.get("detail", ""),
                })
    return findings
