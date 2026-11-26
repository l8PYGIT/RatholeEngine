# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What this is

`rathole-manager` is a multi-location reverse-tunnel system built on **rathole + Nginx**. A single Iran server (behind one domain, one cert, one port 443) fronts many foreign "nodes" that connect back via reverse tunnel. User traffic is routed to nodes **by URL path** (`map $uri $backend_port` in nginx). The primary goal is censorship-resistant tunneling for Iran; almost all code comments and log strings are Persian transliterated into Latin ("Finglish", e.g. `tvlid khodkar` = auto-generate). Match that style when editing.

The repo root holds packaging/bootstrap scripts; the actual product lives in `rathole-manager/`.

## Three roles + the REST Agent

The system has three runtime roles plus an optional management daemon. Read the file for the role you're touching:

- **Iran panel** → `rathole-manager/ratholectl` (bash). Runs the rathole **server** + nginx. Owns node inventory. Generates `/etc/rathole/server.toml` and `/etc/nginx/conf.d/rathole.conf`.
- **Foreign node** → `rathole-manager/ratholenode` (bash). Runs the rathole **client**. Generates `/etc/rathole/client.toml`.
- **Hub** → `rathole-manager/ratholehub/hub.py` (Python 3, **stdlib only, no pip**). Central web panel that drives many Iran servers + nodes over SSH, the REST Agent, **or** Reverse WebSocket (`reverse_ws` via `/hub/ws/agent` & `/ws/agent`). Listens on `127.0.0.1` (fronted by nginx under `/hub/`).
- **REST & Reverse WS Agent** → `rathole-manager/ratholeagent.py` (`AGENT_VERSION = "2.0.0"`, Python 3 stdlib only + `rathole-manager/wsutil.py`; systemd `rathole-agent.service`; default REST `:8089` or outbound `--reverse <ws_url> --name <name>`). Supports direct token-authenticated `GET /api/ping` and `POST /api/exec` (`transport: "api"`), or persistent outbound RFC 6455 WebSocket connections to Hub (`transport: "reverse_ws"`) with zero open inbound ports (`--insecure-ssl`, `--proxy`). Installed by `install-agent.sh` or `ratholectl agent on|reverse` / `ratholenode agent on|reverse`.

`rathole-manager/common.sh` is sourced by both bash tools (colors/logging, `kcp_profile`, `install_kcptun`, `backhaul_mux_profile`, `backhaul_client_transport`, `install_backhaul`, `install_frp`, `frp_systemd_unit`, `gre_setup_interface`, `gre_teardown_interface`, `detect_ip`, `apply_sysctl_tuning`, `fakeweb_service`).

## Central design principle: state → regenerate → hot-reload

Every mutation follows the same pattern — **never hand-edit the generated configs**; change state and regenerate:

- **ratholectl**: state is `/etc/rathole-manager/state.json` (jq-manipulated via `state_set`/`s_get`). Commands mutate state, then call `regenerate()` → `gen_server_toml()` + `gen_nginx_conf()` → `nginx -t` → reload. Configs are written **in place (preserving inode)** so rathole's `config_watcher` hot-reloads without dropping active tunnels. `regenerate` keeps a `.rathole-good.bak` and auto-reverts nginx if `nginx -t` fails.
- **ratholenode**: base state is `/etc/rathole/node.env`; `/etc/rathole/services.conf` owns the rathole lane and `/etc/rathole/bh-services.conf` owns the Backhaul lane. `gen_client()` and `gen_backhaul_client_toml()` build separate configs; both clients can run together for different services.

## Transport modes (the core complexity)

The rathole lane has four carriers (websocket, kcp, plain, noise). Beside it run **independent lanes/cores**: Backhaul (SMUX), FRP, GRE (L3), and the FRP+GRE hybrid. Moving a service between lanes keeps its public path and Iran-side port stable; each Iran path belongs to exactly one lane. Key invariant for the default path: **TLS is terminated only by nginx** — rathole server transport is always `tls = false`; the default client uses `tls = true` over websocket to nginx/443.

