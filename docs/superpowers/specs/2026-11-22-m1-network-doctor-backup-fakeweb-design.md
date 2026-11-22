# Milestone 1 (M1) Design Spec — Network, GRE, PROXY Protocol, Doctor, Backup & Deterministic Fakeweb

**Branch:** `feat/v2.2-backpack-upgrades`  
**Target Release:** `v2.2.0` (Milestone 1 of 7)

---

## 1. Scope

Milestone 1 delivers six high-value reliability, network-correctness, diagnostics, backup-safety, and stealth-camouflage upgrades across `common.sh`, `ratholectl`, `ratholenode`, `fakeweb.py`, `hubcmds.py`, installers/updaters, and CI:

1. **Kernel ephemeral port safety (`ip_local_port_range` + `ip_local_reserved_ports`)**
2. **GRE hardening & extensions (`gre_key`, `ip6gre`, `OUTPUT`+`FORWARD` MSS clamp, Proto 47 firewall rule, DF binary-search Auto-MTU)**
3. **Opt-in `PROXY Protocol` for `game` (SNI) and `FRP`**
4. **Actionable `doctor` diagnostics (concrete remediation hints, TLS cert expiry, token strength, carrier-aware node checks, watchdog/adaptive state, live `snd_mss` / kernel checks)**
5. **Safe recovery & offsite backups (`restore --test` dry-run + argv-only offsite backup hook without shell interpolation)**
6. **Per-install deterministic `fakeweb.py` decoy server (authentic Nginx signatures, `ETag`/`Last-Modified`, `304`/`206`/`404`/`405`)**

---

## 2. Component Designs & Interfaces

### 2.1 Sysctl Ephemeral Port Range & Reserved Ports (`common.sh`, `ratholectl`, `ratholenode`)

- **Problem:** Setting `net.ipv4.ip_local_port_range=1024 65535` lets kernel outbound sockets claim listening service ports (`2087`, `2333`, `3080`, `7000`, `8088`, `8089`, etc.) as ephemeral source ports, producing intermittent `address already in use` startup failures even when `ss -tlnp` shows nothing listening.
- **Changes:**
  - `apply_sysctl_tuning` in `rathole-manager/common.sh` sets `net.ipv4.ip_local_port_range=32768 60999` and supports `RTH_SYSCTL_FILE` override for tests.
  - New `apply_reserved_ports` in `common.sh` deduplicates and numerically sorts valid ports (`1..65535`) and writes `net.ipv4.ip_local_reserved_ports=<csv>` to `${RTH_RESERVED_SYSCTL_FILE:-/etc/sysctl.d/99-rathole-reserved-ports.conf}` (removing the file if empty) and applies `sysctl -w` best-effort.
  - `ratholectl`: `collect_reserved_ports` gathers all configured service/node/API ports from `state.json`. Called in `cmd_tune` and at the end of `regenerate`.
  - `ratholenode`: `collect_node_reserved_ports` gathers inbound ports from `services.conf`, `bh-services.conf`, and local KCP ports from `node.env` / `upstreams/*.env`. Called in `cmd_tune` and `cmd_apply`.

### 2.2 GRE Upgrades (`common.sh`, `ratholectl`, `ratholenode`, `hubcmds.py`)

- **Helpers in `common.sh`:** `rth_is_ipv4`, `rth_is_ipv6`, `rth_valid_ip`, `rth_valid_gre_key` (`0..4294967295`), `rth_valid_mtu` (`576..1500`).
- **`gre_setup_interface <name> <local_ip> <remote_ip> <tunnel_ip> [gre_key] [mtu]`:**
  - Backwards compatible with 4-argument callers.
  - Selects `gre` (`ip_gre`, `iptables`) vs `ip6gre` (`ip6_gre`, `ip6tables`) from `remote_ip` family.
  - Automatically computes default MTU from the outgoing route interface MTU minus GRE overhead (`24`/`28` for IPv4 without/with key; `44`/`48` for IPv6), unless explicit `mtu > 0` is given.
  - Supports `/30` (IPv4) or `/126` (IPv6) when no prefix is given on `tunnel_ip`.
  - Installs tagged (`--comment "rathole-gre-<name>"`) firewall rules:
    - `INPUT -p 47 -s <remote_ip> -j ACCEPT`
    - `mangle OUTPUT -o <name> ... TCPMSS --clamp-mss-to-pmtu`
    - `mangle FORWARD -o <name> ... TCPMSS --clamp-mss-to-pmtu`
- **`gre_teardown_interface <name>`:** Tears down the interface and sweeps all tagged `"rathole-gre-<name>"` rules from `iptables` and `ip6tables` using pure argv parsing (no `eval`), plus legacy untagged `POSTROUTING` cleanup.
- **`gre_probe_mtu <iface> <peer_tunnel_ip>`:** Verifies minimum `1280` MTU using DF `ping -M do`; if current interface MTU drops DF packets, binary-searches `[1280, cur_mtu]` and lowers interface MTU accordingly.
- **CLI & Hub:**
  - `ratholectl gre` & `ratholenode gre`: `on` supports positional `[key]` and `--key K` / `--mtu M`; adds `auto-mtu <peer_ip> [gre_name]` and (`ratholectl`) `probe <peer_ip> [gre_name]`.
  - `hubcmds.py`: `gre_on` accepts IPv4/IPv6 via `_valid_ip` and optional `gre_key` / `mtu`; adds `gre_probe` on Iran and `gre_auto_mtu` (in `WRITE_ACTIONS`) on both roles.

