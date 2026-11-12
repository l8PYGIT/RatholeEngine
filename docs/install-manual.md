<div align="center">

<img src="assets/logo.svg" alt="RatholeEngine" width="110" height="110" />

# Full Manual Install — RatholeEngine

**Iran panel + Pasargad config + foreign nodes + central hub**

_Step by step, no automated script — exactly what the installers do (this manual tracks **RatholeEngine v2.0.2**)._

[**Persian version**](install-manual.fa.md) · [**README**](../README.md) · [One-command install](../README.md#quick-start)

</div>

> **Who is this for?** When you want to install **manually**, fully aware of every layer (instead of the one-command `install.sh`), or when an automated install got stuck at some step and you want to carry that step forward by hand. Every command here is taken verbatim from the real scripts (`install-panel.sh`, `install-node.sh`, `install-hub.sh`, `install-agent.sh`, `ratholectl init`).
>
> If the automated install is enough for you, go to the [one-command install](../README.md#quick-start). For the conceptual design and deeper pessimism, read the [Pasargad design doc](../rathole-multilocation-pasargad.md) (Persian).

## Contents

- [0. Prerequisites & sanity checks](#0-prerequisites--sanity-checks)
- [1. Install the rathole binary (both roles)](#1-install-the-rathole-binary-both-roles)
- [2. Iran server (panel) — manual install](#2-iran-server-panel--manual-install)
- [3. Pasargad config (Xray inbound + user)](#3-pasargad-config-xray-inbound--user)
- [4. Foreign node — manual install](#4-foreign-node--manual-install)
- [5. Full central hub install](#5-full-central-hub-install)
- [6. Verification & troubleshooting](#6-verification--troubleshooting)
- [7. Final checklist](#7-final-checklist)
- [8. Private-repo install & updates](#8-private-repo-install--updates)

---

## 0. Prerequisites & sanity checks

| Item | Assumed value (change it) |
|------|---------------------------|
| Domain | `panel.example.ir` (points to the Iran server's IP) |
| Iran server | Public IP, Ubuntu 22.04+ |
| Foreign nodes | e.g. `trk01`, `nld01` … |
| rathole control port (local) | `127.0.0.1:2333` |
| Data port start (local, on Iran) | from `1001` |
| Management/API port start (local, on Iran) | from `7001` |
| Xray ws inbound on each node (local) | `127.0.0.1:<inbound>` (no TLS) |

**Before anything, check these on the Iran server:**

```bash
dig panel.example.ir +short         # must return the Iran server IP
sudo ss -ltnp | grep ':443'         # must be empty; only nginx should own 443
timedatectl                         # clock in sync; clock skew = TLS failure
sudo timedatectl set-ntp true       # if needed
```

> **Pessimism:**
> - Cloud firewall / security group: ports **443 and 80** must be open (80 for certbot).
> - If the domain is behind Cloudflare, start with **DNS-only** (grey cloud); Cloudflare's extra TLS layer is a source of weird trouble.
> - The rathole version **must be identical on the Iran server and all nodes** (`v0.5.0`). This is the rathole binary version and is separate from the manager version (**2.0.2**, shown by `ratholectl version`).

---

## 1. Install the rathole binary (both roles)

Check the architecture with `uname -m`, then install the binary. **This step is identical on the Iran server and all nodes.**

```bash
cd /tmp
VER="v0.5.0"
# x86_64:
ARCH="x86_64-unknown-linux-gnu"
# aarch64 (ARM):  ARCH="aarch64-unknown-linux-musl"

curl -fsSL "https://github.com/rapiz1/rathole/releases/download/${VER}/rathole-${ARCH}.zip" -o rathole.zip
unzip -o rathole.zip
sudo install -m 755 rathole /usr/local/bin/rathole
rathole --version
```

> **GitHub blocked from inside Iran?** Two options:
> 1. Fetch the binary on a **foreign node** and `scp` it to the Iran server, then `install -m 755`.
> 2. Use mirrors (the same ones `install-panel.sh` tries as fallback):
>    `https://ghproxy.net/https://github.com/…` · `https://gh-proxy.com/https://github.com/…` · `https://mirror.ghproxy.com/https://github.com/…`
>
> Old glibc? Grab the `musl` build.

---

## 2. Iran server (panel) — manual install

These are the same steps as `install-panel.sh`, one at a time.

### 2.1 Prerequisites

```bash
sudo apt-get update -y
export DEBIAN_FRONTEND=noninteractive
# sshpass is needed for automated node provisioning from the panel/hub
sudo apt-get install -y nginx jq curl unzip openssl ca-certificates \
     certbot python3-certbot-nginx sshpass
```

### 2.2 Install `ratholectl`

From the `rathole-manager/` directory of the bundle:

```bash
sudo mkdir -p /etc/rathole /etc/rathole-manager /usr/local/share/rathole
sudo install -m 755 ratholectl        /usr/local/bin/ratholectl
sudo install -m 644 common.sh         /usr/local/share/rathole/common.sh
# the REST Agent files are installed too (used only if you enable the Agent, section 5.5):
sudo install -m 755 ratholeagent.py   /usr/local/share/rathole/ratholeagent.py
sudo install -m 755 install-agent.sh  /usr/local/share/rathole/install-agent.sh
sudo ln -sf /usr/local/share/rathole/install-agent.sh /usr/local/bin/install-agent.sh
```

### 2.3 systemd unit for the server

```bash
sudo tee /etc/systemd/system/rathole-server.service >/dev/null <<'UNIT'
[Unit]
Description=rathole server (Iran panel)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/rathole /etc/rathole/server.toml
Restart=always
RestartSec=2
Environment=RUST_LOG=info
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
```

### 2.4 WebSocket upgrade map (once)

```bash
sudo tee /etc/nginx/conf.d/rathole-upgrade-map.conf >/dev/null <<'MAP'
# needed for WebSocket / HTTP Upgrade
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
MAP
```

> **Pessimism:** this `map` must be defined **only once** in the http context; if it appears twice, `nginx -t` fails with `duplicate map`.

### 2.5 Resolve 443 conflicts

Any config already listening on 443 (e.g. an old panel) must move aside:

```bash
grep -rlE 'listen[[:space:]]+(\[::\]:)?443' /etc/nginx/sites-enabled /etc/nginx/conf.d
# Move the offending files into a backup dir (don't delete):
sudo mkdir -p /etc/nginx/rathole-backup-$(date +%Y%m%d-%H%M%S)
# Disable the nginx default site if it has default_server:
sudo rm -f /etc/nginx/sites-enabled/default
```

### 2.6 init — generate state and configs

The core principle: **change state → regenerate config → `nginx -t` → hot-reload.** Never hand-edit `server.toml` or `rathole.conf`; work only through `ratholectl`.

```bash
sudo ratholectl init \
  --domain     panel.example.ir \
  --fullchain  /root/cert/panel.example.ir/fullchain.pem \
  --key        /root/cert/panel.example.ir/privkey.pem
```

Optional `init` flags (the defaults are usually right):

| Flag | Default | Purpose |
|------|---------|---------|
| `--control-port` | `2333` | rathole local control port |
| `--fake-port` | `8080` | fake site / panel on root |
| `--sub-port` | `2096` | subscription |
| `--data-start` | `1001` | start of data port numbering |
| `--api-start` | `7001` | start of management port numbering |
| `--nginx-conf` | `/etc/nginx/conf.d/rathole.conf` | generated nginx config file |
| `--certbot` | — | obtain a cert via certbot if you have none |

> **Certificate:** if a cert already exists at the `--fullchain/--key` paths, it is used. Otherwise, if you pass `--certbot` (or confirm in interactive mode), `certbot` obtains a Let's Encrypt cert (requires DNS pointing here + port 80 free).

### 2.7 Test and bring up the service

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable --now rathole-server
sudo ratholectl doctor        # health check
sudo ratholectl status        # full dashboard: domain, ports, cert, services, nodes
sudo ratholectl paths         # every config/file path with a ✓/✗ (handy when a step got stuck)
sudo ratholectl version       # manager_version + rathole_version
```

> `ratholectl status --json` is the machine-readable form the hub's **Status** button consumes.

> **Later updates:** `sudo ratholectl update` pulls the latest GitHub Release and
> runs the full snapshot + health-check + auto-rollback update. Same for
> `sudo ratholenode update` on a node. Both fall back through ghproxy mirrors, so
> they work from inside Iran. The hub's **Update** button does the same over SSH,
> and its **Update all** button rolls it across every server one-by-one (progress
> bar + a green/red version badge per server).

### 2.8 Add a node

Every time you add a node, `ratholectl` mutates state and regenerates + hot-reloads the configs (without dropping active tunnels):

```bash
# Data-only node:
sudo ratholectl add trk01 2087

# Node with a panel↔node management channel (a <name>_api service on 127.0.0.1):
sudo ratholectl add trk01 2087 --api-port 62050

sudo ratholectl ls                 # list nodes + user paths
sudo ratholectl show trk01         # prints the exact install command for that node
```

`add` (and `show`) also print a ready-to-paste `curl -fsSL …/install.sh | sudo bash -s -- --node -- --server <panel>:443 --name … --token … --inbound-port …` one-liner (with the token/inbound already filled from state) — copy it straight onto the foreign node.

The output of `show` is exactly what you run on the foreign node — go to section [4](#4-foreign-node--manual-install).

> **Key reminder:** the node name (`trk01`) is simultaneously the **URL path**, the **nginx map entry**, and the **Xray inbound path on the node**. These three must stay identical, character for character.

---

## 3. Pasargad config (Xray inbound + user)

### The golden rule of path alignment

The path must be **identical in three places**, otherwise the user "connects but has no internet":

```
user VLESS config   =   nginx location   =   Xray node ws inbound path
      /trk01                /trk01                    /trk01
```

### Inbound on each node (in the Pasargad panel)

For node `trk01`:

- Protocol: **VLESS**
- Network: **ws**
- Path: **`/trk01`**  (the node name)
- Listen: **`127.0.0.1`**
- Port: the same `inbound` you gave to `ratholectl add` (here `2087`)
- TLS: **off** — nginx terminates TLS on the Iran server; turning it on here means double-TLS and breakage.

### User-side config (one domain, one port, one cert)

```
Address : panel.example.ir
Port    : 443
Network : ws
Path    : /trk01          ← to connect through node trk01
Host/SNI: panel.example.ir
TLS     : tls (on — because nginx has the Let's Encrypt cert)
```

To use another node, the user only changes `Path` (`/nld01`, etc.). **Everything else stays the same.**

### Panel↔node management channel (`_api`)

If you created the node with `--api-port`, a `<name>_api` service appears on `127.0.0.1:<api_local_port>` of the Iran server (`ratholectl show` tells you this port). In the Pasargad panel when adding the node:

- Set the node address to **`127.0.0.1`** (not the node's public IP)
- Set the API port to that `api_local_port` (e.g. `7001`)

because the node's API surfaced on the Iran server's localhost through the tunnel.

> **Hard pessimism (from the Pasargad doc):**
> - **Reality does not work behind nginx** — you must use **VLESS/VMess + WS**.
> - Bind the inbound to `127.0.0.1`, not `0.0.0.0`; otherwise the node port leaks directly and the "one port" logic breaks.
> - The Pasargad-node internal cert (panel↔node authentication) is separate from Let's Encrypt and is still required.
>
> Full details and three-layer troubleshooting in the [Pasargad doc](../rathole-multilocation-pasargad.md) (Persian).

---

## 4. Foreign node — manual install

### The easy way: with the installer

`ratholectl show <name>` on the Iran server gives you exactly this. From the `rathole-manager/` directory on the node:

```bash
sudo bash install-node.sh --server panel.example.ir:443 --name trk01 \
     --token <TOKEN> --inbound-port 2087 \
     [--api-token <API_TOKEN> --api-inbound-port 62050]
```

The installer: installs rathole, copies `ratholenode` and `common.sh` (plus `ratholeagent.py` / `install-agent.sh` for the optional REST Agent), creates the `rathole-client` unit, writes `node.env` and `services.conf`, and starts the client.

### The fully manual way (no installer)

If you want to build each file yourself:

```bash
# 1) rathole installed per section 1
sudo mkdir -p /etc/rathole /usr/local/share/rathole
sudo install -m 755 ratholenode /usr/local/bin/ratholenode
sudo install -m 644 common.sh   /usr/local/share/rathole/common.sh
# optional REST Agent files (section 5.5):
sudo install -m 755 ratholeagent.py  /usr/local/share/rathole/ratholeagent.py
sudo install -m 755 install-agent.sh /usr/local/share/rathole/install-agent.sh
sudo ln -sf /usr/local/share/rathole/install-agent.sh /usr/local/bin/install-agent.sh

# 2) client systemd unit
sudo tee /etc/systemd/system/rathole-client.service >/dev/null <<'UNIT'
[Unit]
Description=rathole client (foreign node)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/rathole /etc/rathole/client.toml
Restart=always
RestartSec=2
Environment=RUST_LOG=info
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
```

Then `client.toml` (exactly what `install-node.sh` generates):

```toml
# /etc/rathole/client.toml — on the foreign node
[client]
remote_addr = "panel.example.ir:443"
retry_interval = 1
heartbeat_timeout = 40

[client.transport]
type = "websocket"
[client.transport.websocket]
tls = true
[client.transport.tls]
hostname = "panel.example.ir"

# data service: publishes this node's Xray ws inbound
[client.services.trk01]
token = "<TOKEN>"
local_addr = "127.0.0.1:2087"
type = "tcp"

# (optional) management channel — only if you passed --api-port
[client.services.trk01_api]
token = "<API_TOKEN>"
local_addr = "127.0.0.1:62050"
type = "tcp"
```

```bash
sudo systemctl enable --now rathole-client
journalctl -u rathole-client -f      # should print "control channel established"
```

> **Pessimism:**
> - `remote_addr` is the same for all nodes: `panel.example.ir:443`. Nodes differ only in **service name and token**.
> - The client's `heartbeat_timeout` (`40`) **must** be greater than the server's `heartbeat_interval` (`30`), otherwise the tunnel keeps flapping.
> - `hostname` must match the cert domain exactly, otherwise `certificate verify failed`.
> - Compare tokens against `ratholectl show` output **character by character**.

### More services / upstreams on the same node

```bash
# Another service (IP/inbound) over the same tunnel:
sudo ratholenode add-svc <name> <token> <inbound>

# Attach this node to a second Iran server (multi-location):
sudo ratholenode upstream add <id> <server:443>
sudo ratholenode upstream add-svc <id> <name> <token> <inbound>

sudo ratholenode backup              # back up node state
sudo ratholenode update              # full update from GitHub (latest Release; snapshot + auto-rollback)
```

### Optional: Direct-IP access (header-based routing, no domain/TLS)

If you want users to connect directly to the **IP address** of the Iran server (no domain, no TLS), enable the direct-IP listener:

```bash
# On the Iran server:
sudo ratholectl direct on [--port 8081] [--header X-Cdn-Id]
# Opens a plain HTTP port; nginx routes by header value = node name
# ⚠ Open the port in your firewall: ufw allow 8081/tcp

sudo ratholectl direct show trk01    # prints ready Xray client config
```

In the Xray/V2Ray client: transport = WebSocket **without TLS**, `address:port` = `<IRAN_IP>:8081`, add the header `X-Cdn-Id: trk01` (or whatever header name you chose), `path` = `/trk01` (same as always).

### Optional: Connect a node via IP with self-signed TLS

If the Iran domain is blocked but the IP is reachable, generate a self-signed cert for the IP and trust it on the node:

```bash
# On the Iran server — create self-signed cert for the IP:
sudo ratholectl ip-cert <IRAN_IPv4>

# Print the public cert to copy to the node:
sudo ratholectl ip-cert-show <IRAN_IPv4>   # outputs fullchain.pem content
```

```bash
# On the node — save the cert and point the tunnel at the IP:
echo "<fullchain.pem content>" | sudo tee /etc/rathole/trusted-iran.pem
sudo ratholenode set-main <IRAN_IPv4>:443 <IRAN_IPv4> /etc/rathole/trusted-iran.pem
```

After `set-main`, the node dials `<IRAN_IPv4>:443` and presents the server IP as the TLS SNI, verifying against the saved cert — no domain needed.

### Optional: Watchdog (auto-restart stuck tunnels)

A lightweight systemd timer that periodically checks whether the tunnel services are up and restarts them if they appear stuck:

```bash
sudo ratholenode watchdog on [60]   # check every 60 seconds (default)
sudo ratholenode watchdog status
sudo ratholenode watchdog off
```

### Optional: Multiple domains on one Iran server

One Iran server can serve traffic from multiple domains — each with its own nginx server block and cert, all on the same port 443:

```bash
sudo ratholectl domain add cdn.example.ir --certbot
sudo ratholectl domain ls
sudo ratholectl domain rm cdn.example.ir

# Change the primary domain + cert:
sudo ratholectl domain primary cdn.example.ir --certbot
```

> If you have a wildcard or CDN cert that already covers both domains, pass `--fullchain /path` and `--key /path` instead of `--certbot`.

### Optional: Standalone FRP Reverse Tunnel Core

If you prefer using the mature `fatedier/frp` core for advanced QUIC or KCP multiplexing, you do **not** need to download binaries by hand: `ratholectl frp on` installs `frps` and `ratholenode frp on` installs `frpc` automatically (`install_frp` in `common.sh`, FRP `0.61.1` by default — override with the `FRP_VER` env before running the command).

```bash
# 1) On the Iran server: activate the FRP server (token comes BEFORE the transport):
sudo ratholectl frp on 7000 <SECRET_TOKEN> quic
# generated config: /etc/frp/frps.toml (bindPort 7000, proxyBindAddr 127.0.0.1, auth token)
# other transports: tcp (default), kcp, quic, websocket
# a node's Iran-side port is exposed on 127.0.0.1 only, exactly where the nginx map points.

# 2) On the foreign node: point frpc at Iran (port defaults to 7000 if omitted).
#    The last argument is the node's Iran-side data port (from `ratholectl show` /
#    `ratholectl frp show`, e.g. 1001) — it keeps the nginx map target stable;
#    if omitted, FRP falls back to the node inbound port:
sudo ratholenode frp on <IRAN_IP>:7000 <SECRET_TOKEN> quic <IRAN_PORT>
sudo ratholenode frp status

# 3) Verify the node's proxy registered on 127.0.0.1:<IRAN_PORT>:
sudo ratholectl frp ready <node_name>
```

### Optional: Linux Kernel Layer 3 GRE Tunnel

For direct kernel-level IP network connectivity between servers without application proxies:

```bash
# 1) On the Iran server:
sudo ip tunnel add gre1 mode gre remote <NODE_IP> local <IRAN_IP> ttl 255
sudo ip addr add 10.10.10.1/30 dev gre1
sudo ip link set gre1 mtu 1476 up
# Apply TCPMSS Clamping to prevent packet fragmentation:
sudo iptables -t mangle -A POSTROUTING -p tcp --tcp-flags SYN,RST SYN -o gre1 -j TCPMSS --clamp-mss-to-pmtu

# Automated with ratholectl (tunnel IP without the /30 mask; defaults 10.10.10.1 gre1):
sudo ratholectl gre on <NODE_IP> 10.10.10.1 gre1

# 2) On the foreign node:
sudo ip tunnel add gre1 mode gre remote <IRAN_IP> local <NODE_IP> ttl 255
sudo ip addr add 10.10.10.2/30 dev gre1
sudo ip link set gre1 mtu 1476 up
sudo iptables -t mangle -A POSTROUTING -p tcp --tcp-flags SYN,RST SYN -o gre1 -j TCPMSS --clamp-mss-to-pmtu

# Automated with ratholenode (tunnel IP without the /30 mask; defaults 10.10.10.2 gre1):
sudo ratholenode gre on <IRAN_IP> 10.10.10.2 gre1

# 3) Test Layer 3 connectivity:
ping -c 3 10.10.10.2   # from Iran server
```

### Optional: FRP + GRE Hybrid Mode (Maximum Resilience)

In this setup, the L3 GRE virtual interface is established first, and the FRP daemon operates strictly inside the private network (`10.10.10.0/30`), delivering QUIC/KCP multiplexed streams inside GRE packets. From the hub this is a service control: service row → "Carrier and protocol" → `FRP + GRE` (it runs `gre_probe` first, then points FRP at the GRE virtual IP).

```bash
# 1. Bring up the GRE interface on both sides (following the GRE instructions above).
# 2. On the Iran server: start frps on 7000 (it listens on all interfaces; the FRP
#    token/proxy contract is unchanged, so the nginx map and 443 stay untouched):
sudo ratholectl frp on 7000 <SECRET_TOKEN> quic
# 3. On the foreign node: connect frpc to Iran's GRE virtual IP so the FRP stream
#    is carried inside GRE (10.10.10.1 is the Iran end of the /30). The last
#    argument is the node's Iran-side data port, exactly like the plain FRP lane:
sudo ratholenode frp on 10.10.10.1:7000 <SECRET_TOKEN> quic <IRAN_PORT>
```

---

## 5. Full central hub install

The hub (`ratholehub`) is a Python stdlib web panel installed on **one management server** (usually the Iran panel itself). The backend is split between `hub.py` and the security-critical `hubcmds.py`; static UI assets live under `ui/`. It runs `ratholectl`/`ratholenode` on other servers over **SSH with a key** by default — and, optionally, through the token-authenticated **REST Agent** (section 5.5) — always as validated argv, never a raw shell string. It listens on `127.0.0.1`.

### 5.1 Install

```bash
cd rathole-manager/ratholehub
sudo bash install-hub.sh          # asks for an admin password, generates an API TOKEN
```

The installer does:

- `hub.py` + `hubcmds.py` → `/opt/ratholehub/`
- copies `ui/` (index.html, app.css, app.js, i18n.js) to `/opt/ratholehub/ui/`
- copies `ratholectl`/`ratholenode`/`common.sh`/`update.sh`/… into `/opt/ratholehub/bundle/` (for remote deploy)
- generates `/etc/ratholehub/config.json` (containing `api_token`, admin password hash, `listen_host`/`listen_port`, SSH key path, ssh options, bundle dir) and an empty `inventory.json`
- a `ratholehub.service` unit that reads those two files and listens on `127.0.0.1:8088` (`HUB_PORT` at install time sets `listen_port`; afterwards it lives in `config.json`)
- creates the hub SSH key: `/root/.ssh/id_ed25519`

> `config.json` contains the token and password hash; it is `chmod 600` and **must never** be committed or leaked.

### 5.2 Authorize the SSH key on each server

The hub connects with the SSH key only (no password). Put the hub's public key on every server you want to manage over SSH (servers added with the REST Agent transport skip this):

```bash
# on the hub server:
ssh-copy-id -i /root/.ssh/id_ed25519.pub -p 22 root@<server_ip>
# test:
ssh -i /root/.ssh/id_ed25519 root@<server_ip> 'ratholenode show || ratholectl ls'
```

### 5.3 Access the panel

**The secure way (opening no port)** — SSH local-forward from your own machine:

```bash
ssh -L 8088:127.0.0.1:8088 root@<hub_ip>
# browser:  http://localhost:8088
```

**Or behind nginx under the same domain** — if the hub is on the same Iran panel server, `install-hub.sh` does this automatically; otherwise, manually:

```bash
sudo ratholectl hub on 8088          # persistent location /hub/ behind nginx
# first run: auto-installs the hub too (install-hub.sh, asks for the admin password)
# later runs: changes the hub's real listen_port + restarts ratholehub + updates nginx
# access:  https://panel.example.ir/hub/
sudo ratholectl hub status           # also shows ratholehub service state and port-mismatch warnings
sudo ratholectl hub off              # remove from nginx (the service keeps running on 127.0.0.1)
```

> Since `hub on` makes the panel public, make sure you set a **strong password**.

### 5.4 REST API (example)

Every route uses the `Authorization: Bearer <API_TOKEN>` header (or the UI session cookie):

```bash
TOKEN=... ; B=http://localhost:8088
curl -s -H "Authorization: Bearer $TOKEN" $B/api/servers
curl -s -H "Authorization: Bearer $TOKEN" -X POST $B/api/servers/rp01/action \
  -d '{"action":"kcp_on","args":{"port":"443","profile":"balanced"}}'
```

Full allow-listed actions and security model: [`docs/hub.md`](hub.md) (Persian).

> **Handy hub buttons:** each Iran server has a **Status** button (renders `ratholectl status --json` as a dashboard) and the dashboard has an **Update all** button (updates every server one-by-one with a progress bar + per-server version badge). In a server's node table, **add to node** wires an Iran node (name/token/inbound) onto a foreign node/upstream as a service, and on a node's page **set main tunnel** links it to its Iran server.

### 5.5 Optional: REST Agent — manage a server without SSH

If SSH from the hub to a server is blocked or you do not want to distribute the SSH key, install the **REST Agent** on that server instead. `ratholeagent.py` is a pure-stdlib daemon (`rathole-agent.service`, default `0.0.0.0:8089`) that exposes exactly two endpoints:

- `GET /api/ping` → `{ok, role, version, hostname}` (no auth; useful for reachability checks)
- `POST /api/exec` with `Authorization: Bearer <token>` and `{"cmd": ["ratholectl","status","--json"], "timeout": 120}` → `{ok, rc, out, err}`

It is a **management** plane only; it never carries user traffic. The hub maps its allow-listed actions to argv and posts them here instead of running them over SSH. Security limits: body 1 B–1 MiB, `cmd` must be a non-empty string list, timeout 1–3600 s, binary allow-list (`ratholectl`, `ratholenode`, `systemctl`, `journalctl`, `curl`, `jq`, …), and the token is compared in constant time.

**Install on the server to manage** (after sections [2](#2-iran-server-panel--manual-install)/[4](#4-foreign-node--manual-install); `ratholeagent.py` and `install-agent.sh` are already installed by `install-panel.sh`/`install-node.sh`):

```bash
# role is auto-detected (`/etc/rathole/server.toml` or `/etc/rathole-manager/state.json` → iran, else node)
sudo install-agent.sh                       # port 8089, auto role, token generated
sudo install-agent.sh --role iran --port 8089 --token <TOKEN>
sudo install-agent.sh --role node --port 8089 --token <TOKEN>
```

What the installer does:

- `ratholeagent.py` → `/usr/local/share/rathole/ratholeagent.py` (systemd runs it with `--port <port> --role <role>`)
- token → `/etc/rathole-agent/token` (`chmod 600`; if `--token` is omitted an existing token is reused, otherwise a new hex token is generated)
- `rathole-agent.service` → `Restart=always`, enabled and started

The same thing from the CLIs:

```bash
sudo ratholectl agent on [port] [token]   # Iran panel
sudo ratholenode agent on [port] [token]  # foreign node
sudo ratholectl agent status|token|show|restart|off   # same for ratholenode
```

`agent show` prints the exact `API URL` + `Token` to paste into the hub.

**Optional HTTPS** (recommended — the token otherwise crosses the network in clear text). The agent enables TLS automatically when both files exist; put a certificate there and restart:

```bash
sudo install -m 600 <fullchain.pem> /etc/rathole-agent/cert.pem
sudo install -m 600 <privkey.pem>   /etc/rathole-agent/key.pem
sudo systemctl restart rathole-agent
# equivalent when running the agent manually:
#   ratholeagent.py --port 8089 --role iran --tls-cert /path/cert.pem --tls-key /path/key.pem
#   env RATHOLE_AGENT_TLS_CERT / RATHOLE_AGENT_TLS_KEY also work
```

For a **self-signed** certificate the hub must be told to skip verification: set `"insecure_ssl": true` on that server's record in `/etc/ratholehub/inventory.json` (the hub form does not expose this field), or run the hub with `RATHOLE_AGENT_INSECURE_SSL=1`. Then use an `https://…:8089` API URL.

**Register it in the hub:** Dashboard → **Add server** section → **Connection:** `Agent REST API (direct)` → fill **Agent API URL** (e.g. `https://203.0.113.10:8089`; only scheme/host/port are allowed, no path/query/userinfo) and **Agent Token**. The server badge then shows `⚡ REST API` instead of `🔑 SSH`; status, service controls, health test, updates and audit logging work the same, and the hub still only sends allow-listed argv.

**Firewall/security:** the agent listens on all interfaces by default and the token is the only authentication. Restrict port `8089/tcp` to the hub's IP, or bind the agent behind a tunnel/firewall, and rotate the token by re-running `install-agent.sh --token <new>` (or `ratholectl agent on 8089 <new>`).

**Lifecycle:** `update.sh` and `ratholectl update`/`ratholenode update` refresh `ratholeagent.py` + `install-agent.sh` and restart `rathole-agent` **keeping the same token**; `uninstall-panel.sh`/`uninstall-node.sh` stop and remove the unit and `/etc/rathole-agent` when the role is removed. Quick checks:

```bash
curl -s http://<server-ip>:8089/api/ping        # {"ok":true,"role":"iran",...}
systemctl status rathole-agent --no-pager
```

---

## 6. Verification & troubleshooting

### Golden debug commands

```bash
# On the Iran server: are the local ports open?
sudo ss -ltnp | grep -E '2333|1001|7001'
# nginx on 443?
sudo ss -ltnp | grep ':443'
# On the node: does the Xray inbound actually respond?
curl -v http://127.0.0.1:2087
# Logs on both ends simultaneously:
journalctl -u rathole-server -f   # Iran
journalctl -u rathole-client -f   # node
```

### Troubleshooting table

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Node keeps "retrying" | wrong domain/port, nginx down, firewall | `curl -v https://panel.example.ir` and `ss -ltnp` |
| Drops immediately after connecting | token mismatch | compare against `ratholectl show` |
| User connects but has no internet | **three-way path mismatch** | user path = nginx = Xray |
| Node offline in the panel | `_api` channel not set / wrong port | check the `_api` service and `api_local_port` |
| `certificate verify failed` | hostname doesn't match the cert | `hostname` = real domain |
| WebSocket `400/502` | nginx not passing the Upgrade header | the `map` and `proxy_set_header`s |
| Tunnel drops every 60s | low nginx timeout | don't touch the generated config; `ratholectl regen` |
| `duplicate default server` | old server block on 443 | section [2.5](#25-resolve-443-conflicts) |
| `ratholehub` won't come up | config/python error | `journalctl -u ratholehub -n 30` |
| Hub shows "Agent unavailable" (`401`/`403`/timeout) | wrong token/URL, port 8089 blocked, self-signed HTTPS not trusted | `curl -s http://<server>:8089/api/ping`; re-check the token; `insecure_ssl: true` for self-signed; firewall |

> **Golden method:** start from the lowest layer — 1) does the Xray inbound respond locally on the node? → 2) are the rathole services (`_data`/`_api`) established? → 3) is nginx proxying the path correctly? → 4) is TLS/DNS healthy from the outside?

---

## 7. Final checklist

- [ ] `rathole` at the **same version** (`v0.5.0`) on Iran and all nodes.
- [ ] Domain DNS points to the Iran server IP; ports 443 and 80 open on the firewall.
- [ ] Only nginx sits on 443 (not Xray directly, not an old panel).
- [ ] Cert obtained and `nginx -t` clean; `map $http_upgrade` defined only once.
- [ ] `rathole-server` on Iran and `rathole-client` on each node **active and enabled**.
- [ ] For nodes needing management, `--api-port` was given (the `_api` service).
- [ ] Tokens match `ratholectl show` exactly; all `bind_addr`/`local_addr` on `127.0.0.1`.
- [ ] Client `heartbeat_timeout` (40) > server `heartbeat_interval` (30).
- [ ] **Path identical in three places:** user config = nginx = Xray inbound.
- [ ] Xray inbound on the node is **TLS-off** and on `127.0.0.1`; protocol **VLESS+WS** (not Reality).
- [ ] In the panel, node address is `127.0.0.1` and the API port is `70xx`.
- [ ] All servers' clocks in sync; both ends log "control channel established".
- [ ] (Hub) the hub SSH key is authorized on every server in the inventory.
- [ ] (Hub, optional) servers managed over the REST Agent show `⚡ REST API`, `rathole-agent` is active, and port `8089` is firewalled to the hub only.
- [ ] (Private repo) `install.sh --token`/`RATHOLE_GH_TOKEN` worked and updates go through `tools/update-private.sh`.
- [ ] Manager is at **2.0.2** (`ratholectl version`); the rathole binary is `v0.5.0` on both ends.
- [ ] End-to-end connection tested from a real user client.

---

## 8. Private-repo install & updates

Everything above assumes the public repo (`loopy-iri/tunnelplus`; `RATHOLE_GH="owner/repo"` overrides the slug). If your fork/mirror is **private**, the files are served through the GitHub API and the public ghproxy mirrors are skipped (they cannot read a private repo).

### 8.1 One-command install from a private repo

`install.sh` accepts the token as a flag (`--token <PAT>` / `-t <PAT>`) or from the environment (`RATHOLE_GH_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`; the flag wins). Note that for a **private** repo the `install.sh` file itself also needs the token to be fetched:

```bash
# fetch install.sh with the token, then hand the same token to the script:
curl -fsSL -H "Authorization: Bearer <github_pat>" \
  https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh \
  | sudo bash -s -- --token <github_pat> --release v2.0.2 \
      --panel --domain panel.example.ir \
      --fullchain /root/cert/panel.example.ir/fullchain.pem \
      --key /root/cert/panel.example.ir/privkey.pem

# node: keep the "--" separator so the node arguments (including its token) are preserved
curl -fsSL -H "Authorization: Bearer <github_pat>" \
  https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh \
  | sudo bash -s -- -t <github_pat> --release v2.0.2 --node -- \
      --server panel.example.ir:443 --name trk01 --token <NODE_TOKEN> --inbound-port 2087
```

Alternatively `git clone` the private repo (or copy the bundle) and run the bundled script locally: `sudo bash install.sh --token <PAT> --panel …`.

- With a token, `install.sh` sends `Authorization: Bearer <token>` to `github.com`/`raw.githubusercontent.com` for every download it performs. It fetches the Release assets first; if they are unavailable it falls back to the raw `bootstrap.sh` of the pinned ref (or `main` for `latest`), then the bundle from the Release, and finally the archive via `api.github.com/repos/<slug>/tarball/<ref>`.
- The resolved token is exported as `RATHOLE_GH_TOKEN` before handing off to `bootstrap.sh`; the node token after `--` is preserved (the post-2.0.2 argument-separator fix).
- The PAT needs **Contents: read** on that repo. Do not paste it into shared terminals or commit it anywhere.

### 8.2 Updating an installed server from a private repo

```bash
# on the server (panel, node or hub — the role is auto-detected):
sudo bash tools/update-private.sh
# optional overrides:
sudo RATHOLE_GH="owner/repo" RATHOLE_RELEASE=v2.0.2 bash tools/update-private.sh
```

It asks for the token with a hidden prompt (or reads `RATHOLE_GH_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN`), downloads the Release assets (`bootstrap.sh` + `rathole-manager.zip`/`.tar.gz`) through the API, then runs `bootstrap.sh --local <bundle> --update`. Set `RATHOLE_RELEASE=main` to build the bundle from the `main` source tarball instead of a Release. The script unsets the token variables on exit.

### 8.3 The safe update path (`update.sh`)

Both `ratholectl update [beta|stable|vX.Y.Z]` / `ratholenode update …` and the hub's Update button download the Release `install.sh` and run it with `--update`, which ends up in `update.sh`:

- full pre-update snapshot (CLI + configs + systemd units per role) in `/var/backups/rathole-manager/pre-update-<ts>/` (`manifest.txt` + `backup.tar.gz`)
- per-role health check (`rathole-server`/`rathole-client`/`ratholehub` active + `nginx -t`)
- automatic rollback to the snapshot on failure; retention = last 7 (`RATHOLE_BACKUP_RETENTION`)
- manual controls:

```bash
sudo bash update.sh --list-backups          # list snapshots
sudo bash update.sh --rollback              # back to the latest snapshot
sudo bash update.sh --rollback <timestamp>  # back to a specific snapshot
sudo bash update.sh --no-rollback           # update, but never auto-rollback
sudo bash update.sh --allow-downgrade       # allow installing an older version (guarded by default)
```

Version pinning: `install.sh --release v2.0.2`, env `RATHOLE_RELEASE=v2.0.2`, or `sudo ratholectl update v2.0.2` (same for `ratholenode update`). The current manager version is **2.0.2** (`ratholectl version` prints `manager_version` and the rathole binary version separately).

---

**Full CLI reference & automated install:** [`README.fa.md`](README.fa.md) (Persian) · **Design & deep pessimism:** [Pasargad doc](../rathole-multilocation-pasargad.md) (Persian) · **Hub:** [`hub.md`](hub.md)