- **websocket + TLS** (default): client connects `wss://domain:443`, nginx splits root `/` between the fake site and the rathole control channel using `$http_upgrade`. The control path is configurable in this repo's patched core — `control_path` (`/_rh/<32 hex>`, `ratholectl control-path rotate`) — with `/` kept as the fallback for nodes that have not been migrated yet.
- **kcp** (`cmd_kcp` both sides): parallel UDP+FEC path via kcptun for lossy links (TCP-over-TCP mitigation). Additive — doesn't touch server/nginx/443. Profiles (`balanced`/`lossy`/`aggressive`) must match on both ends; defined in `common.sh:kcp_profile`. Multi-Iran nodes run independent kcp per upstream (`rathole-kcp-up-<id>`, local ports from 29901).
- **plain** (`cmd_plain` both sides): no-TLS websocket to a separate HTTP listener port (default 8880). Lighter, unencrypted tunnel path.
- **backhaul** (`cmd_backhaul` both sides, `gen_backhaul_server_toml`): a **separate Go core** (`Musixal/Backhaul`) beside rathole that multiplexes many user connections onto one stream via **SMUX** — for busy/lossy links where rathole has no mux. `backhaul-server` listens on `127.0.0.1:<backhaul_port>` (default 3080) and nginx proxies the **hardcoded** `/channel` (control) and `/tunnel` (data) paths to it on the same 443, so single-port/single-domain holds. Three invariants to preserve:
  1. **Server transport is always the non-TLS variant** (`ws`/`wsmux`) and the client always the TLS one (`wss`/`wssmux`) — same rule as rathole; `backhaul_client_transport` maps between them and both sides reject the wrong variant. `tcpmux` cannot traverse the L7 nginx at all.
  2. On Iran, `backhaul` remains the node record's `.transport` so `gen_server_toml` skips that service and avoids a duplicate local bind. On the foreign node, Backhaul is an independent lane: `ratholenode backhaul on` keeps `rathole-client` running when `services.conf` has entries; Backhaul services live in `bh-services.conf`.
  3. **Port mapping is `"127.0.0.1:<iran_port>=<node_inbound_port>"`**, keeping the port the nginx `map $uri` points at unchanged. Each Iran path belongs to one lane only; the mux profile must match on both ends (`mux_con` server-only, `connection_pool` client-only).

- **frp** (`cmd_frp` both sides, `install_frp` in `common.sh`): a standalone reverse-tunnel core (`fatedier/frp`, frps on Iran / frpc on the node) with transports `tcp|kcp|quic|websocket`, shared token auth (default listen port 7000). Adds a second tunnel core beside rathole; does not change the 443/nginx contract.
- **gre** (`cmd_gre` both sides, `gre_setup_interface`/`gre_teardown_interface`): Linux kernel L3 point-to-point `ip tunnel` on a /30 (`10.10.10.0/30`), MTU 1476 with TCPMSS clamping, default interface `gre1`. No userspace daemon; used as an L3 underlay.
- **frp + gre** (`frp_gre`): hybrid carrier — FRP's multiplexed stream (tcp/kcp/quic/ws) carried over the GRE L3 link, selected per service like any other carrier.
- **paqet** (`cmd_paqet` both sides, `install_paqet` in `common.sh`): standalone Direct PCK raw TCP+KCP core (`hanselime/paqet`, `CAP_NET_RAW` + `iptables RAW NOTRACK`) — foreign node runs `paqet server` (`ratholenode paqet on`), Iran runs `paqet client` (`ratholectl paqet on` + `paqet node <name> on`) forwarding data ports directly without TLS handshake; `gen_server_toml` skips `paqet` nodes.
- **Ingress & Managed Edge modes (NOT tunnel carriers):** **Managed Xray** (`ratholenode xray setup|status|uri|off`, `rth_xray_scan_cover` TLS 1.3 + ALPN `h2` Cover Scanner) manages `VLESS+REALITY+Vision` and `VLESS+XHTTP` inbounds on nodes with optional `acceptProxyProtocol`. **game / SNI** (`ratholectl game`, `gen_stream_conf`) — when any node has an `sni`, port 443 switches to nginx **stream/SNI** mode (L4 passthrough) and the L7 path/WS vhost moves to an internal port (`internal_port`, default 8443); TLS for game traffic terminates on the **node** (real cert, VLESS+TLS+Vision), which is why `gen_nginx_conf` branches on `sni_count`. **direct-IP** (`cmd_direct`, hidden header e.g. `X-Cdn-Id`), **proxy** (`cmd_proxy`, non-tunnel reverse proxy), and **fakeweb** (`fakeweb_service`) are likewise ingress, not carriers.

