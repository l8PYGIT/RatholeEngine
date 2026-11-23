# Milestone 2 (M2) Design Spec — Bidirectional Link Test & Read-Only Fleet Drift Detection

**Branch:** `feat/v2.2-backpack-upgrades`  
**Target Release:** `v2.2.0` (Milestone 2 of 7)

---

## 1. Scope

Milestone 2 introduces two operator-critical observability & verification capabilities ported/adapted from `BackPack` into `RatholeEngine`:

1. **Bidirectional Connection Test / Link Test (`ratholectl test`, `ratholenode test`, `POST /api/servers/<name>/link-test`, Hub Link Test modal)**
   - Measures real data-path latency (`min`, `avg`, `max`, `p95`), IPDV `jitter`, packet/probe loss percentage, listener health, backend inbound port liveness on the foreign node, and GRE L3 underlay reachability when configured.
   - Replaces the coarse `doctor` dump inside Hub service `⋯ → Health test` with a fast, structured bidirectional link probe (falling back gracefully to `doctor` on older remote nodes that lack the `test` subcommand).
2. **Read-Only Fleet Drift Detection (`hubdiag.compute_fleet_drift`, `GET /api/fleet/drift`, Hub Dashboard Drift Panel)**
   - Audits the entire inventory on-demand to surface desynchronizations across Iran panels and foreign nodes (unreachable servers, manager version skew, stopped carrier services, expiring/expired TLS certs, orphan Iran nodes, orphan foreign services, carrier/protocol/profile mismatches, and inbound port mismatches).
   - **Strict safety invariant:** Detection is 100% read-only (display + actionable navigation hints only). It **never** auto-reconciles or mutates server state (especially important because adaptive failover intentionally temporarily switches `ws ↔ kcp`).

---

## 2. Architecture & Component Interfaces

### 2.1 Shared Probe Helper (`rathole-manager/common.sh`)

- **`rth_gre_peer_ip <tunnel_ip>`:** Computes the opposite point-to-point host IP in IPv4 `/30` or IPv6 `/126` tunnels (`10.10.10.1 ↔ 10.10.10.2`, `fd00::1 ↔ fd00::2`).
- **`rth_link_probe`:** Pure stdlib Python 3.8+ probe runner supporting `--mode <http_ws|tls_direct|ws_tls|ws_plain|bh_tls|tcp|icmp>`:
  - `http_ws` (Iran E2E probe on `127.0.0.1:<port>`): tests TCP listener + sends `count` RFC 6455 HTTP/1.1 WebSocket Upgrade requests across the live reverse tunnel; flags EOF/`ConnectionResetError`/HTTP `502`/`503`/`504` as `failed` and tolerates idle raw-TCP non-HTTP backends as `open_no_http` (no fake 0.1 ms RTT).
  - `tls_direct` (Iran `game`/SNI node on `127.0.0.1:<port>`): times TCP + TLS ClientHello/ServerHello handshake via the reverse tunnel.
  - `ws_tls` / `ws_plain` (Node → Iran `ws`/`plain` carriers): validates real WebSocket `101` handshake on `CONTROL_PATH`.
  - `bh_tls` (Node → Iran Backhaul TLS/wssmux/wss): validates TLS + `/channel` responsiveness (accepts `101`/`400`/`401`/`403`/`426`, rejects `502`/`503`/`504`/reset/TLS errors).
  - `tcp` (Node → Iran `noise`, `frp/tcp`, `frp/websocket`, `backhaul/ws|wsmux`): TCP connect RTT probes.
  - `icmp` (Node → Iran UDP carriers `kcp`, `frp/kcp`, `frp/quic`): ICMP ping via `subprocess.run(..., shell=False)`.
  - Optional `--backends-json` checks every configured local inbound (`127.0.0.1:<inbound_port>`), and optional `--gre-iface` + `--gre-peer` checks GRE underlay RTT/loss.
  - Outputs compact JSON with `ok`, `verdict` (`healthy`, `degraded`, `open_no_http`, `failed`), `rtt_ms` (`min`/`avg`/`max`/`p95`), `jitter_ms`, `loss_pct`, `ok_count`, `count`, `detail`, `backends`, `gre`.

### 2.2 CLI Commands (`ratholectl test` & `ratholenode test`)

- **`ratholectl test <name> [--count N] [--json]`:** Read-only (no root mutation); inspects `$STATE` for `<name>`, picks `tls_direct` (when `.sni` set) or `http_ws`, attaches systemd service state, and prints `--json` (exit `0` so Hub always receives structured failure reasons) or human summary (`exit 1` on `ok == false`).
- **`ratholenode test [--count N] [--json]`:** Loads `node.env`, selects the active carrier probe mode (`TUNNEL`), enumerates `services.conf` + `bh-services.conf` backends, probes optional GRE underlay, and outputs structured JSON or human report.

### 2.3 Hub Backend (`hubcmds.py`, `hubdiag.py`, `hub.py`)

- **`hubcmds.py`:** Adds read-only `link_test` action (`RE_NAME`, `RE_COUNT` `1..20`); intentionally excluded from `WRITE_ACTIONS`.
- **`hubdiag.py`:**
  - `synthesize_link_test(node_name, iran_res, node_res=None, peer_name=None)` → diagnoses root cause (`listener_down`, `backend_down`, `carrier_unreachable`, `e2e_failed`, `degraded_link`, `healthy`).
  - `compute_fleet_drift(inventory, overviews, hub_version=None, now=None)` → computes deterministic drift items across 8 classes (`unreachable`, `version_skew`, `service_down`, `cert_expiring`, `orphan_iran_node`, `orphan_foreign_service`, `carrier_mismatch`/`profile_mismatch`/`protocol_mismatch`, `inbound_port_mismatch`). Adaptive `ws` ↔ `kcp` skew is downgraded to `info` severity with an adaptive-failover notice.
- **`hub.py`:**
  - Extracts `collect_server_overview(s)` shared by `/api/servers/<name>/overview` and `/api/fleet/drift`.
  - Adds `GET /api/fleet/drift` and `POST /api/servers/<name>/link-test` (both auth-protected).
  - Extends `mock_run()` for `ratholectl test` and `ratholenode test`.

### 2.4 Hub UI (`ui/i18n.js`, `ui/app.css`, `ui/app.js`)

- Dashboard: adds **Fleet Drift Check** button (`GET /api/fleet/drift`) and non-destructive `#driftpanel` with severity badges and direct navigation links.
- Service `⋯ → Health test` & Node page `Link Test`: runs bidirectional `POST /api/servers/<name>/link-test` and renders structured metrics modal (Iran→Node E2E + Node→Iran carrier + GRE underlay + local backend ports), transparently falling back to `doctor` if `404` or `unsupported`.
