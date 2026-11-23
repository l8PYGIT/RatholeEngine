# Milestone 4 Design Spec: Standalone `ratholemonitor.service` + Operational Telegram Bot & Live-Node Auto-Relay

**Date:** 2026-11-23
**Branch:** `feat/v2.2-backpack-upgrades`
**Scope:** Process-isolated monitor daemon (`ratholemonitor.service`), Iran-proof Telegram delivery (`tg_relay.py`), `diagnose-relay`, hysteresis alert engine, fail-closed operational Telegram bot, Hub Settings integration, installers/upgrade wiring, and tests.

---

## 1. Architectural Separation & Isolation

The monitoring and Telegram bot control loop MUST run as a dedicated systemd unit (`ratholemonitor.service`), separate from the Hub web control plane (`ratholehub.service`):

- `ratholehub` remains focused on serving the HTTPS/local REST API + UI without blocking on outbound Telegram polling, SOCKS5 relay failover, or periodic fleet checks.
- If `ratholemonitor` encounters an outbound network hang or SSH relay restart, Hub web logins, service edits, and `/metrics` remain completely unaffected.
- `ratholemonitor` queries Hub's local REST API (`http://127.0.0.1:8088` by default) over loopback using an `admin`-scope Bearer token read dynamically from `RATHOLEMON_CONF.hub_token` or `/etc/ratholehub/config.json` (`api_token`), so token rotation in Hub does not silently break local monitoring.

Files:
- `rathole-manager/ratholehub/tg_relay.py` — Pure-stdlib Telegram HTTPS transport over direct connections, explicit HTTP/HTTPS/SOCKS5 proxies, and dynamic foreign-node SSH SOCKS5 tunnels (`ssh -N -D`).
- `rathole-manager/ratholehub/monitor.py` — Standalone daemon + CLI (`run`, `once`, `diagnose-relay`, `send-test`), hysteresis alert tracker, and operational bot command router.
- `rathole-manager/ratholehub/install-monitor.sh` — Installs `/opt/ratholehub/monitor.py`, `/opt/ratholehub/tg_relay.py`, `/etc/ratholehub/monitor.json` (`0600`), `/var/lib/ratholehub` (`0700`), and `/etc/systemd/system/ratholemonitor.service`.

---

## 2. Iran-Proof Telegram Delivery (`tg_relay.py`)

In Iran networks where `api.telegram.org` is blocked directly from the Hub host, Telegram traffic must route seamlessly across foreign nodes already managed in Hub's inventory:

1. **Modes (`RELAY_MODES`):**
   - `direct` — Connects directly to `api_base` (`https://api.telegram.org`).
   - `proxy` — Tunnels via explicit `proxy_url` (`http`, `https`, `socks5`, `socks5h`) reusing `ssh_proxy.connect_socks5` and `ssh_proxy.connect_http`.
   - `ssh_auto` — Selects foreign nodes (`role == "node"` with valid `host`) from Hub inventory and establishes an argv-only local SOCKS5 relay (`ssh -N -D 127.0.0.1:<port> -o ExitOnForwardFailure=yes -o BatchMode=yes ...`), keeping the active tunnel warm and failing over to healthy peers automatically when broken.
   - `auto` — Tries `direct` first (skipping direct retry for `direct_recheck_sec` after failure once a working fallback exists), then explicit `proxy` (if configured), then `ssh_auto` across candidate foreign nodes.
2. **TLS & Security Guarantees:**
   - Outbound TLS to `api.telegram.org` uses verified system certificates (`ssl.create_default_context()`); certificate verification is never disabled by default.
   - `SshRelayTunnel` validates `host` (`RE_HOST`), `user` (`RE_SSH_USER`), and port ranges, and uses `subprocess.Popen(..., shell=False)` with `BatchMode=yes`.
   - `redact_secrets()` strips raw bot tokens and `user:pass@` proxy credentials from all exceptions, logs, API responses, and diagnostic reports.
