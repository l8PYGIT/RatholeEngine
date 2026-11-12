# Changelog (English)

All notable changes are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/); versioning follows [SemVer](https://semver.org/).

---

## [Unreleased]

### Changed
- **Repository fully moved to `l8PYGIT/RatholeEngine`:** every `loopy-iri/tunnelplus` reference in code and docs now points at the new slug — the `install.sh` default (`RATHOLE_GH`), the `ratholeagent.py` download in `ratholectl`/`ratholenode`, the `gh_repo` default in `hub.py`, `tools/update-private.sh`, `tools/mkdocs_wiki_links.py`, and every install example in the README / `docs/` / wiki. The one-command install and the docs site now point at the current repository and install from its own releases.

## [2.0.3] - 2026-11-12

### Added
- **Static documentation website (MkDocs Material):** `mkdocs.yml` + Persian landing page `docs/index.md` + a wiki-link hook (`tools/mkdocs_wiki_links.py`) + custom styling; the output is fully offline (no CDN/Google Fonts), RTL, with built-in search and light/dark themes. Build/deploy guide and platform comparison (MkDocs Material, VitePress — what Marzban uses —, Docusaurus, Docsify) in `docs/website.md` / `docs/website.en.md`.
- **GitHub Pages deployment:** new `.github/workflows/docs.yml` builds the site from `docs/` and publishes it to Pages.
- **Real Hub screenshots (mock mode):** six 1440×900 images under `docs/assets/screenshots/` (dashboard, Iran page, node page, service controls, routing map, settings), used in the README, the wiki and the site landing page.

### Changed
- **Full documentation sync with v2.0.2:** README, `docs/` (fa/en), the wiki and `ratholehub/README.md` — removed wiring-board claims, documented service controls, carrier protocol labels, the REST Agent, private-repo installs, the FRP/GRE/FRP+GRE carriers, and refreshed examples.
- **AGENTS.md / CLAUDE.md:** updated the REST Agent role, independent carriers, the `/_rh/<hex>` control path and the wiki/doc index.

### Fixed
- **Node token/arguments after the `--` separator are preserved by `install.sh`.** Arguments placed after `--` (e.g. the node's `--token` and `--inbound-port`) were dropped while parsing; now every argument after `--` reaches `bootstrap.sh` untouched. Test: `tests/test_installer_tokens.py`.

## [2.0.2] - 2026-10-16

### Removed
- **Interactive Visual Wiring Board (`#/wiring`) and the Circuit Inspector HUD** were removed from the Hub UI. The legacy `#/wiring` URL silently falls back to the dashboard, and navigation is now Dashboard / Routing map / Audit / Settings. The routing map (`#/routing`) remains as a **read-only** topology view.

### Added
- **Service controls on every service row — on both the Iran and the node page:** **Carrier and protocol** (switch carrier/protocol), **Health test** (runs `doctor` and shows its output), **Create VLESS config** (builds and copies a `vless://` link after validating the UUID, port, path and public host), **Manage peer** (jump to the peer server page) and **Remove both ends** (delete from Iran plus `rm_svc`/`rm_bh_svc` on the node). For SNI/game services a hint points to the gaming-services section instead.

### Changed
- **Carriers report the actual protocol:** the carrier label now shows the protocol reported by the server — `FRP / TCP|KCP|QUIC|WEBSOCKET`, `FRP + GRE / <transport>`, `Backhaul / WS|WSMUX|WSS|WSSMUX`, `KCP / UDP · <profile>` — and `?` means the protocol was not reported. The `hub.py` parsers now return transport/profile; the label alone does not prove connectivity, the health test does.
- **Much smaller Hub UI:** `app.js` shrank by ~1047 lines and `app.css` by ~254 lines, with i18n keys replaced/updated accordingly.

## [2.0.1] - 2026-10-16

### Added
- **REST Agent with HTTPS support:** `ratholeagent.py` gained `--tls-cert`/`--tls-key` (and the `RATHOLE_AGENT_TLS_CERT`/`RATHOLE_AGENT_TLS_KEY` env vars) and serves HTTPS automatically when `/etc/rathole-agent/cert.pem` + `key.pem` exist; the Hub connects through an `HTTPSHandler`, and a self-signed cert is accepted only with `insecure_ssl` on the server record (`/etc/ratholehub/inventory.json`) or `RATHOLE_AGENT_INSECURE_SSL=1`.
- **Readiness/probe commands in the CLI and Hub:** `ratholectl frp ready <name>` checks with `ss` that the proxy is listening on `127.0.0.1:<port>`, and `ratholenode gre probe <peer_ip> [gre_name]` tests the GRE link with `ping -I`; the `frp_ready` and `gre_probe` actions were added to the Hub allow-list with regex validation.
- **GRE IP fields for REST API nodes:** the server IP and tunnel IP are editable in the Hub UI and auto-detected for Agent-managed nodes.
- **Automatic port on carrier switch and live badges:** the inbound port is read from the fresh Iran/node state instead of a default, the carrier badge is shown in the services table and node overview, and the single matching Iran node is auto-resolved.
- **Agent self-healing and multi-service FRP ports:** the agent fetches `ratholeagent.py` from raw GitHub (through the ghproxy mirrors) when it is missing, and each FRP service on a node keeps its own remote port.

### Fixed
- **Public IP routing and carrier synchronization between Iran and nodes:** connection/display paths now use the public IP instead of an internal address, and carrier selection is applied identically on both sides.
- **frpconnect and loopback:** `127.x`/`localhost`/`::1`/`0.0.0.0` addresses are replaced with the public IP, `inbound_port` is also read from the in-memory state, adaptive no longer overrides a manually selected carrier, and `doctor` warns when nothing is listening on the inbound port.
- **`doctor` and backhaul:** the backhaul probe is authorized with the token, and a 401 response is accepted as "alive".
- **FRP disconnect and 6-carrier sync:** the FRP disconnect was fixed and all six carriers are synchronized between Iran and the node; multi-lane status stays in sync and duplicate toasts were silenced.
- **Update and health check:** the install collision on `ratholeagent.py` in `update.sh` was fixed, and the node health check no longer breaks on an empty `services.conf`.
- **Agent install lifecycle:** `install-agent` is consistent (symlink/paths/unit), a `main`-source update fallback was added for private repos, and the agent token no longer appears in systemd units or startup logs (legacy units migrate to the protected token file).
- **Agent robustness and error messages:** the request body is drained on auth failure to avoid connection resets, and REST-agent connection errors plus service startup errors are reported with clearer messages.
- **Hub provisioning, transport lifecycle and private updates:** these three paths were repaired and covered by dedicated tests.
- **Node REST API and FRP/GRE/Backhaul controls:** audited and fixed, and Hub→node command dispatch was corrected.

## [2.0.0] - 2026-10-14

### Added
- **Interactive Visual Wiring Board (`#/wiring` / Patch Panel):** Datacenter-style 4-rack patch board (Ingress, Carriers, Inbounds, Outbounds) with drag-and-drop & click-to-wire patch cabling, animated SVG cubic Bézier curves, socket spark & puff animations, floating Circuit Inspector HUD with live ping and one-click V2Ray recipe copy, and Carrier Switcher Modal.
- **Standalone FRP Core (`fatedier/frp`):** Full reverse tunnel integration with TCP, KCP, QUIC, and WebSocket transport support. New commands: `ratholectl frp on/off/status/show` and `ratholenode frp on/off/status`.
- **Linux Kernel Layer 3 GRE Tunnel:** Direct kernel IP-in-IP tunnel (`ip tunnel`) with /30 subnet addressing (`10.10.10.0/30`), MTU 1476 optimization, and iptables TCPMSS clamping. New commands: `ratholectl gre on/off/status` and `ratholenode gre on/off/status`.
- **FRP + GRE Hybrid Carrier:** L3 kernel GRE network interface carrying nested FRP QUIC/KCP multiplexed streams for maximum censorship resistance.
- **Multi-Device Responsive Redesign:** 5-column bottom navigation bar on mobile/tablet viewports, safe-area offset for floating HUD inspector, and 1-column fallback grids for mobile displays.

### Fixed
- **Resolved Installer Freeze / Stalled Transfers under Iranian DPI:**
  - Added bounded speed-limits (`--speed-limit 1024 --speed-time 20` and `--connect-timeout 15`) across all `curl` download loops in `install.sh`, `bootstrap.sh`, `install-panel.sh`, `install-node.sh`, `common.sh`, `ratholectl`, `ratholenode`, and `hub.py`. Prevents indefinite hangs when DPI drops traffic after initial TCP connection.
  - Set `NEEDRESTART_MODE=a`, `NEEDRESTART_SUSPEND=1`, and `-o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"` across all `apt-get` calls to eliminate interactive restart prompts on Ubuntu 22.04 and 24.04.
  - Added multi-mirror fallback (including ghproxy mirrors) for rathole binary download in `install-node.sh`.
  - Hardened `test_tty_prompt.sh` regression harness to gracefully skip `setsid` when unavailable.

## [1.9.3] - 2026-08-19

### Changed
- **Maintenance release:** installation bundles and multi-architecture cores are rebuilt and published by the current Release workflow so stable assets come from the latest repository state.

## [1.9.2] - 2026-08-15

### Changed
- **Documentation sync:** guides now match the dual-core Backhaul lane, current CLI signatures, and the Hub UI released in 1.9.1.
- **Repository default:** installer, Hub, and documentation URLs now target `l8PYGIT/RatholeEngine`, so one-line installs and remote updates pull the correct Release assets.

## [1.9.1] - 2026-08-14

### Changed
- **Complete Hub UI rewrite:** responsive desktop/mobile layouts, light and dark themes, correct RTL/LTR navigation, consistent SVG icons, and clearer dashboard, server, settings, and activity-log views.
- **Accessibility:** semantic controls, associated form labels, visible focus, focus-trapped dialogs with Escape support, inline validation, and `prefers-reduced-motion` support.
- **No new dependency:** the Hub remains plain HTML/CSS/JavaScript served by the Python standard-library backend.

## [1.8.3] - 2026-08-07

### Fixed
- **State lock was held during user input (regression from v1.6.3).** `menu` (the default `ratholectl` command) and `init` both waited for user input while holding the global lock. This caused: (1) any other `ratholectl` call (e.g. a hub SSH action) to block for 30 seconds; (2) after that timeout, execution continued **without the lock**, bypassing the lost-update/TOCTOU protection the lock was built for. Fixed by releasing the lock before `read` and re-acquiring it after the answer. One fix in `rth_read` — all 25 prompts go through the same path. Test: `tests/test_lock_prompt.sh`.

## [1.8.2] - 2026-08-07

### Added
- **Pin a specific release version with a flag.** Previously the only way was `RATHOLE_RELEASE=v1.7.0 curl ... | sudo bash`, which doesn't work: the variable goes to `curl` and `sudo` strips it. Now `install.sh` accepts `--release <tag|latest|beta>` (and `--release=` form); it prompts if not provided (Enter = latest). The pin is forwarded to bootstrap so `--update` stays on the same version. `ratholectl update <tag>` / `ratholenode update <tag>` also accept a tag. Test: `tests/test_release_pin.sh`.

### Fixed
- **Install silently hung after option selection.** Two causes: (1) in `rth_with_lock`, `exec 9>"$RTH_LOCK" 2>/dev/null` without grouping made the stderr redirect permanent — all `err`/`die` messages were silently lost; (2) TTY was not forwarded to `ratholectl init` so domain prompts didn't work under `curl | bash`. Tests: `test_stderr_visible.sh`, `test_tty_prompt.sh`, `test_init_interactive.sh`.

## [1.8.1] - 2026-08-02

### Fixed
- **Existing nodes never received the uTLS core.** `install_backhaul` started with `[ -x "$bin" ] && return 0` — before checking whether the patched core was already installed. Any node that already had `/usr/local/bin/backhaul-client` silently kept the old binary without uTLS after update. Now the SHA256 of the core is checked first; no-op if identical, replaces if different. After update, re-run `ratholenode backhaul on ...` to apply (running binary is not replaced until service restart). Test: `tests/test_core_backhaul_patch.sh`.

## [1.8.0] - 2026-08-02

### Added
- **Custom backhaul core with Chrome TLS fingerprint (uTLS).** The upstream backhaul binary uses Go's `crypto/tls` which has its own JA3/JA4 fingerprint — DPI can distinguish a Go client from a browser even when the User-Agent is faked. Our patch replaces only the TLS layer. ALPN is intentionally limited to `http/1.1` (Chrome also advertises `h2`, which causes the server to negotiate HTTP/2 and break the HTTP/1.1 WebSocket Upgrade — caught in real e2e testing). The patched binary is preferred from the local bundle; falls back to upstream download only if absent.
- **Backhaul direct-IP with self-signed TLS.** `ratholectl backhaul on <port> wssmux <profile> direct_ip` — backhaul terminates TLS itself (nginx is not in the path) using the cert from `ratholectl ip-cert <IPv4>`. Previously direct-IP was unencrypted; now the token is not on the wire. Note: the client does not verify the cert (`InsecureSkipVerify`) — passive eavesdropping is prevented; active MITM is not. Both CLI and hub state this clearly.
- **License changed to AGPL-3.0-or-later** (previously MIT). Versions up to v1.7.0 remain under MIT. Practical note (AGPL §13): if you modify RatholeEngine and let others use it over a network (e.g. run a modified `ratholehub` for them), you must provide them the source of your version. See `NOTICE`.

### Fixed
- `tls`/`encrypted` in `status --json` and hub's `backhaul show` were hardcoded to the mode string — so direct-IP + `wssmux` was incorrectly reported as "unencrypted". Now uses the transport field. New `verified` field distinguishes "encrypted" from "cert-verified".

## [1.7.0] - 2026-08-02

### Fixed
- **Install hung silently for hours during init.** Two bugs: (1) `read -rp` on a non-terminal stdin that's not yet closed (slow/filtered curl|bash from inside Iran, SSH channel, hub) waits forever — and bash `read -p` only writes the prompt when stdin is a terminal, so the user saw nothing. (2) `[ -r /dev/tty ]` was used as "we have a TTY" indicator, which is always true (device node is always readable). Fix: all prompts go through a common helper that actually opens `/dev/tty` and has a time limit (`RTH_READ_TIMEOUT`, default 300s). Without TTY, the answer is always "no" (safe default). Test: `tests/test_tty_prompt.sh`.
- **`certbot` ran without a time limit during `init`** — while nginx was stopped. From inside Iran (ACME is often filtered/slow) it could hang for hours. Now bounded (`RATHOLE_CERTBOT_TIMEOUT`, 300s).
- **Install downloads hung on stalled TCP connections** — DPI establishes the connection then stalls the stream. `--connect-timeout` doesn't catch this. Added `--speed-limit`/`--speed-time` (slow-but-progressing transfers are not killed).

### Added
- **Tunnel over bare IP (no domain).** `ratholectl ip-cert <IPv4> [days]` creates a self-signed IP-SAN cert and makes it the `default_server` vhost — the main domain/cert is untouched. Includes `ip-cert-show` (print public cert for trusting on node) and `ip-cert-off`. The private key never leaves the Iran server.
- **`ratholenode set-main <server:port> [tls_hostname] [trusted_root]`** — atomically sets the dial endpoint, SNI/cert hostname, and trust root. The node can dial an IP but verify the cert with the correct hostname; certificate verification is never disabled.
- **`ratholenode status --json`** — transport, endpoint, SNI, TLS/encryption, service state as normalized JSON (consumed by hub, with fallback for older nodes).
- **Backhaul direct-IP mode** — `ratholectl backhaul on <port> <ws|wsmux> <profile> direct_ip` binds on `0.0.0.0` without nginx. Port 443 is rejected (conflicts with nginx). Warns that TLS is absent in this mode.

## [1.6.3] - 2026-07-31

### Fixed
- **Missing `state.json` after a failed jq write.** `state_set` didn't check jq's output and did `mv` unconditionally. With `set -uo pipefail` (intentionally not `-e`), a failed jq didn't abort — so a bad jq path, full disk, or half-written state silently replaced `state.json` with an empty file, wiping all nodes/tokens/ports. Now a failed jq or empty output is rejected before `mv`.
- **Lost lock in `rth_commit_config` on systems without `flock`** — `flock: command not found` went to stderr but the subshell returned rc=0, so the `|| return 1` never fired and config was written without the lock. Added a portable `mkdir`-based fallback.

## [1.6.0] - 2026-07

### Added
- **Hub UI rewrite** — UI moved out of the inline string in `hub.py` into `ratholehub/ui/` (`index.html`, `app.css`, `app.js`, `i18n.js`). Sidebar + hash-router, bilingual (Persian/English), responsive, smart auto-refresh (every 20s, active page only).
- **Security module `hubcmds.py`** — action→argv map and `RE_*` argument regexes extracted into a small standalone module for easier auditing.
- **Exclusive transport select per node** in hub UI — replaces five independent on/off switches with a single exclusive select (`ws`/`kcp`/`plain`/`noise`/`backhaul`) that coordinates both sides.
- **Proxy ingress** — `ratholectl proxy add <name> <http(s)://host:port>`: a `/<name>/` path on 443 that `proxy_pass`es to any upstream without going through rathole.
- **Port management section** in hub server page.

## [1.5.0] - 2026-07

### Added
- **Adaptive Failover** — `ratholenode adaptive on`: timer-driven probes classify the carrier (`dns_failed` / `tcp_timeout` / `tls_failed` / `ws_rejected` / `ws_timeout` / `healthy`) and auto-switch `ws` → `kcp` with threshold/hysteresis/cooldown. State sanitized: no token/key/WS_PATH in `adaptive-state.json`.
- **Secret WebSocket control path** — control channel moved from `/` to `/_rh/<32 hex>`. Only that exact path routes to rathole; all others keep fake-site behavior. `ratholectl control-path show/rotate`.
- **Direct-IP ingress** — `ratholectl direct on`: a plain HTTP port where node selection comes from a hidden header instead of URL path.
