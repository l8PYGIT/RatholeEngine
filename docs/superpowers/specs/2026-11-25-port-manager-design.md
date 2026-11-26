# Design Spec: Port Manager (`مدیریت پورت‌ها`) — Raw L4 TCP/UDP Forwarding & Optional PROXY Protocol

**Date:** 2026-11-25  
**Scope:** Multi-protocol L4 public port forwarding without URL `path` or `SNI`, across all RatholeEngine carriers, with Guided Hub UI.

---

## 1. Motivation

Before Port Manager, RatholeEngine exposed user traffic in two ways:
1. **Path-based HTTP/WebSocket over TLS (`443`):** Requires WS/XHTTP/gRPC/SplitHTTP and nginx path routing (`/<name>`). Does not support `VLESS + TCP + REALITY + Vision`, raw `MTProto`, or arbitrary `UDP` protocols (`Hysteria2`, `TUIC`, `WireGuard`).
2. **Game / SNI mode (`443` L4 passthrough):** Moves Nginx L7 onto `internal_port` (`8443`) and requires a distinct DNS subdomain + TLS SNI per service.

**Goal:** Expose arbitrary TCP, UDP, and TCP+UDP (`both`) public ports on the Iran server forwarding directly to any foreign node inbound (`127.0.0.1:<inbound>`) **without `path`**, **without `SNI`**, and **with zero Nginx in the data path by default** — while retaining an optional per-rule Nginx `stream` `PROXY Protocol` toggle (isolated to that rule's port so `443` stays untouched).

---

## 2. Data Architecture & Carriers

### 2.1 Hybrid Data Path

- **Default Direct Mode (`proxy_protocol = false`, `local_port = null`):**
  ```
  Client ──(TCP/UDP :<public_port>)──▶ Tunnel Core (0.0.0.0:<public_port>) ──▶ Node Inbound (127.0.0.1:<inbound>)
  ```
  - Nginx is NOT in the user traffic path (tunnel survives nginx reload/downtime).
  - Supports **TCP**, **UDP**, and **TCP+UDP (`both`)**.

- **Optional PROXY Protocol Mode (`proxy_protocol = true`, TCP-only):**
  ```
  Client ──(TCP :<public_port>)──▶ Nginx stream { listen <pub>; proxy_protocol on; } ──▶ 127.0.0.1:<local_port> ──▶ Tunnel Core ──▶ Node Inbound
  ```
  - Allocates a dedicated loopback `local_port` (`21000+`) via `next_port`.
  - `gen_stream_conf()` emits an isolated `server { listen <pub>; ... }` block without creating or touching `map $ssl_preread_server_name` / `listen 443;` unless SNI/game nodes (`sni_count > 0`) exist.
  - Node Xray/backend inbound MUST have `acceptProxyProtocol: true`.

### 2.2 Carrier Mapping

| Carrier (`transport`) | Direct Bind | PP Mode (`local_port`) | UDP Support | Node Service Registry |
|-----------------------|-------------|------------------------|-------------|-----------------------|
| `ws` / `kcp` / `plain` (`server.toml`) | `0.0.0.0:<pub>` | `127.0.0.1:<loc>` | `tcp` / `udp` / `both` (`_udp` sibling) | `services.conf` (`add-svc`) |
| `noise` (`noise-server.toml`) | `0.0.0.0:<pub>` | `127.0.0.1:<loc>` | `tcp` / `udp` / `both` (`_udp` sibling) | `services.conf` (`add-svc`) |
| `backhaul` (`backhaul-server.toml`) | `"0.0.0.0:<pub>=<inb>"` | `"127.0.0.1:<loc>=<inb>"` | TCP-only (UDP rejected) | `bh-services.conf` (`backhaul add-svc`) |
| `frp` / `frp_gre` (`frps.toml` / `frpc.toml`) | `proxyBindAddr = "0.0.0.0"` + `remotePort = <pub>` | `remotePort = <loc>` | `tcp` / `udp` / `both` (`_udp` proxy) | `services.conf` (`add-svc` with `remote_port`) |
| `paqet` (`paqet/client.yaml`) | `listen: "0.0.0.0:<pub>"` | `listen: "127.0.0.1:<loc>"` | `tcp` / `udp` / `both` (dual entries) | None required (`paqet` forwards directly from Iran) |

---

## 3. State Schema & Collision Prevention

Stored lazily under `.ports[]` in `/etc/rathole-manager/state.json` (no migration required for existing installations):

```json
{
  "name": "p2083",
  "public_port": 2083,
  "inbound_port": 443,
  "proto": "tcp",
  "transport": "ws",
  "proxy_protocol": false,
  "local_port": null,
  "token": "<32-hex>",
  "node_server": "de01",
  "note": "VLESS REALITY Vision"
}
```

### Guardrails
1. **Batch Limit:** Single port (`2083`), comma list (`2053,2083,8443`), or contiguous range (`2080-2085`) — capped at **20 ports per batch** (`_port_expand_spec`, `RE_PORT_SPEC`, `pmParsePortSpec`).
2. **Protocol-Aware Collision Check (`check_public_port_free`):**
   - Port `22` blocked for all protocols; `80` and `443` blocked when overlapping `tcp` (`443/udp` permitted if `kcp.port != 443`).
   - Checks all system ports (`control_port`, `fake_port`, `sub_port`, `internal_port`, `hub_port`), active carrier listeners (`kcp`, `plain`, `direct`, `noise`, `backhaul`, `frp`), `.nodes[]` data/API ports, `.ports[]` public and PP local ports, and live kernel sockets via `ss -ltnH`/`ss -lunH`.
   - Allows `tcp` and `udp` rules to coexist on the same port number unless protocols overlap (`both` overlaps both).
3. **Firewall Safety (`_port_ufw_sync`):** Opens/closes `ufw allow <port>/tcp|udp`, never deleting a UFW rule while another `.ports[]` rule still shares that `(port, proto)`.
4. **Secret Handling:** `cmd_status --json`, `port ls --json`, and `port add --json` redact `.token`; only `ratholectl port show <name> --json` (exposed via Hub's `operate`-scoped `GET /api/servers/<iran>/portconnect/<rule>`) reveals the token for node syncing.

---

## 4. Hub Security & Guided UI

- **Strict Regex Allow-List (`hubcmds.py`):** `port_ls`, `port_map`, `port_show`, `port_add`, `port_edit`, `port_rm` + optional `proto` on `add_svc`; mutators registered in `WRITE_ACTIONS`; argv execution only (zero shell interpolation).
- **Guided UI (`ui/app.js`, `ui/app.css`, `ui/i18n.js`):**
  - 5th tab on Iran server page (`🔌 مدیریت پورت‌ها`), featuring a calm hero + `+ ساخت قانون پورت جدید` CTA, sliding-pill segmented switcher (`قوانین فوروارد` / `نقشهٔ پورت‌های اشغال‌شده` / `پورت‌های سیستم`), live collision probe, and `<dialog>` composer with live 4-hop pipeline preview + conditional `acceptProxyProtocol` warning + automatic two-sided synchronization.
