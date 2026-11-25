# Architecture — Three Roles and the Central Design Principle

`rathole-manager` is a multi-location reverse-tunnel system built on **rathole + Nginx**. A single Iran server — behind one domain, one certificate, one port 443 — fronts many foreign "nodes" that connect back over a reverse tunnel. User traffic is routed to nodes **by URL path** (`map $uri $backend_port` in nginx).

![Architecture overview](assets/architecture.svg)

*Everything on one port/domain behind Nginx; foreign nodes connect to the Iran server via reverse tunnel.*

---

## Three Roles, Three Programs

| Role | Program | Responsibility |
|------|---------|----------------|
| **Iran panel** | [`ratholectl`](../rathole-manager/ratholectl) (bash) | rathole **server** + nginx. Owns node inventory. Generates `server.toml` + `rathole.conf`. |
| **Foreign node** | [`ratholenode`](../rathole-manager/ratholenode) (bash) | rathole **client**. Generates `client.toml`. |
| **Hub** | [`ratholehub/hub.py`](../rathole-manager/ratholehub/hub.py) (Python, stdlib only) | Central web panel driving multiple Iran servers/nodes over SSH, direct REST Agent, or Reverse WS (`wsutil.py`). Details: [`hub.en.md`](hub.en.md). |
| **REST / Reverse WS Agent** (optional) | [`ratholeagent.py`](../rathole-manager/ratholeagent.py) + [`wsutil.py`](../rathole-manager/wsutil.py) (Python, stdlib only; unit `rathole-agent.service`) | Dual-mode daemon on an Iran server/node for SSH-free management (direct REST `:8089` or outbound Reverse WebSocket to `/hub/ws/agent`). Details: [`hub.en.md`](hub.en.md). |

`common.sh` is sourced by both bash tools (colors/logging, `kcp_profile`, `install_kcptun`, `backhaul_mux_profile`, `backhaul_client_transport`, `install_backhaul`, `install_frp`, `frp_systemd_unit`, `gre_setup_interface`, `gre_teardown_interface`, `apply_sysctl_tuning`, `fakeweb_service`).

---

## Management Plane: SSH, REST Agent, or Reverse WS

The hub has three ways to run commands on a server; each server record's `transport` field selects one:

- **`transport: "ssh"` (default):** SSH key auth; the command runs as an argv list with every argument passed separately.
- **`transport: "api"`:** the hub sends the request to the server's REST Agent — `POST <api_url>/api/exec` with body `{"cmd":[...], "timeout": N}` and header `Authorization: Bearer <api_token>`. `GET /api/ping` is public and returns `{ok, role, version: "2.0.0", hostname}`.
- **`transport: "reverse_ws"` (`v2.4.0`):** for filtered or NAT-bound servers where port `8089` is unreachable, `ratholeagent.py` dials outbound over RFC 6455 WebSocket (`wsutil.py`) to `GET /hub/ws/agent` (behind Nginx TLS `:443`) or `/ws/agent` — zero open inbound ports required on the target, with `--insecure-ssl` and HTTP `CONNECT` proxy support.
- **Security:** on all three paths the hub never runs raw shell strings; `hubcmds.build_iran_cmd`/`build_node_cmd` map an action + regex-validated args (`RE_*`) to an argv list. The agent only accepts argv (`ALLOWED_BINARIES` allow-list, payload capped at 1 MiB for HTTP / 4 MiB frames for WebSocket, constant-time token compare).
- **HTTPS & daemon hardening:** direct REST listens on HTTP at `0.0.0.0:8089` by default (`request_queue_size=64` + TCP keepalive); `--tls-cert`/`--tls-key` switch it to HTTPS. Self-signed certs require `insecure_ssl: true` (or `RATHOLE_AGENT_INSECURE_SSL=1`) in `api` mode, or `--insecure-ssl` on the agent CLI in `reverse_ws` mode. The `rathole-agent.service` unit is hardened with `StartLimitIntervalSec=0`, `LimitNOFILE=65535`, `KillMode=process`, and cgroup-safe self-restarts via `_schedule_agent_restart()` in `update.sh`.
- **Install:** `install-agent.sh [--port 8089] [--token T] [--role iran|node]` (or `--reverse <ws_url> --name <name> --token T`), or from the CLIs: `ratholectl|ratholenode agent on [port] [token]` and `ratholectl|ratholenode agent reverse <ws_url> <name> [token] [--insecure-ssl] [--proxy <url>]`. The token lives in `/etc/rathole-agent/token` (chmod 600).

---

## Core Principle: State → Regenerate → Hot-Reload

Every mutation follows this pattern — **never hand-edit generated configs**; change state and regenerate:

![State→Regenerate→Reload cycle](assets/state-regenerate-reload.svg)

- **ratholectl:** state is `/etc/rathole-manager/state.json` (jq-manipulated). Commands mutate state, then call `regenerate()` → `gen_server_toml()` + `gen_nginx_conf()` → `nginx -t` → reload. Configs are written **in place (inode preserved)** so rathole's `config_watcher` hot-reloads without dropping active tunnels. Auto-reverts to `.rathole-good.bak` if `nginx -t` fails.
- **ratholenode:** base state is `/etc/rathole/node.env`; `/etc/rathole/services.conf` owns rathole-lane services and `/etc/rathole/bh-services.conf` owns Backhaul-lane services. `gen_client()` and `gen_backhaul_client_toml()` build their independent configs. `reload_svc` prefers hot-reload for rathole; transport/core changes restart only the affected unit.

