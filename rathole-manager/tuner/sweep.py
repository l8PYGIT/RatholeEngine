"""6-stage coordinate-descent search & finalist soak orchestration for rathole-tuner."""

from __future__ import annotations

import copy

from .carriers import benchmark_carriers, recommend_best_carrier
from .probes import probe_pmtu, probe_trial, probe_unloaded_rtt
from .profile import (
    ALLOWED_OFFLOADS,
    ALLOWED_QDISCS,
    _ALLOWED_SYSCTL_ENUMS,
    _ALLOWED_SYSCTL_INTS,
    _ALLOWED_SYSCTL_TRIPLETS,
    clamp_config_for_ram,
    compute_ram_buffer_cap,
)
from .scoring import check_hard_fail, diagnose_findings, raw_throughput, score_trials
from .sysstate import apply_candidate, capture_snapshot, read_net_counters, restore_snapshot


def compute_bdp_buffers(bw_mbps: float, rtt_ms: float, ram_mb: int) -> list[dict]:
    """Compute generous tunnel buffer sysctl tiers strictly clamped to 10% host RAM."""
    bw = max(10.0, float(bw_mbps or 100.0))
    rtt = max(5.0, float(rtt_ms or 40.0))
    bdp = int((bw * 1_000_000.0 / 8.0) * (rtt / 1000.0))
    ram_cap = compute_ram_buffer_cap(ram_mb)
    # Linux splits tcp_rmem max roughly 50/50 with skb overhead, and momentary
    # baseline throughput must never shrink buffers below proven tunnel floors.
    min_tiers = {1: 8 * 1024 * 1024, 2: 16 * 1024 * 1024, 4: 32 * 1024 * 1024}
    out = []
    for mult in (1, 2, 4):
        floor_bytes = min(ram_cap, min_tiers[mult])
        target = min(ram_cap, max(262144, floor_bytes, bdp * mult * 2))
        r_mid = min(target, 262144)
        w_mid = min(target, 131072)
        def_buf = min(target, 1048576)
        out.append({
            "label": f"bdp_{mult}x",
            "net.core.rmem_max": target,
            "net.core.wmem_max": target,
            "net.core.rmem_default": def_buf,
            "net.core.wmem_default": def_buf,
            "net.ipv4.tcp_rmem": f"4096 {r_mid} {target}",
            "net.ipv4.tcp_wmem": f"4096 {w_mid} {target}",
            "net.ipv4.udp_rmem_min": 16384 if mult >= 2 else 8192,
            "net.ipv4.udp_wmem_min": 16384 if mult >= 2 else 8192,
        })
    return out


def _dedup_ints(vals: list[int], lo: int, hi: int) -> list[int]:
    seen = set()
    res = []
    for v in vals:
        iv = max(lo, min(hi, int(v)))
        if iv not in seen:
            seen.add(iv)
            res.append(iv)
    return res


