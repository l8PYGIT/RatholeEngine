# Milestone 7 Design Spec: `paqet` (Direct PCK), Managed `Xray` (`REALITY`/`XHTTP` + Cover Scanner) & v2.2.0 Release

**Date:** 2026-11-24
**Branch:** `feat/v2.2-backpack-upgrades` -> `main` (`v2.2.0`)
**Scope:** Raw-packet KCP carrier via `hanselime/paqet`, Managed `XTLS/Xray-core` (`VLESS+REALITY+Vision` and `VLESS+XHTTP+TLS`) with opt-in PROXY Protocol and TLS 1.3 / HTTP/2 Cover Site Scanner, Hub controls, full docs/wiki/`CHANGELOG.md` sync, `v2.2.0` bump, fast-forward merge, tag `v2.2.0`, and push to `l8pygit`.

---

## 1. `paqet` (Direct PCK) Carrier

For heavily censored networks where stateful L4 middleboxes throttle or reset standard kernel TCP/UDP flows, `hanselime/paqet` transports encrypted KCP streams inside crafted raw TCP packets (`pcap`/raw sockets) while exempting those packets from host kernel conntrack & RST interference via `iptables`.

- **Architecture Preservation (Single-Port `:443` Iran Edge):**
  - **Foreign Node (`ratholenode paqet on ...`):** Runs `paqet-server` (`role: "server"`, `listen.addr: ":<port>"` default `9999`) with shared KCP encryption (`block: aes-128-gcm`, `mode: fast`, `key`). No Nginx ports touched.
  - **Iran Panel (`ratholectl paqet on ...` + `ratholectl paqet node <name> on`):** Runs `paqet-client` (`role: "client"`) forwarding `127.0.0.1:<node_iran_port>` -> `127.0.0.1:<inbound_port>` over the encrypted raw-packet KCP session. Services with `.transport == "paqet"` are omitted from `/etc/rathole/server.toml` (just like `noise`/`backhaul`/`frp`) so `:443` `map $uri $backend_port` routes seamlessly without duplicate port binds.
- **Networking & `iptables` Hygiene:**
  - `paqet_detect_net` inspects `ip -4 route show default` and `ip -4 neigh show` to auto-detect `iface`, `local_ip`, and `router_mac` (all overridable via `--iface`, `--local-ip`, `--router-mac`).
  - `paqet_iptables_apply` / `paqet_iptables_remove` attach comment-tagged rules (`rathole-paqet-<role>-<port>`) in `raw PREROUTING`/`OUTPUT` (`CT --notrack`) and `mangle OUTPUT` (`--tcp-flags RST RST -j DROP`), removed cleanly on `off` (`--skip-iptables` skips kernel mutation in unprivileged containers/tests).
  - Hardened systemd units grant `CAP_NET_RAW` + `CAP_NET_ADMIN` cleanly without running ad-hoc scripts.

---

## 2. Managed `Xray` (`XTLS/Xray-core`) & Cover Site Scanner

Provides turnkey backend inbound provisioning on foreign nodes (matching the ports registered in Iran `map $uri`) plus a zero-dependency TLS 1.3 / ALPN Cover Site Scanner usable on both Iran and foreign nodes.

- **`rth_xray_scan_cover` (`ratholectl xray scan` & `ratholenode xray scan`):**
  - Pure Python 3 stdlib concurrent scanner (`ThreadPoolExecutor`) probing candidate domains over TCP + TLS with ALPN `["h2", "http/1.1"]`.
  - Ranks candidates requiring `TLSv1.3` + valid certificate chain, preferring `h2` ALPN and lowest `rtt_ms`, outputting structured JSON or aligned table.
- **`ratholenode xray setup <reality|xhttp>`:**
  - **`reality`:** Generates `VLESS + Flow xtls-rprx-vision + REALITY` (`/etc/xray/config.json` `0600`), auto-generating UUIDv4, 16-hex shortId, and X25519 keypair (`xray x25519` or pure OpenSSL/stdlib fallback via `rth_xray_gen_x25519`). Defaults `dest=www.microsoft.com:443`.
  - **`xhttp`:** Generates `VLESS + XHTTP` (`/etc/xray/config.json` `0600`) with configurable `--path`, `--mode` (`auto|packet-up|stream-up|stream-one`), `--host`, and optional `--tls --cert ... --key ...`.
  - **Opt-in PROXY Protocol:** `--proxy-protocol` enables `acceptProxyProtocol: true` in `streamSettings.sockopt` so `frp` / `game` SNI real client IP preservation works out of the box.
  - Validates JSON (`python3 -m json.tool` + `xray run -test -c`) before committing and starting `rathole-xray.service`, never prints `privateKey` in `status`, and formats shareable URIs via `ratholenode xray uri`.

---

## 3. Hub Integration, Security & v2.2.0 Release

- Strict allow-listed `hubcmds.py` mappings (`RE_UUID`, `RE_MAC`, `RE_PAQET_MODE`, `RE_PAQET_BLOCK`, `RE_XRAY_MODE`, `RE_XHTTP_MODE`, `RE_HEX_SID`, `RE_DOMAINS_CSV`), read-only vs `WRITE_ACTIONS` separation, `rth_redact` + `_redact_cmd_for_audit` secret masking, Hub mock responses, `GET /api/servers/<name>/paqetconnect`, and UI modals in `app.js`/`i18n.js`.
- Version bump to `MANAGER_VERSION="2.2.0"`, full `CHANGELOG.md` v2.2.0 release notes, synced README / `docs/` / `docs/wiki/`, full Windows + WSL test suite pass, clean fast-forward merge to `main`, annotated tag `v2.2.0`, and push to `l8pygit`.