---

## Path == Node Name == Nginx Map == Xray Inbound

A node's `name` is simultaneously its URL path, its nginx `map` entry, and the Xray inbound path on the node. These three must stay identical. Each node has a data service; adding `--api-port` also creates a `<name>_api` service (bound to `127.0.0.1`) for panel↔node management over the tunnel.

---

## Transport Modes and Independent Cores

The rathole lane has four carriers (websocket+TLS default, KCP, plain, Noise). Beside it run **independent lanes/cores**; each Iran path belongs to exactly one lane:

| Lane/core | What it is | Key point |
|---|---|---|
| **Backhaul** (SMUX) | separate Go core (`Musixal/Backhaul`) with SMUX multiplexing | behind the same nginx/443 via `/channel` and `/tunnel`; own `bh-services.conf` registry |
| **FRP** | standalone reverse-tunnel core `fatedier/frp` (frps on Iran, frpc on the node) | transports `tcp\|kcp\|quic\|websocket`, shared token auth, default port 7000 |
| **GRE** | Linux kernel L3 tunnel (`ip tunnel`) on a /30 | no userspace daemon; MTU 1476 + TCPMSS clamping; default interface `gre1` |
| **FRP + GRE** | hybrid: FRP over the GRE L3 link | FRP's multiplexed stream inside GRE; selectable from the hub service controls |
| **Paqet** (Direct PCK) | raw TCP+KCP packet core (`hanselime/paqet`) | zero TLS handshake; uses `CAP_NET_RAW` and automatic `iptables RAW NOTRACK` rules |

A service/path on an Iran server lives in exactly one of these lanes, while several lanes may run at once for different services. Moving a service between lanes **does not change its path or Iran-side port**. Full details: [`transport-modes.en.md`](transport-modes.en.md).

---

## Network Auto-Tuner (`rathole-tuner`) & Fleet Monitor (`v2.4.0`)

![rathole-tuner Architecture](assets/tuner-architecture.svg)

- **`rathole-tuner` (`ratholectl|ratholenode bench` & `#/tuner`):** 6-stage bidirectional benchmark & sysctl/interface auto-tuner (PMTU/MSS with UDP-blocked `TCP_INFO` fallback, non-fixed offloads, `BBR/CAKE/FQ`, safe socket buffers, Bufferbloat, carrier matrix) over an ephemeral HMAC-authenticated peer (`:44990`), backed by **two-phase dead-man Watchdog confirmation** (`bench apply --confirm-ttl 45` + `bench confirm <id>`), live `bench status`, initial pre-tuner snapshot preservation, safe `sysctl --system` + `tc qdisc del root` rollback, and AI-analyzable **`rathole.netprofile.v1` / `rthprof1:`** profiles. See [`performance.en.md`](performance.en.md).
- **`ratholemonitor.service`:** standalone hysteresis fleet monitor and multi-path Telegram bot (`direct`, `proxy`, or `node_tunnel`).
- **Managed Xray (`ratholenode xray`):** native `VLESS+REALITY+Vision` and `XHTTP` lifecycle on nodes with an asynchronous TLS 1.3 + ALPN `h2` cover scanner.

---

## User Ingress Modes

Beyond standard path-routing on 443, three alternative user entry points exist:

- **direct-IP:** a separate HTTP port (default 8081) where users connect directly to the Iran server IP. Node selection uses a hidden header (`X-Cdn-Id: <node_name>`) instead of URL path. The tunnel between Iran↔node is untouched. Backhaul also has an optional direct-IP exposure, which is separate from this user ingress.
- **proxy:** a `/<name>/` path on the same 443 that `proxy_pass`es to any upstream — **without going through rathole**. For independent services that don't need a tunnel.
- **fakeweb:** the default fake site on `fake_port` (default 8080) for servers without a real panel, so `/` never returns 502. Managed with `ratholectl fakeweb start|stop|rm|status`.

---

## Multi-Domain and IP Certificate

One Iran server can serve multiple domains — each with its own nginx server block on the same port 443:

```bash
ratholectl domain add cdn.example.ir [--certbot]
ratholectl domain primary cdn.example.ir
```

For users connecting directly via IP (no domain), a self-signed cert for the IP can be created and trusted on the node:

```bash
ratholectl ip-cert <IPv4>                           # Iran: create self-signed cert
ratholenode set-main <ip>:443 <ip> /path/to/cert    # Node: trust the cert
```

---

## See Also

- [`transport-modes.en.md`](transport-modes.en.md) — all transport/ingress modes with commands
- [`hub.en.md`](hub.en.md) — Hub panel, REST API, security model
- [`traffic-flow.md`](traffic-flow.md) — packet path layer by layer (Persian)
- [`performance.en.md`](performance.en.md) — tuning beyond the tunnel
- [`README.fa.md`](README.fa.md) — full CLI reference and install flows (Persian)
- [`install-manual.md`](install-manual.md) — full manual install walkthrough (English)
- [Wiki — CLI Reference](https://l8pygit.github.io/RatholeEngine/wiki/CLI-Reference/)