def build_stage_candidates(
    stage: int,
    mode: str,
    caps_local: dict,
    caps_remote: dict,
    best_cfg: dict,
    baseline_metrics: dict,
    pmtu_info: dict,
    fast_test: bool = False,
) -> list[dict]:
    """Build candidates for Stage 1 (MTU/MSS), Stage 2 (CC/qdisc/lowat), Stage 3 (BDP/TCP knobs)."""
    pmtu = min(
        int((pmtu_info or {}).get("forward_bytes", 1500) or 1500),
        int((pmtu_info or {}).get("reverse_bytes", 1500) or 1500),
    )
    udp_blocked = bool((pmtu_info or {}).get("udp_blocked"))
    blackhole = bool((pmtu_info or {}).get("blackhole_detected"))
    v6_floor = 1280 if ((caps_local or {}).get("ipv6_active") or (caps_remote or {}).get("ipv6_active")) else 576
    base = copy.deepcopy(best_cfg or {"sysctl": {}, "route": {}, "qdisc": {}, "offloads": {}})
    cands: list[dict] = []

    if stage == 1:
        if udp_blocked or (not blackhole and pmtu >= 1460):
            raw_mtus = [1500, 1460, 1420] if fast_test else [1500, 1460, 1420, 1380]
        else:
            raw_mtus = [pmtu, pmtu - 40, 1380, 1280] if fast_test else [pmtu, pmtu - 20, pmtu - 40, 1420, 1380, 1280]
        mtus = _dedup_ints(raw_mtus, v6_floor, 1500)
        if mode == "safe":
            for m in mtus:
                c = copy.deepcopy(base)
                c["name"] = f"safe_mss_{m - 40}"
                c["socket_mss"] = max(536, m - 40)
                cands.append(c)
        else:
            for i, m in enumerate(mtus):
                c = copy.deepcopy(base)
                c["name"] = f"mtu_{m}"
                c["mtu"] = m
                c["txqueuelen"] = 2000 if m >= 1420 else 1000
                c.setdefault("sysctl", {})["net.ipv4.tcp_mtu_probing"] = 1 if i == 0 else 2
                c["sysctl"]["net.ipv4.tcp_base_mss"] = 1024 if m >= 1360 else 512
                cands.append(c)
        return cands

    if stage == 2:
        if mode == "safe":
            return []
        l_cc = set((caps_local or {}).get("available_cc") or ["cubic"])
        r_cc = set((caps_remote or {}).get("available_cc") or ["cubic"])
        common_cc = [c for c in ("bbr", "bbr2", "bbr3", "cubic", "hybla", "westwood", "reno") if c in (l_cc & r_cc)]
        if not common_cc:
            common_cc = [next(iter(l_cc & r_cc or {"cubic"}))]

        l_qd = set((caps_local or {}).get("available_qdisc") or ["fq_codel"])
        r_qd = set((caps_remote or {}).get("available_qdisc") or ["fq_codel"])
        primary_qd = [q for q in ("fq", "fq_codel") if q in (l_qd & r_qd)]
        if not primary_qd:
            primary_qd = [q for q in ("cake",) if q in (l_qd & r_qd)] or ["fq_codel"]
        # Avoid tiny lowat (16k/32k) that chokes event-driven epoll proxies (nginx/rathole/xray).
        lowats = [262144] if fast_test else [4294967295, 262144, 131072]

        combos = []
        for lw in lowats:
            for cc in common_cc[: (2 if fast_test else 4)]:
                for qd in primary_qd[:2]:
                    combos.append((cc, qd, lw))
        for cc, qd, lw in combos[: (3 if fast_test else 12)]:
            c = copy.deepcopy(base)
            c["name"] = f"{cc}_{qd}_lw{lw}"
            c["qdisc"] = {"kind": qd, "params": {}}
            c.setdefault("sysctl", {}).update({
                "net.core.default_qdisc": qd,
                "net.ipv4.tcp_congestion_control": cc,
                "net.ipv4.tcp_notsent_lowat": lw,
            })
            cands.append(c)
        return cands

    if stage == 3:
        if mode == "safe":
            return []
        min_ram = min(int((caps_local or {}).get("ram_mb", 1024)), int((caps_remote or {}).get("ram_mb", 1024)))
        bw = raw_throughput(baseline_metrics or {"throughput_mbps": 150.0})
        rtt = float((baseline_metrics or {}).get("unloaded_rtt_p50_ms", 40.0) or 40.0)
        bdps = compute_bdp_buffers(bw, rtt, min_ram)
        cwnds = [20] if fast_test else [10, 20]
        for b in bdps[: (2 if fast_test else 3)]:
            label = b.pop("label")
            for cw in cwnds[: (1 if fast_test else 2)]:
                c = copy.deepcopy(base)
                c["name"] = f"{label}_cwnd{cw}"
                eff_mtu = int(c.get("mtu", 1500) or 1500)
                rt_cfg = {"initcwnd": cw, "initrwnd": cw}
                if eff_mtu < 1460:
                    rt_cfg["advmss"] = max(536, eff_mtu - 40)
                c["route"] = rt_cfg
                c.setdefault("sysctl", {}).update(b)
                c["sysctl"].update({
                    "net.ipv4.tcp_slow_start_after_idle": 0,
                    "net.ipv4.tcp_ecn": 0,
                    "net.ipv4.tcp_timestamps": 1,
                    "net.ipv4.tcp_fastopen": 3,
                    "net.ipv4.tcp_sack": 1,
                    "net.ipv4.tcp_dsack": 1,
                    "net.ipv4.tcp_autocorking": 1,
                    "net.ipv4.tcp_frto": 2,
                    "net.core.netdev_max_backlog": 16384,
                    "net.core.somaxconn": 65535,
                    "net.ipv4.tcp_max_syn_backlog": 65535,
                })
                cands.append(c)
        return cands

    return cands


