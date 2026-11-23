# Milestone 5 Design Spec: Multi-Carrier Adaptive Fallback Chain & Health-Scored Backup Endpoints

**Date:** 2026-11-23
**Branch:** `feat/v2.2-backpack-upgrades`
**Scope:** Real `noise` & `frp` adaptive probes, configurable multi-carrier fallback chain (`ADAPTIVE_CHAIN`) with optional candidate pre-probing (`ADAPTIVE_PROBE_CANDIDATES`) and automatic primary recovery (`ADAPTIVE_AUTO_RECOVER`), EWMA health-scored backup Iran endpoints (`BACKUP_SERVERS` + `ratholenode endpoints`), Hub command/parser/UI integration, and regression tests.

---

## 1. Real `noise` & `frp` Probes + Unified Carrier Dispatcher

Previously, `ratholenode`'s `adaptive_run_probe` fell through to a blind `healthy:0` stub for `noise` and only checked `systemctl is-active` for `frp`:

- **`adaptive_probe_noise [remote]`**: Requires non-empty remote (`$NOISE_REMOTE`) and `NOISE_PUBKEY` (returns `unconfigured:0` otherwise), and executes `adaptive_probe_tcp` against the Noise listener endpoint.
- **`adaptive_probe_frp [remote] [transport]`**: Requires non-empty remote (`$FRP_REMOTE`) and `FRP_TOKEN` (`unconfigured:0` otherwise). Probing uses `adaptive_probe_tcp` for `tcp`/`websocket` transports and a lightweight stdlib Python 3 UDP probe (`udp_refused:<ms>` / `udp_failed:<ms>` / `healthy:<ms>`) for `kcp`/`quic`. In `adaptive_run_probe` when `TUNNEL=frp`, local daemon health (`$FRP_CLI_SVC`) is checked first (`dead:0` if inactive) before running `adaptive_probe_frp`.
- **`adaptive_probe_carrier <carrier> [endpoint_override]`**: Single dispatcher supporting `ws`, `noise`, `kcp`, `frp`, `plain`, and `backhaul` across both live probing and pre-switch candidate evaluation.

---

## 2. Multi-Carrier Fallback Chain & Auto-Recovery

- **`ADAPTIVE_CHAIN`** (default `"ws,kcp"`): Comma-separated ordered list of 1–5 unique carriers from `{ws, noise, kcp, frp, plain}`. Wait: defaults preserve `"ws,kcp"` and `ADAPTIVE_PROBE_CANDIDATES=0` so existing deployments and `test_phase2_bash_lifecycle.py` behave identically unless opted in.
- **`ALLOW_INSECURE=1` Gate**: `plain` is never considered ready unless `ALLOW_INSECURE=1` (`adaptive_plain_allowed == yes`) and `PLAIN_REMOTE` is configured.
- **Candidate Selection (`adaptive_pick_next_carrier`)**: Rotates through the chain starting after the active carrier (`$TUNNEL`), checks readiness (`adaptive_carrier_ready`), and when `ADAPTIVE_PROBE_CANDIDATES=1`, probes candidates before switching so dead links (e.g. blocked `noise`) are skipped immediately.
- **Daemon Switching (`adaptive_switch_carrier`)**:
  - Switching to `frp`: sets `TUNNEL=frp`, generates `frpc.toml` via `gen_frp_client_toml`, stops/disables `rathole-client`, and enables/restarts `frpc`.
  - Switching to `ws|kcp|noise|plain`: sets `TUNNEL`, regenerates `client.toml` via `gen_client`, disables `frpc`, and restarts `rathole-client`.
- **Primary Auto-Recovery (`ADAPTIVE_AUTO_RECOVER=1`)**: While active on a secondary carrier or backup endpoint and probes stay healthy for `ADAPTIVE_RECOVERIES` checks after cooldown expires, probes the primary carrier (`${ADAPTIVE_CHAIN%%,*}`) or `PRIMARY_SERVER` and restores primary cleanly.

---

## 3. Health-Scored Backup Addresses (`ratholenode endpoints`)

- **`node.env` Keys**: `PRIMARY_SERVER` (preserved original primary `host:port`) and `BACKUP_SERVERS` (comma-separated backup `host:port` list, max 8).
- **EWMA Scoring (`/etc/rathole/endpoint-scores.json`, mode `0600`)**:
  - Healthy probe score sample: `70.0 + max(0.0, 30.0 - min(latency_ms, 600.0) / 20.0)` (`70..100`).
  - Failed probe score sample: `0.0`.
  - Exponentially weighted moving average (`alpha = 0.5`) tracks `score`, `last_ok`, `last_ms`, `ok_count`, `fail_count`, `consecutive_fails`, and `updated_at`.
- **CLI Subcommands (`ratholenode endpoints ...`)**:
  - `add <host:port>` / `rm <host:port>` / `ls [--json]` / `test [--json]` / `switch <host:port>`.
- **Failover Integration**: When `cmd_adaptive run` triggers switch (`failures >= ADAPTIVE_FAILURES`) and no alternative carrier in `ADAPTIVE_CHAIN` is ready/healthy, if `BACKUP_SERVERS` is populated it probes all addresses, picks the highest-scored healthy endpoint != `$SERVER`, preserves `PRIMARY_SERVER`, updates `SERVER` (plus host-matched `NOISE_REMOTE`/`PLAIN_REMOTE`/`FRP_REMOTE`), regenerates config, and restarts the tunnel.

---

## 4. Hub, UI & Security Controls

- **Strict Env Parsing**: `adaptive_load_env` keeps strict key allow-listing and regex checks (`adaptive_valid_chain`, `^[01]$`) with zero `eval`/`source`.
- **`hubcmds.py`**: Validates `--chain` (`RE_CHAIN` + uniqueness) and `--probe-candidates`/`--allow-insecure` on `adaptive_on`, while preserving exact original argv when omitted; adds `endpoints_ls`, `endpoints_test` (read-only), and `endpoints_add`/`endpoints_rm`/`endpoints_switch` (`RE_IPPORT`, in `WRITE_ACTIONS`).
- **`hub.py` & UI (`i18n.js`, `app.js`)**: Expands `parse_adaptive_state` safely without exposing secrets (`CONTROL_PATH`/`/_rh/`), adds mock endpoint responses, updates `adaptiveOnNode`, and adds the Node page Backup Endpoints modal (`openEndpointsModal`).