## Path == node name == nginx map == Xray inbound

A node's `name` is simultaneously its URL path, its nginx `map` entry, and the Xray inbound path on the node. These three must stay identical. Each node has a data service; adding `--api-port` also creates a `<name>_api` service (bound to `127.0.0.1`) for panel↔node management over the tunnel.

## Hub (hub.py) specifics

- Stdlib HTTP server split into `hub.py` (router/state/SSH), `hubcmds.py` (validated action→argv map), and static assets under `ui/` (`index.html`, `app.css`, `app.js`, `i18n.js`). `Handler` is the API/router; `main()` serves `ThreadingHTTPServer`.
- **Security-critical:** it never runs raw strings on servers. `build_iran_cmd` / `build_node_cmd` map an `action` + validated args (via the `RE_*` regexes) to an **argv list**, executed over SSH with each arg passed separately (`run_on_server` → `_ssh_base`), over direct HTTP(S) `/api/exec` for `transport: "api"` (`run_on_agent`), or over an active RFC 6455 WebSocket session on `/hub/ws/agent` / `/ws/agent` for `transport: "reverse_ws"` (`run_on_reverse_agent`). When adding a server action, add it to the right `build_*_cmd` **and** the allow-list of actions (`WRITE_ACTIONS` for mutators, including `bench_apply`/`bench_confirm`/`bench_rollback`), and validate every arg with a regex — do not interpolate user input into a shell string. The agent enforces its own `ALLOWED_BINARIES` allow-list and 1 MiB HTTP / 4 MiB WS frame caps; HTTPS self-signed certs use `insecure_ssl` / `RATHOLE_AGENT_INSECURE_SSL=1` (or `--insecure-ssl` on the `reverse_ws` client). Tuner profile application in `_apply_tuner_side` uses two-phase dead-man confirmation (`bench apply --confirm-ttl 45` + `bench confirm <id>`) and rolls back Iran immediately if Node fails confirmation.
- **The hub UI has no wiring/patch-board page.** v2.0.2 removed `#/wiring`; v2.0.4 puts a **per-node carrier `<select>`** back in the Iran page row (`iranNodeCarrierSel` → `setIranNodeCarrier`): one confirm, then it applies the carrier on **both** sides through `configureServiceCarrier`, keeping the existing inbound port, and reverts the select if the node-side sync fails; `frp`/`gre`/`frp_gre` open the modal instead. The five service actions (carrier & protocol, health test, VLESS-config copy, manage peer, remove both ends) sit behind a compact `⋯` menu on both the Iran and the node page (`serviceMenu()`), so rows stay single-line. Labels show the reported protocol, e.g. `FRP / QUIC`, `Backhaul / WSMUX`; `?` means not reported. v2.4.0 adds `reverse_ws` connection onboarding (`buildReverseWsUrl`, `showReverseSetupModal`, `convertServerToReverseWs` on offline REST servers, online/waiting status badges, `rotate_token`). v2.5.0 adds the **Guided Port Manager** (`ratholectl port` for direct L4 TCP/UDP/`both` forwarding without path/SNI/Nginx or with opt-in per-rule `PROXY Protocol`, `tab_ports` 5th Iran tab, `port_*` in `hubcmds.py` / `WRITE_ACTIONS`, and `GET /api/servers/<name>/portconnect/<rule>`). Routes: `#/dashboard`, `#/server/<name>`, `#/tuner`, `#/routing` (read-only topology), `#/audit`, `#/settings`.
- **Private GitHub repos:** `install.sh --token`/`-t` (or `RATHOLE_GH_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN`) downloads private raw content / the API archive and skips public ghproxy mirrors; `tools/update-private.sh` updates an installed server from a private repo (release assets or `main` source).
- `deploy_to_server` (the hub "update" button) fetches the latest Release `install.sh` **on the server itself** (over SSH, via the ghproxy mirror loop) and runs it with `--update` — so servers pull from GitHub and no longer depend on the hub's local `bundle_dir` being fresh. The repo slug comes from config `gh_repo` (default `l8PYGIT/RatholeEngine`, validated by `RE_SLUG`); the remote command is a fixed `bash -c` script with only that validated slug interpolated. `provision_server` bootstraps SSH key auth.

