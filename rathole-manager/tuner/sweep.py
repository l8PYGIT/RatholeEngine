"""6-stage coordinate-descent search & finalist soak orchestration for rathole-tuner."""

from __future__ import annotations

import copy

from .carriers import benchmark_carriers, recommend_best_carrier
from .probes import probe_pmtu, probe_trial, probe_unloaded_rtt
from .profile import clamp_config_for_ram, compute_ram_buffer_cap
from .scoring import check_hard_fail, diagnose_findings, raw_throughput, score_trials
from .sysstate import apply_candidate, capture_snapshot, read_net_counters, restore_snapshot


def compute_bdp_buffers(bw_mbps: float, rtt_ms: float, ram_mb: int) -> list[dict]:
    """Compute 1x, 2x, and 4x BDP buffer sysctl dicts clamped strictly to 10% RAM."""
    bw = max(10.0, float(bw_mbps or 100.0))
    rtt = max(5.0, float(rtt_ms or 40.0))
    bdp = int((bw * 1_000_000.0 / 8.0) * (rtt / 1000.0))
    ram_cap = compute_ram_buffer_cap(ram_mb)
    out = []
    for mult in (1, 2, 4):
        target = min(ram_cap, max(262144, bdp * mult))
        def_w = min(target, 131072)
        out.append({
            "label": f"bdp_{mult}x",
            "net.core.rmem_max": target,
            "net.core.wmem_max": target,
            "net.core.rmem_default": min(target, 2097152),
            "net.core.wmem_default": min(target, 2097152),
            "net.ipv4.tcp_rmem": f"4096 {def_w} {target}",
            "net.ipv4.tcp_wmem": f"4096 {min(65536, def_w)} {target}",
            "net.ipv4.udp_rmem_min": 8192 if mult >= 2 else 4096,
            "net.ipv4.udp_wmem_min": 8192 if mult >= 2 else 4096,
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
    v6_floor = 1280 if ((caps_local or {}).get("ipv6_active") or (caps_remote or {}).get("ipv6_active")) else 576
    base = copy.deepcopy(best_cfg or {"sysctl": {}, "route": {}, "qdisc": {}, "offloads": {}})
    cands: list[dict] = []

    if stage == 1:
        mtus = _dedup_ints(
            [pmtu, pmtu - 40, 1380, 1280] if fast_test else [pmtu, pmtu - 20, pmtu - 40, 1460, 1420, 1380, 1350, 1280],
            v6_floor,
            1500,
        )
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
            if not fast_test and caps_local.get("has_ethtool"):
                c_off = copy.deepcopy(base)
                c_off["name"] = "offloads_tso_off"
                c_off["offloads"] = {"tso": False, "gso": False, "gro": True}
                cands.append(c_off)
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
        common_qd = [q for q in ("fq", "fq_codel", "cake") if q in (l_qd & r_qd)] or ["fq_codel"]
        lowats = [32768] if fast_test else [16384, 32768, 65536, 131072, 4294967295]

        combos = []
        for cc in common_cc[: (2 if fast_test else 5)]:
            for qd in common_qd[: (2 if fast_test else 3)]:
                for lw in lowats:
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
        cwnds = [20] if fast_test else [10, 32, 64]
        for b in bdps[: (2 if fast_test else 3)]:
            label = b.pop("label")
            for cw in cwnds[: (1 if fast_test else 2)]:
                c = copy.deepcopy(base)
                c["name"] = f"{label}_cwnd{cw}"
                c["route"] = {"initcwnd": cw, "initrwnd": cw, "advmss": max(536, int(c.get("mtu", 1460)) - 40)}
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


def _config_from_snapshot(snap: dict) -> dict:
    return {
        "mtu": snap.get("mtu", 1500),
        "mss_clamp": 0,
        "qdisc": {"kind": (snap.get("qdisc") or {}).get("kind", "fq_codel"), "params": {}},
        "txqueuelen": snap.get("txqueuelen", 1000),
        "route": copy.deepcopy(snap.get("route") or {}),
        "offloads": copy.deepcopy(snap.get("offloads") or {}),
        "sysctl": {
            k: v
            for k, v in (snap.get("sysctl") or {}).items()
            if k in (
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
        },
    }


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
) -> dict:
    local_iface = caps_local["iface"]
    remote_iface = caps_remote["iface"]
    local_ram = caps_local["ram_mb"]
    remote_ram = caps_remote["ram_mb"]

    c_before = read_net_counters(local_driver, local_iface)
    if mode == "brutal":
        cfg_local = clamp_config_for_ram(cfg, local_ram)
        cfg_remote = clamp_config_for_ram(cfg, remote_ram)
        apply_candidate(
            local_driver, cfg_local, iface=local_iface, peer_ip=host, session_id=session_id,
            ram_mb=local_ram, ipv6_active=caps_local["ipv6_active"],
        )
        ctrl_client.call("apply_cand", {"config": cfg_remote, "iface": remote_iface, "session_id": session_id})

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
    return m


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

    def _emit(stage_idx: int, phase: str, completed: int, total: int, best_score: float = 0.0):
        if progress_cb:
            progress_cb({
                "phase": phase,
                "stage_index": stage_idx,
                "stage_total": 6,
                "completed_trials": completed,
                "estimated_trials": total,
                "best_so_far": round(best_score, 2),
            })

    sweep_dur = 0.12 if fast_test else (8.0 if deep else 3.2)
    soak_dur = 0.16 if fast_test else (16.0 if deep else 6.0)
    carrier_dur = 0.12 if fast_test else 2.5

    _emit(0, "baseline_and_pmtu", 0, 12)
    pmtu_info = probe_pmtu(host, data_udp_port, fast_test=fast_test)
    unloaded = probe_unloaded_rtt(host, data_tcp_port, data_udp_port, samples=4 if fast_test else 20)
    unloaded_p50 = float(unloaded["tcp_rtt"]["p50"] or 1.0)

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
    )
    baseline_trial["id"] = "baseline"
    baseline_trial["name"] = "baseline"
    baseline_trial["config"] = copy.deepcopy(baseline_cfg)

    all_trials = [baseline_trial]
    best_cfg = copy.deepcopy(baseline_cfg)
    completed = 1
    est_total = 12

    for stage in (1, 2, 3):
        stage_names = {1: "mtu_mss_offload", 2: "cc_qdisc_pacing", 3: "bdp_buffers_tcp"}
        cands = build_stage_candidates(stage, mode, caps_local, caps_remote, best_cfg, baseline_trial, pmtu_info, fast_test=fast_test)
        est_total = max(est_total, completed + len(cands) + 4)
        for idx, cand in enumerate(cands):
            cid = f"s{stage}_{idx}_{cand['name']}"
            tr = _evaluate_candidate(
                cid, cand, mode, host, data_tcp_port, data_udp_port,
                ctrl_client, local_driver, local_snap, caps_local, caps_remote,
                session_id, sweep_dur, unloaded_p50, baseline_trial,
            )
            all_trials.append(tr)
            completed += 1
            scored_now = score_trials(all_trials, baseline_id="baseline")
            alive = [x for x in scored_now if not x["disqualified"]]
            best_now = max(alive, key=lambda x: x["scores"][goal]) if alive else scored_now[0]
            _emit(stage, stage_names[stage], completed, est_total, best_now["scores"][goal])
        scored_stage = score_trials(all_trials, baseline_id="baseline")
        alive_stage = [x for x in scored_stage if not x["disqualified"] and x["id"] != "baseline"]
        if alive_stage:
            best_stage = max(alive_stage, key=lambda x: x["scores"][goal])
            best_cfg = copy.deepcopy(best_stage["config"])

    # Stage 4: Isolated carrier benchmarks
    _emit(4, "carrier_matrix", completed, est_total)
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
    rec_carrier = recommend_best_carrier(carrier_matrix)

    # Stage 5: Brutal Top-3 Finalist Soak vs Baseline
    _emit(5, "finalist_soak", completed, completed + 3)
    scored_pre = score_trials(all_trials, baseline_id="baseline")
    distinct_top = []
    seen_names = {"baseline"}
    for item in sorted(scored_pre, key=lambda x: x["scores"][goal], reverse=True):
        if item["disqualified"]:
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
        session_id, soak_dur, unloaded_p50, None,
    )
    soak_trials.append(base_soak)
    for idx, fcfg in enumerate(distinct_top):
        ftr = _evaluate_candidate(
            f"final_{idx}_{fcfg.get('name', 'cand')}", fcfg, mode, host, data_tcp_port, data_udp_port,
            ctrl_client, local_driver, local_snap, caps_local, caps_remote,
            session_id, soak_dur, unloaded_p50, base_soak,
        )
        soak_trials.append(ftr)
        completed += 1

    final_scored = score_trials(soak_trials, baseline_id="baseline")
    base_final = next(x for x in final_scored if x["id"] == "baseline")
    alive_final = [x for x in final_scored if not x["disqualified"]]
    winner_final = max(alive_final, key=lambda x: x["scores"][goal]) if alive_final else base_final

    _emit(6, "completed", completed, completed, winner_final["scores"][goal])
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
