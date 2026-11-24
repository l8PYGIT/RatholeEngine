"""CLI entrypoint for standalone and wrapped rathole-tuner execution."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys

from . import DEFAULT_CTRL_PORT, DEFAULT_DATA_PORT, TUNER_VERSION
from .apply import apply_boot, apply_persistent, rollback_persistent, tuner_status
from .orchestrator import TunerOrchestrator
from .profile import build_profile, encode_profile_b64, load_profile_any, validate_profile
from .responder import TunerResponder
from .sysstate import RealLinuxDriver


def _parse_hostport(raw: str, default_port: int = DEFAULT_CTRL_PORT) -> tuple[str, int]:
    s = (raw or "").strip()
    if s.startswith("[") and "]:" in s:
        h, p = s[1:].split("]:", 1)
        return h, int(p)
    if s.count(":") == 1:
        h, p = s.split(":", 1)
        return h, int(p)
    return s, default_port


def _parse_tags(raw_tags: list[str] | None) -> dict:
    out = {}
    for item in raw_tags or []:
        if ":" in item:
            k, v = item.split(":", 1)
            out[k.strip()] = v.strip()
        elif "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _cmd_listen(args) -> int:
    resp = TunerResponder(
        bind_host=args.bind,
        ctrl_port=args.port,
        data_port=args.data_port,
        token=args.token,
        idle_timeout=args.idle_timeout,
        pidfile=args.pidfile or None,
    )
    def _on_sig(_signum, _frame):
        resp.stop()
    signal.signal(signal.SIGTERM, _on_sig)
    signal.signal(signal.SIGINT, _on_sig)
    resp.start()
    if args.json:
        print(json.dumps({
            "ok": True,
            "listening": True,
            "ctrl_port": resp.ctrl_port,
            "data_tcp_port": resp.data_tcp_port,
            "data_udp_port": resp.data_udp_port,
        }), flush=True)
    resp.serve_forever()
    return 0


def _cmd_run(args) -> int:
    host, port = _parse_hostport(args.peer, DEFAULT_CTRL_PORT)
    orch = TunerOrchestrator(
        peer_host=host,
        ctrl_port=port,
        token=args.token,
        mode=args.mode,
        goal=args.goal,
        deep=args.deep,
        tags=_parse_tags(args.tag),
        out_dir=args.out_dir or None,
        job_id=args.job_id or None,
    )
    report = orch.run()
    if args.apply and report.get("ok"):
        apply_persistent(RealLinuxDriver(), report["profile"], side=args.side)
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        w = report["benchmarks"]["winner"]
        b = report["benchmarks"]["baseline"]
        print(f"[+] Benchmark complete ({report['elapsed_s']}s) goal={args.goal}")
        print(f"    Baseline: {b['throughput_mbps']} Mbps | loaded p95={b['loaded_rtt_p95_ms']}ms | score={b['scores'].get(args.goal)}")
        print(f"    Winner:   {w['throughput_mbps']} Mbps | loaded p95={w['loaded_rtt_p95_ms']}ms | score={w['scores'].get(args.goal)}")
        print(f"    Profile (rthprof1): {report['profile_b64']}")
    return 0


def _cmd_test_profile(args) -> int:
    host, port = _parse_hostport(args.peer, DEFAULT_CTRL_PORT)
    orch = TunerOrchestrator(peer_host=host, ctrl_port=port, token=args.token, mode=args.mode, goal=args.goal)
    res = orch.test_profile(args.profile)
    print(json.dumps(res, ensure_ascii=False, indent=None if args.json else 2))
    return 0


def _cmd_compare(args) -> int:
    host, port = _parse_hostport(args.peer, DEFAULT_CTRL_PORT)
    orch = TunerOrchestrator(peer_host=host, ctrl_port=port, token=args.token, mode=args.mode, goal=args.goal)
    res = orch.compare_profiles(args.profiles)
    print(json.dumps(res, ensure_ascii=False, indent=None if args.json else 2))
    return 0


def _cmd_export(args) -> int:
    with open(args.report, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    prof = doc.get("profile") if isinstance(doc.get("profile"), dict) else doc
    if args.name or args.tag:
        meta = dict(prof.get("meta") or {})
        if args.name:
            meta["name"] = args.name
        if args.tag:
            tags = dict(meta.get("tags") or {})
            tags.update(_parse_tags(args.tag))
            meta["tags"] = tags
        prof = build_profile(
            meta=meta,
            environment=prof.get("environment") or {},
            diagnostics=prof.get("diagnostics") or [],
            benchmarks=prof.get("benchmarks") or {},
            iran_config=prof.get("iran_config") or {},
            node_config=prof.get("node_config") or {},
            non_kernel_recommendations=prof.get("non_kernel_recommendations") or {},
        )
    else:
        prof = validate_profile(prof, verify_sha=False)

    if args.format == "base64":
        print(encode_profile_b64(prof))
    else:
        print(json.dumps(prof, ensure_ascii=False, indent=2))
    return 0


def _cmd_validate(args) -> int:
    prof = load_profile_any(args.profile, verify_sha=False)
    out = {
        "ok": True,
        "schema": prof["schema"],
        "name": (prof.get("meta") or {}).get("name"),
        "tags": (prof.get("meta") or {}).get("tags"),
        "sha256": (prof.get("integrity") or {}).get("sha256"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=None if args.json else 2))
    return 0


def _cmd_apply(args) -> int:
    prof = load_profile_any(args.profile, verify_sha=False)
    res = apply_persistent(RealLinuxDriver(), prof, side=args.side)
    print(json.dumps(res, ensure_ascii=False, indent=None if args.json else 2))
    return 0


def _cmd_apply_boot(_args) -> int:
    res = apply_boot(RealLinuxDriver())
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


def _cmd_rollback(args) -> int:
    res = rollback_persistent(RealLinuxDriver())
    print(json.dumps(res, ensure_ascii=False, indent=None if args.json else 2))
    return 0 if res.get("ok") else 1


def _cmd_status(args) -> int:
    res = tuner_status(RealLinuxDriver())
    print(json.dumps(res, ensure_ascii=False, indent=None if args.json else 2))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="rathole-tuner", description="Bidirectional kernel, MTU/MSS, carrier & non-kernel auto-tuner")
    ap.add_argument("--version", action="version", version=f"rathole-tuner {TUNER_VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ls = sub.add_parser("listen", help="Run peer responder")
    p_ls.add_argument("--bind", default="0.0.0.0")
    p_ls.add_argument("--port", type=int, default=DEFAULT_CTRL_PORT)
    p_ls.add_argument("--data-port", type=int, default=DEFAULT_DATA_PORT)
    p_ls.add_argument("--token", required=True)
    p_ls.add_argument("--idle-timeout", type=int, default=600)
    p_ls.add_argument("--pidfile", default="")
    p_ls.add_argument("--json", action="store_true")
    p_ls.set_defaults(func=_cmd_listen)

    p_run = sub.add_parser("run", help="Run full 6-stage benchmark sweep")
    p_run.add_argument("--peer", required=True)
    p_run.add_argument("--token", required=True)
    p_run.add_argument("--mode", choices=["brutal", "safe"], default="brutal")
    p_run.add_argument("--goal", choices=["balanced", "low-latency", "max-throughput", "anti-loss"], default="balanced")
    p_run.add_argument("--deep", action="store_true")
    p_run.add_argument("--tag", action="append", default=[])
    p_run.add_argument("--out-dir", default="")
    p_run.add_argument("--job-id", default="")
    p_run.add_argument("--apply", action="store_true")
    p_run.add_argument("--side", choices=["iran", "node"], default="iran")
    p_run.add_argument("--json", action="store_true")
    p_run.set_defaults(func=_cmd_run)

    p_tp = sub.add_parser("test-profile", help="Live A/B test a JSON or rthprof1 profile")
    p_tp.add_argument("--peer", required=True)
    p_tp.add_argument("--token", required=True)
    p_tp.add_argument("--profile", required=True)
    p_tp.add_argument("--mode", choices=["brutal", "safe"], default="brutal")
    p_tp.add_argument("--goal", choices=["balanced", "low-latency", "max-throughput", "anti-loss"], default="balanced")
    p_tp.add_argument("--json", action="store_true")
    p_tp.set_defaults(func=_cmd_test_profile)

    p_cmp = sub.add_parser("compare", help="Benchmark and rank multiple profiles live")
    p_cmp.add_argument("--peer", required=True)
    p_cmp.add_argument("--token", required=True)
    p_cmp.add_argument("--mode", choices=["brutal", "safe"], default="brutal")
    p_cmp.add_argument("--goal", choices=["balanced", "low-latency", "max-throughput", "anti-loss"], default="balanced")
    p_cmp.add_argument("profiles", nargs="+")
    p_cmp.add_argument("--json", action="store_true")
    p_cmp.set_defaults(func=_cmd_compare)

    p_exp = sub.add_parser("export", help="Export report/profile to JSON or rthprof1 Base64url")
    p_exp.add_argument("report")
    p_exp.add_argument("--format", choices=["json", "base64"], default="json")
    p_exp.add_argument("--name", default="")
    p_exp.add_argument("--tag", action="append", default=[])
    p_exp.set_defaults(func=_cmd_export)

    p_val = sub.add_parser("validate", help="Validate JSON or rthprof1 profile")
    p_val.add_argument("profile")
    p_val.add_argument("--json", action="store_true")
    p_val.set_defaults(func=_cmd_validate)

    p_app = sub.add_parser("apply", help="Persistently apply a validated profile")
    p_app.add_argument("profile")
    p_app.add_argument("--side", choices=["iran", "node"], default="iran")
    p_app.add_argument("--json", action="store_true")
    p_app.set_defaults(func=_cmd_apply)

    p_ab = sub.add_parser("apply-boot", help="Re-apply stored non-sysctl profile at boot")
    p_ab.set_defaults(func=_cmd_apply_boot)

    p_rb = sub.add_parser("rollback", help="Restore pre-apply system snapshot")
    p_rb.add_argument("--json", action="store_true")
    p_rb.set_defaults(func=_cmd_rollback)

    p_st = sub.add_parser("status", help="Show host network capabilities and applied profile status")
    p_st.add_argument("--json", action="store_true")
    p_st.set_defaults(func=_cmd_status)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