## Commands

There is no build step (bash + stdlib Python). Common tasks:

```bash
# Test ratholectl end-to-end WITHOUT root/systemd/nginx (sandboxed; stubs need_root/nginx/systemctl):
bash rathole-manager/test-harness.sh
#   NOTE: it hardcodes BASE=/mnt/d/... (WSL path) and needs a `jq-linux` binary beside the scripts.

# Run the hub locally with mocked SSH (no real servers touched):
RATHOLEHUB_MOCK=1 RATHOLEHUB_CONF=/tmp/hub-conf.json RATHOLEHUB_INV=/tmp/hub-inv.json \
  python3 rathole-manager/ratholehub/hub.py        # then open http://127.0.0.1:8088
#   Env overrides: RATHOLEHUB_HOST, RATHOLEHUB_PORT, RATHOLEHUB_CONF, RATHOLEHUB_INV, RATHOLEHUB_MOCK.

# Build the distributable zip (LF endings, forward-slash paths — do NOT use Windows Compress-Archive):
bash package.sh                                     # → rathole-manager.zip (bundles rathole-manager/ + docs/; falls back to tar.gz)

# One-command install from GitHub (fetches the latest Release bundle, then runs bootstrap):
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --panel --domain ... --fullchain ... --key ...
#   install.sh: defaults to l8PYGIT/RatholeEngine; RATHOLE_GH="owner/repo" overrides the repo slug; RATHOLE_RELEASE="vX" pins a version.

# Local install on a fresh server (no download; bundle already present):
sudo bash bootstrap.sh                              # interactive; asks panel/node/update/rollback
sudo bash bootstrap.sh --local ./rathole-manager.zip --panel --domain ... --fullchain ... --key ...
```

## Update, backup & rollback

`update.sh` is the safe upgrade path (auto-detects panel/node/hub). Before touching anything it takes a **full snapshot** (CLI + configs + systemd units, per role) into `/var/backups/rathole-manager/pre-update-<ts>/` (`manifest.txt` + `backup.tar.gz`), applies the update, runs a per-role **health check** (`rathole-server`/`rathole-client`/`ratholehub` active + `nginx -t`), and **auto-rolls-back** to the snapshot on failure. Retention = last 7 (env `RATHOLE_BACKUP_RETENTION`).

- **From the server itself:** `ratholectl update` / `ratholenode update` (new subcommands) download the latest Release `install.sh` from GitHub — through the ghproxy mirror loop so it works from inside Iran — and run it with `--update` (which reaches this same `update.sh` via `bootstrap.sh --local`). The hub "update" button (`deploy_to_server`) does the identical thing remotely over SSH. Slug from `RATHOLE_GH` (default `l8PYGIT/RatholeEngine`), version from `RATHOLE_RELEASE` (default `latest`).

- Manual: `update.sh --list-backups`, `update.sh --rollback [<ts>]`, `update.sh --no-rollback`. `bootstrap.sh` forwards `--rollback`/`--list-backups` (and menu entries 5/6) to `update.sh`, using a local `update.sh` without re-downloading when possible.
- This complements the narrower `.rathole-good.bak` (nginx rollback inside `regenerate`) and `ratholectl backup`/`ratholenode backup` (state-only tarballs). The rathole binary is not changed by `update.sh`, so it is intentionally excluded from snapshots.

Installers/lifecycle (run on the target server, all need root): `rathole-manager/install-panel.sh`, `install-node.sh`, `ratholehub/install-hub.sh`, `update.sh` (snapshot + upgrade + health-check + rollback; also finishes partial installs), `uninstall-panel.sh`, `uninstall-node.sh`. One-command entry from GitHub: root `install.sh` (curl-piped) → downloads the Release bundle → `bootstrap.sh`.

CI/release: `.github/workflows/ci.yml` (shellcheck + `bash -n` + `py_compile` on push/PR) and `.github/workflows/release.yml` (on tag `v*`: runs `package.sh`, uploads `rathole-manager.zip` + `bootstrap.sh` + `install.sh` as Release assets — the exact assets `install.sh` fetches from `releases/latest/download`).