### 2.3 Opt-in PROXY Protocol (`ratholectl`, `ratholenode`, `hubcmds.py`)

- **Invariant:** Off by default everywhere so unconfigured backends never break; enabling prints an explicit warning to enable `acceptProxyProtocol` on the target Xray/backend first.
- **`game` (SNI):**
  - `ratholectl game proxy-protocol <on|off|status>` mutates `.game_proxy_protocol` in `state.json` and runs `regenerate`.
  - When enabled and `sni_count > 0`:
    - `gen_stream_conf` emits `proxy_protocol on;` in the `:443` stream server block.
    - `gen_nginx_conf` adds `proxy_protocol` to the internal `127.0.0.1:${internal}` L7 listener and adds `set_real_ip_from 127.0.0.1;` + `real_ip_header proxy_protocol;` in the corresponding server blocks.
- **`FRP`:**
  - `ratholectl frp proxy-protocol <v2|v1|off|status>` stores `.frp_proxy_protocol` in `state.json`.
  - `ratholenode frp proxy-protocol <v2|v1|off|status>` sets `FRP_PROXY_PROTOCOL` in `node.env` and regenerates/restarts `frpc` when active.
  - `gen_frp_client_toml` emits `transport.proxyProtocolVersion = "<v1|v2>"` on each `[[proxies]]`.
- **Hub (`hubcmds.py`):** Adds `game_proxy_protocol` (Iran) and `frp_proxy_protocol` (Iran & Node) to `build_*_cmd` and `WRITE_ACTIONS`.

### 2.4 Actionable `doctor` Upgrades (`common.sh`, `ratholectl`, `ratholenode`)

- Keep `check_active(){`, `check_listen(){`, and zero-`eval` invariant (`test_doctor_no_eval.sh`).
- `common.sh`:
  - `rth_cert_days_left <pem>`: returns days until expiration via `openssl x509 -enddate` + `python3`/`date`.
  - `rth_check_kernel_health <panel|node>`: checks `ip_local_port_range` start `>= 10000`, `bbr` congestion control, and established TCP `snd_mss` (`< 1300` triggers Path MTU warning).
- `ratholectl doctor`: prints `→ rah-e hal:` remediation hints beneath failures, checks TLS certificate expiry (`<= 0` FAIL, `<= 14` WARN) for primary and extra domains, warns on weak node tokens (`< 16` chars), checks GRE interface state if enabled, and runs `rth_check_kernel_health`.
- `ratholenode doctor`: prints remediation hints, checks the active carrier service according to `TUNNEL` (`ws`/`kcp`/`plain`/`noise`/`frp`) + `bh-services.conf` + `GRE_NAME`, checks `rathole-watchdog.timer` / `rathole-adaptive.timer`, and runs `rth_check_kernel_health`.

### 2.5 `restore --test` & Argv-Only Offsite Backup Hook (`common.sh`, `ratholectl`, `ratholenode`, `hubcmds.py`)

- **Security invariant:** Offsite hook configuration stores a JSON `{"argv": [...]}` array, requires `{}` placeholder in at least one argument, validates `argv[0]` against shell metacharacters/whitespace, and executes via `python3` `subprocess.run(expanded, shell=False, timeout=300)` — **never through a shell**.
- **Separate failure reporting:** Local archive creation and offsite copy are reported separately so operators know whether local disk or remote transfer failed.
- **CLI:**
  - `ratholectl backup offsite set <argv...> | show | off | test [file]` and `ratholectl backup [--offsite] [out]` (same on `ratholenode`).
  - `ratholectl restore --test <file>` and `ratholenode restore --test <file>`: runs full gzip/traversal/symlink validation into temp dir, prints a summary of what would be restored, warns on empty nodes/services or missing local cert files, and exits cleanly with zero mutation to live files or services.
- **Hub (`hubcmds.py`):** Adds read-only `restore_test` (with `RE_PATH`) and `backup_offsite_status` for both roles.

### 2.6 Per-Install Deterministic `fakeweb.py` (`fakeweb.py`, `common.sh`, `ratholectl`, `ratholenode`, installers/CI)

- Pure Python 3 stdlib HTTP server (`127.0.0.1:<port>`) replacing bare `python3 -m http.server`.
- Derives a persistent Nginx identity (`Server` banner, default page variant `1.18/1.22` vs `1.24/1.26`, fixed-anchor `Last-Modified`, and Nginx-formatted `ETag: "<mtime_hex>-<len_hex>"`) from SHA-256 of `--seed` or a dedicated persistent `--seed-file` (`$(dirname "$STATE")/fakeweb.seed` on Iran, `$(dirname "$ENV_FILE")/fakeweb.seed` on node, or fallback `/etc/rathole/fakeweb.seed`), keeping secret tokens untouched and the decoy identity immutable across node additions/rotations.
- Preserves custom user `index.html` if present (ignoring legacy `It works! Default web page.` placeholder).
- Handles `GET`/`HEAD` on `/` and `/index.html`, `If-None-Match` / `If-Modified-Since` → `304`, `Range` → `206` / `416`, unknown paths (including `/channel`) → authentic Nginx `404`, and non-GET/HEAD methods → Nginx `405`.
- Packaged and installed to `/usr/local/share/rathole/fakeweb.py` (`0755`) in `install-panel.sh`, `install-node.sh`, `update.sh`, `package.sh`, `tools/build_zip.py`, and compiled in `.github/workflows/ci.yml`.