3. **`diagnose-relay` Probe:**
   - Probes `direct`, explicit `proxy` (if configured), and up to 5 foreign SSH nodes (opening ephemeral tunnels and always closing them in `finally`).
   - Returns structured JSON with `direct`, `proxy`, `ssh_nodes`, `recommended_mode` (`direct` -> `proxy` -> `ssh_auto` -> `none`), `best_ssh_node` (lowest-latency healthy node), and an actionable `summary`.

---

## 3. Hysteresis Alert Engine (`HysteresisTracker`)

To eliminate flapping noise on lossy Iran uplinks:
- Alerts require `fail_threshold` (default `3`) consecutive failing observations before emitting a `firing` notification.
- Recovery requires `recover_threshold` (default `2`) consecutive healthy observations before emitting a `resolved` notification.
- `cooldown_sec` (default `300`) prevents repeated alert storms; `/mute [minutes]` suppresses notifications cleanly while still updating underlying incident streaks and recovery states.
- Absent/cleared observations increment `ok_streak` so resolved drift/server incidents recover and are pruned cleanly.
- State persists atomically (`0600`) to `RATHOLEMON_STATE` (`/var/lib/ratholehub/monitor-state.json`) so service restarts do not lose active incident memory or re-fire already active alerts.

---

## 4. Operational Telegram Bot (`BotCommandRouter`)

- **Fail-Closed Authorization:** If `allowed_chat_ids` is empty or an incoming `chat_id` is not listed, updates are ignored completely.
- **Commands & Inline Keyboards:**
  - `/start`, `/help` — Command reference and quick inline buttons (`Status`, `Drift`, `Alerts`, `Relay`).
  - `/status` (`cb:status`) — Fleet count, reachability summary, drift counts, active alerts, and mute state.
  - `/drift` (`cb:drift`) — Fleet drift items by severity (`error`, `warning`, `info`).
  - `/test <server> [node]` — Runs Hub bidirectional link test (`/api/servers/<server>/link-test`) after `RE_NAME` validation.
  - `/doctor <server>` — Runs panel/node `doctor` remotely after `RE_NAME` validation.
  - `/restart <server>` — Restarts service only when `allow_remote_actions` is enabled and `RE_NAME` passes.
  - `/relay` (`cb:relay`) — Displays active Telegram delivery route (`mode`, `node`, redacted `proxy`).
  - `/alerts` (`cb:alerts`) — Lists currently firing incidents.
  - `/mute [minutes]` (1..1440, default 60) / `/unmute` — Temporarily silence alert notifications.
- All dynamic values rendered in Telegram HTML messages are escaped via `html.escape(..., quote=True)` and messages >4000 chars are split cleanly on newline boundaries.

---

## 5. Hub Integration, UI & Packaging

- Hub (`hub.py`) exposes `admin`-only endpoints protected by M3 scoped RBAC and Cookie CSRF:
  - `GET /api/monitor/config` (never returns raw `bot_token` or `hub_token`; includes `service_active`).
  - `POST /api/monitor/config` (validates inputs, preserves existing `bot_token` when omitted, saves atomically with `0600`, audits without leaking secrets).
  - `POST /api/monitor/diagnose-relay` (runs `diagnose_relay` live or returns deterministic mock results when `RATHOLEHUB_MOCK=1`).
  - `POST /api/monitor/test` (delivers a test Telegram message through active relay config).
- Hub Settings page (`#/settings`) gains a Monitor & Telegram Bot configuration card (`loadMonitorSettings`, `saveMonitorConfig`, `diagnoseMonitorRelay`, `sendMonitorTest`).
- `install-hub.sh`, `update.sh`, and `.github/workflows/ci.yml` install, snapshot/upgrade/health-check, and syntax-check `tg_relay.py`, `monitor.py`, and `install-monitor.sh`.