_SNAP_SYSCTL_KEYS = (
    "net.core.default_qdisc",
    "net.ipv4.tcp_congestion_control",
    "net.ipv4.tcp_notsent_lowat",
    "net.ipv4.tcp_mtu_probing",
    "net.ipv4.tcp_base_mss",
    "net.ipv4.tcp_slow_start_after_idle",
    "net.ipv4.tcp_ecn",
    "net.core.rmem_max",
    "net.core.wmem_max",
    "net.ipv4.tcp_rmem",
    "net.ipv4.tcp_wmem",
)

_CLAMP_INT_KEYS = frozenset({
    "net.core.rmem_max",
    "net.core.wmem_max",
    "net.core.rmem_default",
    "net.core.wmem_default",
})


def sanitize_snapshot_config(snap: dict) -> dict:
    """Convert raw host snapshot into a strictly schema-valid side config."""
    snap = snap or {}
    snap_sys = snap.get("sysctl") or {}

    try:
        raw_mtu = int(snap.get("mtu", 1500) or 1500)
    except (TypeError, ValueError):
        raw_mtu = 1500
    mtu = max(576, min(1500, raw_mtu))

    try:
        raw_txq = int(snap.get("txqueuelen", 1000) or 1000)
    except (TypeError, ValueError):
        raw_txq = 1000
    txq = max(100, min(20000, raw_txq))

    raw_qd = str((snap.get("qdisc") or {}).get("kind", "") or "").strip()
    sys_qd = str(snap_sys.get("net.core.default_qdisc", "") or "").strip()
    if raw_qd in ALLOWED_QDISCS:
        qd_kind = raw_qd
    elif sys_qd in ALLOWED_QDISCS:
        qd_kind = sys_qd
    else:
        qd_kind = "fq_codel"

    clean_rt: dict[str, int] = {}
    for rk in ("initcwnd", "initrwnd"):
        rv = (snap.get("route") or {}).get(rk)
        if rv is not None and not isinstance(rv, bool):
            try:
                irv = int(rv)
                if 4 <= irv <= 128:
                    clean_rt[rk] = irv
            except (TypeError, ValueError):
                pass
    adv = (snap.get("route") or {}).get("advmss")
    if adv is not None and not isinstance(adv, bool):
        try:
            iadv = int(adv)
            if iadv == 0:
                clean_rt["advmss"] = 0
            elif iadv > 0:
                clean_rt["advmss"] = max(536, min(1460, iadv))
        except (TypeError, ValueError):
            pass

    clean_offs = {
        k: v
        for k, v in (snap.get("offloads") or {}).items()
        if k in ALLOWED_OFFLOADS and type(v) is bool
    }

    clean_sys: dict = {}
    for k in _SNAP_SYSCTL_KEYS:
        if k not in snap_sys:
            continue
        v = snap_sys[k]
        if k in _ALLOWED_SYSCTL_ENUMS:
            sv = str(v).strip()
            if sv in _ALLOWED_SYSCTL_ENUMS[k]:
                clean_sys[k] = sv
        elif k in _ALLOWED_SYSCTL_INTS:
            if isinstance(v, bool):
                continue
            try:
                iv = int(v)
            except (TypeError, ValueError):
                continue
            lo, hi = _ALLOWED_SYSCTL_INTS[k]
            if k in _CLAMP_INT_KEYS:
                clean_sys[k] = max(lo, min(hi, iv))
            elif lo <= iv <= hi:
                clean_sys[k] = iv
        elif k in _ALLOWED_SYSCTL_TRIPLETS:
            parts = str(v).split()
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                lo, hi = _ALLOWED_SYSCTL_TRIPLETS[k]
                a, b, c = [int(p) for p in parts]
                a = max(lo, min(hi, a))
                b = max(a, min(hi, b))
                c = max(b, min(hi, c))
                clean_sys[k] = f"{a} {b} {c}"

    return {
        "mtu": mtu,
        "mss_clamp": 0,
        "qdisc": {"kind": qd_kind, "params": {}},
        "txqueuelen": txq,
        "route": clean_rt,
        "offloads": clean_offs,
        "sysctl": clean_sys,
    }


