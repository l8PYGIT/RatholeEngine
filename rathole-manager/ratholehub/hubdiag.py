# hubdiag.py — bidirectional Link Test synthesis va Fleet Drift Detection (read-only).
# faghat Python stdlib — hich taghir/reconcile rooye serverha anjam nemidahad.

from __future__ import annotations

from datetime import datetime, timezone
import re

_SEV_RANK = {"error": 0, "warning": 1, "info": 2}


def synthesize_link_test(node_name, iran_res, node_res=None, peer_name=None):
    """Combine Iran->Node and Node->Iran link-test payloads into a single diagnosis."""
    backend = None
    if isinstance(node_res, dict):
        for b in (node_res.get("backends") or []):
            if isinstance(b, dict) and b.get("name") == node_name:
                backend = b
                break

    if isinstance(iran_res, dict) and not iran_res.get("listener_up", True):
        verdict = "failed"
        code = "listener_down"
        diag = "Iran listener port (%s) is not listening or refused connection" % (iran_res.get("port") or "?")
    elif backend is not None and not backend.get("up", True):
        verdict = "failed"
        code = "backend_down"
        diag = "Node local backend (127.0.0.1:%s) is not responding (check Xray/service)" % (backend.get("port") or "?")
    elif isinstance(node_res, dict) and not node_res.get("ok"):
        verdict = "failed"
        code = "carrier_unreachable"
        diag = "Node -> Iran carrier (%s) failed: %s" % (
            node_res.get("transport") or "?",
            node_res.get("detail") or "unreachable",
        )
    elif isinstance(iran_res, dict) and not iran_res.get("ok"):
        verdict = "failed"
        code = "e2e_failed"
        diag = "Iran -> Node E2E probe failed: %s" % (iran_res.get("detail") or "tunnel timed out or closed")
    elif (isinstance(iran_res, dict) and iran_res.get("verdict") == "degraded") or (
        isinstance(node_res, dict) and node_res.get("verdict") == "degraded"
    ):
        verdict = "degraded"
        code = "degraded_link"
        diag = "Link is reachable but exhibits elevated latency, jitter, or packet loss"
    elif iran_res is None and node_res is None:
        verdict = "failed"
        code = "e2e_failed"
        diag = "No link-test telemetry received from either side"
    else:
        verdict = "healthy"
        code = "healthy"
        if isinstance(iran_res, dict) and iran_res.get("verdict") == "open_no_http":
            diag = "Bidirectional link healthy (non-HTTP backend kept TCP tunnel open)"
        else:
            diag = "Bidirectional link healthy"

    return {
        "ok": verdict != "failed",
        "verdict": verdict,
        "diagnosis_code": code,
        "diagnosis": diag,
        "node": node_name,
        "peer": peer_name,
        "iran_to_node": iran_res,
        "node_to_iran": node_res,
    }