## Editing conventions

- **Bash:** these scripts intentionally use `set -uo pipefail` (not `-e`) — the `jq | while read` pattern returns nonzero and would abort under `-e`; errors are handled explicitly via `die`. Keep that. Preserve in-place config writes (inode preservation) so hot-reload keeps working. Temp files go through `rth_mktemp`/`rth_mktempd` (auto-cleaned via trap).
- **Windows/line-endings:** this repo lives on a Windows drive. Scripts must ship with **LF** endings and be executable; `package.sh`/`update.sh`/`bootstrap.sh` all run `sed -i 's/\r$//'` defensively. Don't introduce CRLF.
- **Secrets:** certs/keys, `state.json`, `inventory.json`, `node.env`, `services.conf`, and `config.json` are gitignored and must never be committed. (Note: `fullchain.pem` currently sits at repo root and is gitignored — leave it out of any bundle.)

## Reference docs

Documentation lives in `docs/` (Persian, except the root README). Diagrams (SVG/PNG) are in `docs/assets/`.

- `README.md` (repo root) — GitHub landing page, **bilingual** (English + Persian summary). Embeds `docs/assets/architecture.svg` and `transport-modes.svg`.
- `docs/README.fa.md` — full CLI reference and install flows (Persian; was `rathole-manager/README.md`).
- `docs/install-manual.md` / `docs/install-manual.fa.md` — full **manual** install walkthrough (English + Persian): Iran panel + Pasargad Xray/user config + foreign nodes + hub, step by step, mirroring exactly what `install-panel.sh`/`install-node.sh`/`install-hub.sh`/`ratholectl init` do.
- `docs/architecture.md` — three roles + REST / Reverse WS Agent + independent lanes, and the state→regenerate→reload principle (embeds `architecture.svg`, `state-regenerate-reload.svg`).
- `docs/transport-modes.md` — every tunnel carrier (ws/kcp/plain/noise, Backhaul SMUX, FRP, GRE, FRP+GRE) plus ingress modes game/SNI, direct-IP, proxy (embeds `transport-modes.svg`).
- `docs/traffic-flow.md` — packet path layer-by-layer per lane (Mermaid + `assets/*.svg`; was `TRAFFIC-FLOW.md`).
- `docs/hub.md` — hub web panel / service controls / REST API + REST & Reverse WS Agent (`reverse_ws`, `/hub/ws/agent`) / security model (embeds `hub-architecture.svg`; mirrors `rathole-manager/ratholehub/README.md`).
- `docs/performance.md` — `rathole-tuner` (two-phase `--confirm-ttl` Watchdog) & tuning beyond the tunnel (BBR, kcp profiles, FRP/GRE/Backhaul knobs, non-tunnel bottlenecks; was `PERFORMANCE-GUIDE.md`).
- `docs/amneziawg-reverse.md` — a separate AmneziaWG reverse-tunnel design (not part of the rathole flow; was `AMNEZIAWG-REVERSE.md`).
- `docs/wiki/` — GitHub-wiki source: `Home.md`, `Getting-Started.md`, `CLI-Reference.md`, `Hub-Management.md`, `Troubleshooting.md`, `Workflow-Guides.md`, `Adaptive-Filtering-Guide.md`, `_Sidebar.md` (Persian, wiki-style `](Page)` links). Keep it in sync with `docs/` when behaviour changes.
- `rathole-multilocation-pasargad.md` (repo root) — original detailed design/troubleshooting doc.

Docs are versioned with the product: bump user-facing version references when a release is tagged (`MANAGER_VERSION` in `rathole-manager/common.sh`), add a CHANGELOG section, and check the README/docs/wiki for claims that a release invalidated (the v2.0.2 removal of the wiring board is the precedent).

Three hand-authored diagrams are new: `docs/assets/transport-modes.svg`, `hub-architecture.svg`, `state-regenerate-reload.svg`. All diagrams share one visual style (white bg, dark title banner, per-zone pastel boxes, `#334155` data-path arrows / `#9333ea` dashed reverse-tunnel arrows, Segoe UI font). Match it when adding diagrams. `package.sh` bundles `docs/` alongside `rathole-manager/`.