def _config_from_snapshot(snap: dict) -> dict:
    return sanitize_snapshot_config(snap)


_MIN_THROUGHPUT_RATIO = {
    "max-throughput": 0.98,
    "balanced": 0.92,
    "anti-loss": 0.90,
    "low-latency": 0.80,
}


def _select_best_candidate(
    scored_trials: list[dict],
    baseline: dict,
    goal: str,
    min_gain: float = 0.0,
) -> dict:
    """Return top candidate only if it beats baseline without throughput regression."""
    base_tp = raw_throughput(baseline)
    min_ratio = _MIN_THROUGHPUT_RATIO.get(goal, 0.92)
    base_score = float((baseline.get("scores") or {}).get(goal, 0.0) or 0.0)
    eligible = []
    for item in scored_trials:
        if item.get("disqualified") or item.get("id") == baseline.get("id"):
            continue
        if base_tp > 0.0 and raw_throughput(item) < base_tp * min_ratio:
            continue
        eligible.append(item)
    if not eligible:
        return baseline
    top = max(eligible, key=lambda x: float((x.get("scores") or {}).get(goal, 0.0) or 0.0))
    top_score = float((top.get("scores") or {}).get(goal, 0.0) or 0.0)
    if top_score > base_score + min_gain:
        return top
    return baseline


def _evaluate_candidate(
    cand_id: str,
    cfg: dict,
    mode: str,
    host: str,
    data_tcp_port: int,
    data_udp_port: int,
    ctrl_client,
    local_driver,
    local_snap: dict,
    caps_local: dict,
    caps_remote: dict,
    session_id: str,
    duration_s: float,
    unloaded_p50: float,
    baseline_trial: dict | None,
    skip_udp: bool = False,
) -> dict:
    local_iface = caps_local["iface"]
    remote_iface = caps_remote["iface"]
    local_ram = caps_local["ram_mb"]
    remote_ram = caps_remote["ram_mb"]

    c_before = read_net_counters(local_driver, local_iface)
    remote_warn = ""
    if mode == "brutal":
        cfg_local = clamp_config_for_ram(cfg, local_ram)
        cfg_remote = clamp_config_for_ram(cfg, remote_ram)
        apply_candidate(
            local_driver, cfg_local, iface=local_iface, peer_ip=host, session_id=session_id,
            ram_mb=local_ram, ipv6_active=caps_local["ipv6_active"],
        )
        rc_resp = ctrl_client.call("apply_cand", {"config": cfg_remote, "iface": remote_iface, "session_id": session_id})
        if isinstance(rc_resp, dict) and rc_resp.get("ok") is False:
            remote_warn = str(rc_resp.get("error") or "remote apply rejected")

    try:
        m = probe_trial(
            host,
            data_tcp_port,
            data_udp_port,
            duration_s=duration_s,
            streams=4,
            mss_override=int(cfg.get("socket_mss") or 0),
            include_bidir=True,
            include_burst=True,
            unloaded_p50_ms=unloaded_p50,
            skip_udp=skip_udp,
        )
    finally:
        if mode == "brutal":
            restore_snapshot(local_driver, local_snap, session_id=session_id)
            ctrl_client.call("revert", {"session_id": session_id})

    c_after = read_net_counters(local_driver, local_iface)
    m["drop_delta"] = max(0, (c_after["tx_dropped"] - c_before["tx_dropped"]) + (c_after["rx_dropped"] - c_before["rx_dropped"]))
    m["id"] = cand_id
    m["name"] = cfg.get("name", cand_id)
    m["config"] = copy.deepcopy(cfg)
    if remote_warn:
        m["remote_apply_warning"] = remote_warn
    return m