def _parse_cert_expiry(raw):
    if not raw or not isinstance(raw, str):
        return None
    norm = " ".join(raw.strip().split())
    for fmt in ("%b %d %H:%M:%S %Y GMT", "%b %d %H:%M:%S %Y UTC", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(norm, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _host_key(val):
    if not val or not isinstance(val, str):
        return ""
    s = val.strip().lower()
    if s.startswith("[") and "]" in s:
        return s[1:s.index("]")]
    if s.count(":") == 1:
        return s.split(":", 1)[0]
    return s


def _iran_matches_node_server(iran_name, iran_srv, iran_ov, node_srv, node_ov):
    target = _host_key(node_ov.get("main_server") or "")
    if not target:
        return False
    cands = {
        _host_key(iran_ov.get("domain") or ""),
        _host_key(iran_srv.get("host") or ""),
        _host_key(iran_ov.get("host") or ""),
        _host_key((iran_ov.get("status") or {}).get("domain") or ""),
        _host_key((iran_ov.get("status") or {}).get("public_ip") or ""),
    }
    cands.discard("")
    return target in cands


def _check_carrier_alignment(ir_name, ov_ir, nd, node_srv_name, nov, node_lane, is_bh_lane):
    items = []
    ir_tr = str(nd.get("transport") or "ws")
    node_name = nd.get("name") or ""

    if not nd.get("sni"):
        if ir_tr == "backhaul":
            bh_enabled = bool((nov.get("backhaul") or {}).get("enabled"))
            if not is_bh_lane or not bh_enabled:
                items.append({
                    "severity": "error",
                    "kind": "carrier_mismatch",
                    "server": ir_name,
                    "peer": node_srv_name,
                    "service": node_name,
                    "expected": "backhaul",
                    "actual": "backhaul" if is_bh_lane else node_lane,
                    "message": "Iran expects backhaul lane but node '%s' is not active in backhaul" % node_srv_name,
                })
            else:
                ir_prof = (
                    ((ov_ir.get("status") or {}).get("features") or {}).get("backhaul", {}).get("profile")
                    or (ov_ir.get("backhaul") or {}).get("profile")
                    or ""
                )
                nd_prof = (nov.get("backhaul") or {}).get("profile") or ""
                if ir_prof and nd_prof and ir_prof != nd_prof:
                    items.append({
                        "severity": "error",
                        "kind": "profile_mismatch",
                        "server": ir_name,
                        "peer": node_srv_name,
                        "service": node_name,
                        "expected": ir_prof,
                        "actual": nd_prof,
                        "message": "Backhaul mux profile mismatch (%s vs %s)" % (ir_prof, nd_prof),
                    })
        elif ir_tr in ("frp", "frp_gre"):
            if is_bh_lane or node_lane != "frp":
                items.append({
                    "severity": "error",
                    "kind": "carrier_mismatch",
                    "server": ir_name,
                    "peer": node_srv_name,
                    "service": node_name,
                    "expected": ir_tr,
                    "actual": "backhaul" if is_bh_lane else node_lane,
                    "message": "Iran expects %s but node '%s' runs %s" % (ir_tr, node_srv_name, "backhaul" if is_bh_lane else node_lane),
                })
            else:
                ir_ftr = ((ov_ir.get("frp") or {}).get("transport") or "").lower()
                nd_ftr = ((nov.get("frp") or {}).get("transport") or "").lower()
                if ir_ftr and nd_ftr and ir_ftr != nd_ftr:
                    items.append({
                        "severity": "error",
                        "kind": "protocol_mismatch",
                        "server": ir_name,
                        "peer": node_srv_name,
                        "service": node_name,
                        "expected": ir_ftr,
                        "actual": nd_ftr,
                        "message": "FRP transport mismatch (%s vs %s)" % (ir_ftr, nd_ftr),
                    })
            if ir_tr == "frp_gre":
                ir_gre = bool((ov_ir.get("gre") or {}).get("enabled"))
                nd_gre = bool((nov.get("gre") or {}).get("enabled"))
                if not ir_gre or not nd_gre:
                    items.append({
                        "severity": "error",
                        "kind": "carrier_mismatch",
                        "server": ir_name,
                        "peer": node_srv_name,
                        "service": node_name,
                        "expected": "frp_gre (GRE on both ends)",
                        "actual": "iran_gre=%s node_gre=%s" % (ir_gre, nd_gre),
                        "message": "frp_gre requires GRE enabled on both Iran and node",
                    })
        elif ir_tr in ("noise", "plain"):
            if is_bh_lane or node_lane != ir_tr:
                items.append({
                    "severity": "error",
                    "kind": "carrier_mismatch",
                    "server": ir_name,
                    "peer": node_srv_name,
                    "service": node_name,
                    "expected": ir_tr,
                    "actual": "backhaul" if is_bh_lane else node_lane,
                    "message": "Iran expects %s but node '%s' runs %s" % (ir_tr, node_srv_name, "backhaul" if is_bh_lane else node_lane),
                })
        elif ir_tr == "kcp":
            if is_bh_lane or node_lane != "kcp":
                items.append({
                    "severity": "error",
                    "kind": "carrier_mismatch",
                    "server": ir_name,
                    "peer": node_srv_name,
                    "service": node_name,
                    "expected": "kcp",
                    "actual": "backhaul" if is_bh_lane else node_lane,
                    "message": "Iran expects kcp but node '%s' runs %s" % (node_srv_name, "backhaul" if is_bh_lane else node_lane),
                })
            else:
                ir_kprof = (ov_ir.get("kcp") or {}).get("profile") or ""
                nd_kprof = (nov.get("kcp") or {}).get("profile") or ""
                if ir_kprof and nd_kprof and ir_kprof != nd_kprof:
                    items.append({
                        "severity": "error",
                        "kind": "profile_mismatch",
                        "server": ir_name,
                        "peer": node_srv_name,
                        "service": node_name,
                        "expected": ir_kprof,
                        "actual": nd_kprof,
                        "message": "KCP profile mismatch (%s vs %s)" % (ir_kprof, nd_kprof),
                    })
        elif ir_tr == "gre":
            ir_gre = bool((ov_ir.get("gre") or {}).get("enabled"))
            nd_gre = bool((nov.get("gre") or {}).get("enabled"))
            if is_bh_lane or not ir_gre or not nd_gre:
                items.append({
                    "severity": "error",
                    "kind": "carrier_mismatch",
                    "server": ir_name,
                    "peer": node_srv_name,
                    "service": node_name,
                    "expected": "gre (both ends)",
                    "actual": "iran_gre=%s node_gre=%s lane=%s" % (ir_gre, nd_gre, "backhaul" if is_bh_lane else node_lane),
                    "message": "GRE carrier requires GRE interface enabled on both Iran and node",
                })
        elif ir_tr == "ws":
            if is_bh_lane or node_lane in ("frp", "noise", "plain"):
                items.append({
                    "severity": "error",
                    "kind": "carrier_mismatch",
                    "server": ir_name,
                    "peer": node_srv_name,
                    "service": node_name,
                    "expected": "ws",
                    "actual": "backhaul" if is_bh_lane else node_lane,
                    "message": "Iran expects ws but node '%s' runs %s" % (node_srv_name, "backhaul" if is_bh_lane else node_lane),
                })
            elif node_lane == "kcp":
                items.append({
                    "severity": "info",
                    "kind": "carrier_mismatch",
                    "server": ir_name,
                    "peer": node_srv_name,
                    "service": node_name,
                    "expected": "ws",
                    "actual": "kcp",
                    "message": "Node '%s' is on kcp while Iran lists ws (adaptive failover may be active — review before changing)" % node_srv_name,
                })

    return items


def compute_fleet_drift(inventory, overviews, hub_version=None, now=None):
    """Read-only fleet configuration/health drift detector across Hub inventory."""
    if now is None:
        now_dt = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now_dt = now.replace(tzinfo=timezone.utc)
    else:
        now_dt = now.astimezone(timezone.utc)

    items = []
    unreachable = 0
    inv = list(inventory or [])
    ovs = overviews or {}

    reachable_irans = []
    reachable_nodes = []

    for srv in inv:
        name = srv.get("name") or ""
        role = srv.get("role") or ""
        ov = ovs.get(name) or {"reachable": False, "error": "missing overview"}
        if ov.get("reachable") is False:
            unreachable += 1
            items.append({
                "severity": "error",
                "kind": "unreachable",
                "server": name,
                "peer": "",
                "service": "",
                "expected": "reachable",
                "actual": ov.get("error") or "unreachable",
                "message": "Server '%s' is unreachable (%s)" % (name, ov.get("error") or "offline"),
            })
            continue

        if role == "iran":
            reachable_irans.append((srv, ov))
        else:
            reachable_nodes.append((srv, ov))

        # 2. Manager version skew
        mgr_ver = ((ov.get("version") or {}).get("manager") or "").strip()
        if hub_version and hub_version not in ("", "unknown", "?") and mgr_ver and mgr_ver not in ("unknown", "?") and mgr_ver != hub_version:
            items.append({
                "severity": "warning",
                "kind": "version_skew",
                "server": name,
                "peer": "",
                "service": "",
                "expected": hub_version,
                "actual": mgr_ver,
                "message": "Manager version skew on '%s' (installed %s vs Hub %s)" % (name, mgr_ver, hub_version),
            })

        # 3. Stopped core or configured carrier services
        st = ov.get("status") or {}
        if role == "iran":
            svcs = st.get("services") or {}
            feats = st.get("features") or {}
            for k in ("rathole_server", "nginx", "nginx_config_ok"):
                if k in svcs and svcs.get(k) != "yes":
                    items.append({
                        "severity": "error",
                        "kind": "service_down",
                        "server": name,
                        "peer": "",
                        "service": k,
                        "expected": "yes",
                        "actual": str(svcs.get(k)),
                        "message": "Core service/check '%s' is unhealthy (%s) on '%s'" % (k, svcs.get(k), name),
                    })
            for fk, sk_opts in (("noise", ("noise",)), ("backhaul", ("backhaul",)), ("frp", ("frp", "frps"))):
                if (feats.get(fk) or {}).get("configured"):
                    vals = [svcs.get(sk) for sk in sk_opts if sk in svcs]
                    if vals and all(v == "no" for v in vals):
                        items.append({
                            "severity": "error",
                            "kind": "service_down",
                            "server": name,
                            "peer": "",
                            "service": fk,
                            "expected": "active",
                            "actual": "inactive",
                            "message": "Configured carrier '%s' is inactive on '%s'" % (fk, name),
                        })
            gre_ov = ov.get("gre") or {}
            if gre_ov.get("enabled") and ("active" in gre_ov) and not gre_ov.get("active"):
                items.append({
                    "severity": "error",
                    "kind": "service_down",
                    "server": name,
                    "peer": "",
                    "service": gre_ov.get("name") or "gre",
                    "expected": "UP",
                    "actual": "DOWN",
                    "message": "GRE interface '%s' is DOWN on '%s'" % (gre_ov.get("name") or "gre1", name),
                })

            # 4. TLS certificate expiry
            cert = st.get("cert") or {}
            exp_dt = _parse_cert_expiry(cert.get("expiry"))
            if exp_dt is not None:
                days_left = int((exp_dt - now_dt).total_seconds() // 86400)
                if days_left <= 0:
                    items.append({
                        "severity": "error",
                        "kind": "cert_expiring",
                        "server": name,
                        "peer": "",
                        "service": "tls_cert",
                        "expected": "> 14d",
                        "actual": "%dd" % days_left,
                        "message": "TLS certificate on '%s' has EXPIRED (%d days)" % (name, days_left),
                    })
                elif days_left <= 14:
                    items.append({
                        "severity": "warning",
                        "kind": "cert_expiring",
                        "server": name,
                        "peer": "",
                        "service": "tls_cert",
                        "expected": "> 14d",
                        "actual": "%dd" % days_left,
                        "message": "TLS certificate on '%s' expires in %d day(s)" % (name, days_left),
                    })
        else:
            main_svc = ((st.get("main") or {}).get("service") or {})
            if "active" in main_svc and main_svc.get("active") is False:
                items.append({
                    "severity": "error",
                    "kind": "service_down",
                    "server": name,
                    "peer": "",
                    "service": main_svc.get("name") or "tunnel",
                    "expected": "active",
                    "actual": "inactive",
                    "message": "Active tunnel service '%s' is stopped on node '%s'" % (main_svc.get("name") or "client", name),
                })
            st_gre = st.get("gre") if isinstance(st.get("gre"), dict) else {}
            ov_gre = ov.get("gre") if isinstance(ov.get("gre"), dict) else {}
            gre_ov = st_gre if "active" in st_gre else ov_gre
            if (gre_ov.get("enabled") or gre_ov.get("name")) and ("active" in gre_ov) and not gre_ov.get("active"):
                items.append({
                    "severity": "error",
                    "kind": "service_down",
                    "server": name,
                    "peer": "",
                    "service": gre_ov.get("name") or "gre",
                    "expected": "UP",
                    "actual": "DOWN",
                    "message": "GRE interface '%s' is DOWN on node '%s'" % (gre_ov.get("name") or "gre1", name),
                })

    # Index all reachable foreign node services for orphan & alignment checks
    # node_svc_map[svc_name] = list of dicts describing where svc is configured on foreign nodes
    node_svc_map = {}
    for nsrv, nov in reachable_nodes:
        nname = nsrv.get("name") or ""
        nlane = nov.get("main_tunnel") or "ws"
        for s_item in (nov.get("services") or []):
            sname = s_item.get("name") or ""
            if sname:
                node_svc_map.setdefault(sname, []).append({
                    "node_srv": nsrv, "nov": nov, "server": nname,
                    "inbound": str(s_item.get("inbound") or ""),
                    "lane": nlane, "is_bh": False, "is_upstream": False,
                })
        for b_item in (nov.get("backhaul_services") or []):
            sname = b_item.get("name") or ""
            if sname:
                node_svc_map.setdefault(sname, []).append({
                    "node_srv": nsrv, "nov": nov, "server": nname,
                    "inbound": str(b_item.get("inbound") or ""),
                    "lane": "backhaul", "is_bh": True, "is_upstream": False,
                })
        for up in (nov.get("upstreams") or []):
            ulane = up.get("tunnel") or "ws"
            for u_item in (up.get("services") or []):
                sname = u_item.get("name") or ""
                if sname:
                    node_svc_map.setdefault(sname, []).append({
                        "node_srv": nsrv, "nov": nov, "server": nname,
                        "inbound": str(u_item.get("inbound") or ""),
                        "lane": ulane, "is_bh": False, "is_upstream": True,
                        "upstream_server": up.get("server") or "",
                    })

    all_iran_node_names = set()
    for isrv, iov in reachable_irans:
        ir_name = isrv.get("name") or ""
        for nd in (iov.get("nodes") or []):
            n_nm = nd.get("name") or ""
            if not n_nm:
                continue
            all_iran_node_names.add(n_nm)
            matches = node_svc_map.get(n_nm) or []
            if not matches:
                if len(reachable_nodes) >= 1:
                    items.append({
                        "severity": "warning",
                        "kind": "orphan_iran_node",
                        "server": ir_name,
                        "peer": "",
                        "service": n_nm,
                        "expected": "registered on foreign node",
                        "actual": "missing on reachable nodes",
                        "message": "Iran node '%s' on '%s' has no matching service on any reachable foreign node" % (n_nm, ir_name),
                    })
                continue

            # Prefer non-upstream match or match pointing at this Iran panel
            chosen = None
            for m in matches:
                if not m["is_upstream"] and _iran_matches_node_server(ir_name, isrv, iov, m["node_srv"], m["nov"]):
                    chosen = m
                    break
            if chosen is None:
                chosen = matches[0]

            if not chosen["is_upstream"]:
                items.extend(_check_carrier_alignment(
                    ir_name, iov, nd, chosen["server"], chosen["nov"], chosen["lane"], chosen["is_bh"]
                ))

            # 8. Inbound port mismatch
            ir_inb = str(nd.get("inbound_port") or nd.get("inbound") or "").strip()
            nd_inb = chosen["inbound"].strip()
            if ir_inb and nd_inb and ir_inb != nd_inb:
                items.append({
                    "severity": "warning",
                    "kind": "inbound_port_mismatch",
                    "server": ir_name,
                    "peer": chosen["server"],
                    "service": n_nm,
                    "expected": ir_inb,
                    "actual": nd_inb,
                    "message": "Inbound port mismatch for '%s' (Iran expects %s, node '%s' uses %s)" % (
                        n_nm, ir_inb, chosen["server"], nd_inb
                    ),
                })

    # 6. Orphan foreign services
    if len(reachable_irans) >= 1:
        for sname, mlist in node_svc_map.items():
            if sname not in all_iran_node_names:
                for m in mlist:
                    items.append({
                        "severity": "warning",
                        "kind": "orphan_foreign_service",
                        "server": m["server"],
                        "peer": "",
                        "service": sname,
                        "expected": "registered on Iran panel",
                        "actual": "missing on reachable Iran panels",
                        "message": "Service '%s' on node '%s' is not registered on any reachable Iran panel" % (
                            sname, m["server"]
                        ),
                    })

    items.sort(key=lambda x: (_SEV_RANK.get(x["severity"], 9), x.get("server") or "", x.get("service") or "", x.get("kind") or ""))

    counts = {"error": 0, "warning": 0, "info": 0}
    for it in items:
        sev = it.get("severity")
        if sev in counts:
            counts[sev] += 1

    return {
        "checked_at": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hub_version": hub_version or "",
        "servers_checked": len(inv),
        "servers_unreachable": unreachable,
        "summary": {
            "total": len(items),
            "error": counts["error"],
            "warning": counts["warning"],
            "info": counts["info"],
            "clean": len(items) == 0,
        },
        "items": items,
    }