def _live_trial_row(t: dict, goal: str) -> dict:
    return {
        "id": t.get("id", ""),
        "name": t.get("name", t.get("id", "")),
        "stage": int(t.get("stage", 0) or 0),
        "throughput_mbps": round(raw_throughput(t), 2),
        "loaded_rtt_p95_ms": t.get("loaded_rtt_p95_ms"),
        "jitter_ms": t.get("jitter_ms"),
        "retrans_pct": t.get("retrans_pct"),
        "udp_loss_pct": t.get("udp_loss_pct"),
        "stability_cov": t.get("stability_cov"),
        "score": round(float((t.get("scores") or {}).get(goal, 0.0) or 0.0), 2),
        "disqualified": bool(t.get("disqualified")),
        "disqualify_reason": t.get("disqualify_reason"),
    }


def run_staged_sweep(
    ctrl_client,
    host: str,
    data_tcp_port: int,
    data_udp_port: int,
    local_driver,
    caps_local: dict,
    caps_remote: dict,
    mode: str = "brutal",
    goal: str = "balanced",
    deep: bool = False,
    fast_test: bool = False,
    session_id: str = "tuner",
    snapshot_path: str | None = None,
    progress_cb=None,
) -> dict:
    """Execute Stage 0..5 search, isolated carrier benchmarks, and winner selection."""
    local_snap = capture_snapshot(local_driver, iface=caps_local["iface"], peer_ip=host, save_path=snapshot_path)

    best_score_so_far = 0.0
    pmtu_live: dict | None = None
    baseline_live: dict | None = None
    best_trial_live: dict | None = None
    live_trials_cache: list[dict] = []
    carriers_live: dict = {}
    warnings_live: list[str] = []

    def _emit(
        stage_idx: int,
        phase: str,
        completed: int,
        total: int,
        best_score: float | None = None,
        current_candidate: str = "",
        extra_rows: list[dict] | None = None,
    ):
        nonlocal best_score_so_far
        if best_score is not None:
            best_score_so_far = float(best_score)
        if progress_cb:
            rows = (live_trials_cache + (extra_rows or []))[-40:]
            progress_cb({
                "phase": phase,
                "stage_index": stage_idx,
                "stage_total": 6,
                "completed_trials": completed,
                "estimated_trials": total,
                "best_so_far": round(best_score_so_far, 2),
                "current_candidate": current_candidate,
                "pmtu": pmtu_live,
                "baseline": baseline_live,
                "best_trial": best_trial_live,
                "live_trials": rows,
                "carriers": carriers_live,
                "warnings": warnings_live[-10:],
            })

    def _update_scored_state(trials_list: list[dict]) -> list[dict]:
        nonlocal baseline_live, best_trial_live, live_trials_cache
        scored = score_trials(trials_list, baseline_id="baseline")
        live_trials_cache = [_live_trial_row(x, goal) for x in scored]
        base_item = next((x for x in live_trials_cache if x["id"] == "baseline"), None)
        if base_item:
            baseline_live = base_item
        base_raw = next((x for x in scored if x.get("id") == "baseline"), scored[0])
        best_raw = _select_best_candidate(scored, base_raw, goal, min_gain=0.0)
        best_trial_live = _live_trial_row(best_raw, goal)
        return scored

    sweep_dur = 0.12 if fast_test else (8.0 if deep else 3.2)
    soak_dur = 0.16 if fast_test else (16.0 if deep else 6.0)
    carrier_dur = 0.12 if fast_test else 2.5

    _emit(0, "baseline_and_pmtu", 0, 12, current_candidate="PMTU + Unloaded RTT")
    pmtu_info = probe_pmtu(host, data_udp_port, fast_test=fast_test, tcp_port=data_tcp_port)
    pmtu_live = dict(pmtu_info)
    unloaded = probe_unloaded_rtt(host, data_tcp_port, data_udp_port, samples=4 if fast_test else 20)
    unloaded_p50 = float(unloaded["tcp_rtt"]["p50"] or 1.0)
    skip_udp = bool(pmtu_info.get("udp_blocked") and unloaded.get("udp_samples_ok", 0) == 0)
    if skip_udp:
        warnings_live.append("UDP blocked/filtered on path: PMTU inferred via TCP, UDP waits skipped.")
    _emit(0, "baseline_and_pmtu", 0, 12, current_candidate="baseline")

    baseline_cfg = _config_from_snapshot(local_snap)
    baseline_cfg["name"] = "baseline"
    baseline_trial = probe_trial(
        host,
        data_tcp_port,
        data_udp_port,
        duration_s=sweep_dur,
        streams=4,
        include_bidir=True,
        include_burst=True,
        unloaded_p50_ms=unloaded_p50,
        skip_udp=skip_udp,
    )
    baseline_trial["id"] = "baseline"
    baseline_trial["name"] = "baseline"
    baseline_trial["stage"] = 0
    baseline_trial["config"] = copy.deepcopy(baseline_cfg)

    all_trials = [baseline_trial]
    best_cfg = copy.deepcopy(baseline_cfg)
    completed = 1
    est_total = 12
    scored_base = _update_scored_state(all_trials)
    _emit(0, "baseline_and_pmtu", completed, est_total, best_score=scored_base[0]["scores"][goal])

    stage_names = {1: "mtu_mss_offload", 2: "cc_qdisc_pacing", 3: "bdp_buffers_tcp"}
    for stage in (1, 2, 3):
        cands = build_stage_candidates(stage, mode, caps_local, caps_remote, best_cfg, baseline_trial, pmtu_info, fast_test=fast_test)
        est_total = max(est_total, completed + len(cands) + 4)
        for idx, cand in enumerate(cands):
            _emit(stage, stage_names[stage], completed, est_total, current_candidate=cand.get("name", f"s{stage}_{idx}"))
            cid = f"s{stage}_{idx}_{cand['name']}"
            tr = _evaluate_candidate(
                cid, cand, mode, host, data_tcp_port, data_udp_port,
                ctrl_client, local_driver, local_snap, caps_local, caps_remote,
                session_id, sweep_dur, unloaded_p50, baseline_trial, skip_udp=skip_udp,
            )
            tr["stage"] = stage
            if tr.get("remote_apply_warning"):
                warnings_live.append(f"{cand.get('name', cid)}: {tr['remote_apply_warning']}")
            all_trials.append(tr)
            completed += 1
            scored_now = _update_scored_state(all_trials)
            base_now = next((x for x in scored_now if x["id"] == "baseline"), scored_now[0])
            best_now = _select_best_candidate(scored_now, base_now, goal, min_gain=0.0)
            _emit(stage, stage_names[stage], completed, est_total, best_score=best_now["scores"][goal])
        scored_stage = score_trials(all_trials, baseline_id="baseline")
        base_stage = next((x for x in scored_stage if x["id"] == "baseline"), scored_stage[0])
        best_stage = _select_best_candidate(scored_stage, base_stage, goal, min_gain=0.5)
        if best_stage.get("id") != "baseline":
            best_cfg = copy.deepcopy(best_stage["config"])

    # Stage 4: Isolated carrier benchmarks
    _emit(4, "carrier_matrix", completed, est_total, current_candidate="raw-tcp / kcp / installed carriers")
    pmtu_min = min(int(pmtu_info.get("forward_bytes", 1460)), int(pmtu_info.get("reverse_bytes", 1460)))
    carrier_matrix = benchmark_carriers(
        ctrl_client,
        host,
        data_tcp_port,
        data_udp_port,
        pmtu_min,
        unloaded["udp_loss_pct"],
        caps_local,
        caps_remote,
        duration_s=carrier_dur,
        dry_run=fast_test,
    )
    carriers_live = {
        k: {
            "status": v.get("status"),
            "throughput_mbps": v.get("throughput_mbps"),
            "udp_loss_pct": v.get("udp_loss_pct"),
        }
        for k, v in (carrier_matrix or {}).items()
    }
    rec_carrier = recommend_best_carrier(carrier_matrix)

    # Stage 5: Brutal Top-3 Finalist Soak vs Baseline
    _emit(5, "finalist_soak", completed, completed + 3, current_candidate="soak:baseline")
    scored_pre = score_trials(all_trials, baseline_id="baseline")
    base_pre = next((x for x in scored_pre if x["id"] == "baseline"), scored_pre[0])
    min_ratio = _MIN_THROUGHPUT_RATIO.get(goal, 0.92)
    base_pre_tp = raw_throughput(base_pre)
    distinct_top = []
    seen_names = {"baseline"}
    for item in sorted(scored_pre, key=lambda x: x["scores"][goal], reverse=True):
        if item["disqualified"] or item.get("id") == "baseline":
            continue
        if base_pre_tp > 0.0 and raw_throughput(item) < base_pre_tp * min_ratio:
            continue
        nm = item["name"]
        if nm not in seen_names:
            seen_names.add(nm)
            distinct_top.append(item["config"])
        if len(distinct_top) >= (2 if fast_test else 3):
            break

    soak_trials = []
    base_soak = _evaluate_candidate(
        "baseline", baseline_cfg, "safe", host, data_tcp_port, data_udp_port,
        ctrl_client, local_driver, local_snap, caps_local, caps_remote,
        session_id, soak_dur, unloaded_p50, None, skip_udp=skip_udp,
    )
    base_soak["stage"] = 5
    soak_trials.append(base_soak)
    soak_total = completed + len(distinct_top)
    soak_rows_scored = [_live_trial_row(x, goal) for x in score_trials(soak_trials, baseline_id="baseline")]
    for idx, fcfg in enumerate(distinct_top):
        _emit(5, "finalist_soak", completed, soak_total, current_candidate=f"soak:{fcfg.get('name', 'cand')}", extra_rows=soak_rows_scored)
        ftr = _evaluate_candidate(
            f"final_{idx}_{fcfg.get('name', 'cand')}", fcfg, mode, host, data_tcp_port, data_udp_port,
            ctrl_client, local_driver, local_snap, caps_local, caps_remote,
            session_id, soak_dur, unloaded_p50, base_soak, skip_udp=skip_udp,
        )
        ftr["stage"] = 5
        soak_trials.append(ftr)
        completed += 1
        soak_scored_now = score_trials(soak_trials, baseline_id="baseline")
        soak_rows_scored = [_live_trial_row(x, goal) for x in soak_scored_now]
        for sr in soak_rows_scored:
            if not str(sr.get("name", "")).startswith("soak:"):
                sr["name"] = f"soak:{sr['name']}"
        _emit(5, "finalist_soak", completed, max(completed, soak_total), extra_rows=soak_rows_scored)

    final_scored = score_trials(soak_trials, baseline_id="baseline")
    base_final = next(x for x in final_scored if x["id"] == "baseline")
    winner_final = _select_best_candidate(final_scored, base_final, goal, min_gain=1.0)
    best_trial_live = _live_trial_row(winner_final, goal)

    _emit(6, "completed", completed, completed, best_score=winner_final["scores"][goal], extra_rows=soak_rows_scored)
    return {
        "pmtu": pmtu_info,
        "unloaded_rtt": unloaded,
        "baseline": base_final,
        "winner": winner_final,
        "top_candidates": sorted(final_scored, key=lambda x: x["scores"][goal], reverse=True),
        "carriers": carrier_matrix,
        "recommended_carrier": rec_carrier,
        "local_snapshot": local_snap,
    }
