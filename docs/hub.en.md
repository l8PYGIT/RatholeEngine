# ratholehub — Web Management Panel

Central web panel for managing multiple Iran servers and foreign nodes without touching the existing system. No agents are installed on servers — the hub runs SSH commands on the same battle-tested `ratholectl`/`ratholenode` CLIs.

![Hub architecture](assets/hub-architecture.svg)

*Hub listens on `127.0.0.1` behind nginx at `/hub/`. It connects to each server over SSH (key auth) and executes validated argv-list commands — never raw shell strings.*

---

## Why this design

- **No agent on nodes** — the hub runs on one server (usually the primary Iran server) and drives the rest over SSH with the already-tested CLIs. No new port or service on nodes.
- **No pip dependencies** — pure Python stdlib. No conflicts with anything on the server.
- **Token-authenticated REST API** — for automation and external tooling.
- **Secure** — listens on `127.0.0.1`; access via SSH forward or nginx under the same domain. Single-port/single-domain is preserved.

---

## Installation

```bash
# Recommended — via ratholectl on the Iran server:
sudo ratholectl hub on [port]
# Installs the hub automatically if not already installed.

# Direct:
sudo bash rathole-manager/ratholehub/install-hub.sh

# From GitHub:
curl -fsSL https://raw.githubusercontent.com/loopy-iri/tunnelplus/main/install.sh | sudo bash -s -- --hub
```

---

## Accessing the Panel

**Most secure (no port opened):**
```bash
ssh -L 8088:127.0.0.1:8088 root@<server_ip>
# Browser: http://localhost:8088
```

**Via nginx under the same domain:**
```bash
sudo ratholectl hub on 8088   # → https://<domain>/hub/
```

---

## Adding Servers

**Easy way — "Provision" button in the dashboard (or `POST /api/provision`):**
Connects once with an SSH password (requires `sshpass` on the hub), adds the hub's public key to `authorized_keys` (idempotent), runs deploy from GitHub, and registers the server in the inventory. The hub's key comes from config (`ssh_key_path`; the installer creates `/root/.ssh/id_ed25519`); if absent, the hub generates `/etc/ratholehub/id_ed25519`.

**Manual:**
```bash
ssh-copy-id -i /root/.ssh/id_ed25519.pub root@<node_ip>
# Then add the server via POST /api/servers
```

---

## UI (v1.9.1)

The Hub UI is a static asset tree under `ratholehub/ui/`, served by the stdlib backend. It has no frontend build step or runtime dependency. It is bilingual (Persian/English), switches RTL/LTR direction, supports light/dark themes, responsive desktop/mobile layouts, accessible dialogs, keyboard focus management, and reduced-motion preferences. Language and theme are stored locally in the browser.

The dashboard supports grid and list views. Refresh is page-aware (default 20 seconds), while routing provides both a draggable SVG topology graph and a console/table view. Long command output opens in a copyable modal; collected logs can also be downloaded as text.

| Page | Hash | Content |
|------|------|---------|
| **Dashboard** | `#/dashboard` | Server cards, grid/list toggle, availability/version badges, add-server and Provision forms, Update All progress. |
| **Server page** | `#/server/<name>` | Overview, domain/certificates, ports/paths, rathole carriers, ingress modes, node/service tables, game/SNI, Backhaul lane, status/details/log actions. |
| **Routing / Console** | `#/routing` | Ingress versus tunnel lanes, draggable SVG graph, console/table view, and direct links to server pages. |
| **Activity** | `#/audit` | Authenticated audit history with time, user, server, action, and return code. |
| **Settings** | `#/settings` | Listen/API-token hint, API-token rotation, and admin-password change. |

### Ports Section (in server page)

| Port | Editable? | Description |
|------|-----------|-------------|
| `fake-port` | ✅ | Fake site port (default 8080) |
| `sub-port` | ✅ | Subscription port (default 2096) |
| `control-port` | ✅ | rathole control port (default 2333) |
| `internal` | Display only | Internal panel port (behind SNI) |
| `hub`, `plain`, `noise`, `backhaul`, `direct` | Display only | Port of each listener/core |

The `sub-path` and `hub-path` path segments are editable too. Carrier-owned ports are display-only because enabling/disabling that carrier owns their lifecycle.

### Key Buttons

- **"Update All"** — updates all servers one by one over SSH. Live progress bar: queued → updating → ✓ new version or ✗ (rc=N). The server running the hub itself is included; if the hub service restarts mid-update, that one row may show incomplete while the rest finish.
- **Version badge** — green = up to date, yellow `vX→vY` = needs update. Version is read from `ratholectl/ratholenode version` and compared against `latest_version` from `GET /api/hubstatus` (which reads `MANAGER_VERSION` from `common.sh` in the deployed bundle).
- **"Wire to node"** — registers an Iran node (name/token/inbound) as a service on a foreign node or upstream. The hub fetches the actual token/inbound via `GET /api/servers/<iran>/nodeconnect/<node>` (masked in `ls`), then runs `add_svc` (or `upstream_add_svc`) on the target.
- **"Set main tunnel"** — links a foreign node to a registered Iran server by setting `SERVER=host:443` (action `set_server`). The provision form also has an "Iran server" select; if the server being provisioned has role `node`, the hub sets its main tunnel automatically after a successful deploy.
- **Backhaul lane services** — node pages expose a separate table backed by `bh-services.conf`; adding/removing Backhaul services does not stop the normal rathole client.
- **Theme/language controls** — icon buttons switch theme, language, refresh, and logout, with accessible labels and tooltips.

---

## REST API

All routes require `Authorization: Bearer <API_TOKEN>` (or the session cookie from the UI).

```
GET    /api/health
POST   /api/login                             {"password":"..."} → {token}
GET    /api/hubstatus                          Hub status + latest_version
GET    /api/servers                            List servers
POST   /api/servers                            {name, role(iran|node), host, ssh_user, ssh_port}
PUT    /api/servers/<name>                     Edit inventory record
DELETE /api/servers/<name>
POST   /api/provision                          Auto-install (SSH key + deploy + register)
GET    /api/servers/<name>/status              Server status (JSON)
GET    /api/servers/<name>/discover            Iran node discovery
GET    /api/servers/<name>/overview            Compact overview + version
GET    /api/servers/<name>/details             Detailed diagnostics
GET    /api/servers/<name>/{kcp,noise,backhaul}connect  Carrier autofill data
GET    /api/servers/<name>/mainconnect         Main-tunnel autofill data
POST   /api/servers/<name>/action             {"action":"...", "args":{...}}
GET    /api/servers/<iran>/nodeconnect/<node>  Real token/inbound of an Iran node (for wire-to-node)
GET    /api/config                             Redacted Hub configuration
POST   /api/config                             Rotate token/change admin settings
GET    /api/audit?limit=100                    Recent audit records (max 500)
POST   /api/ip-tls/prepare                     Prepare IP-TLS data for a node
```

**Example:**
```bash
TOKEN=your_api_token
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8088/api/servers
curl -s -H "Authorization: Bearer $TOKEN" -X POST \
  http://localhost:8088/api/servers/rp01/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"status","args":{}}'
```

---

## Security Model

The hub never executes raw strings on servers. Every request goes through:

1. **Allow-list check** — the action must be in the explicit whitelist (`hubcmds.py`).
2. **Argument validation** — every argument is validated against a strict regex (`RE_NAME`, `RE_IPPORT`, `RE_KEY`, `RE_SLUG`, …).
3. **argv-list execution** — `build_iran_cmd`/`build_node_cmd` produce a list where each argument is passed separately over SSH (`run_on_server` → `_ssh_base`) — no shell string interpolation.
4. **Remote deploy** — the "Update" / "Update All" button runs `install.sh --update` on the server itself (fetched from GitHub via the ghproxy mirror loop); only the validated `gh_repo` slug is substituted into a fixed `bash -c` script.
5. **Audit log** — every operation (user, server, action, rc) is recorded; visible at `#/audit`.

The security-critical action→argv mapping lives in the separate **`hubcmds.py`** module (small, reviewable, no dependencies on the rest of the hub) since v1.6.

**Action scopes:**
- *Shared (both roles):* `deploy` (remote update with snapshot + auto-rollback), `status`, `version`.
- *Iran:* `ls`, `doctor`, `status`, `regen`, transport management (`kcp_*`, `plain_*`, `noise_*`, `backhaul_*`, `direct_*`), game management (`game_*` — `game_cert` fetches a Let's Encrypt cert and returns the **private key**; only use from an authenticated hub and don't log), node management (`add_node`, `rm_node`, `show_node`), proxy (`proxy_add`/`proxy_rm`/`proxy_ls`).
- *Node:* `show`, `ls`, `upstream_ls`, `set_server`, service management (`add_svc`, `rm_svc`, `upstream_add`, `upstream_add_svc`), transport (`kcp_*`, `upstream_kcp_*`, `noise_*`, `backhaul_*`), `apply`.

---

## Local Development (Mock Mode)

```bash
RATHOLEHUB_MOCK=1 RATHOLEHUB_PORT=8088 python3 rathole-manager/ratholehub/hub.py
# Browser: http://127.0.0.1:8088
# RATHOLEHUB_MOCK=1 → SSH is never executed; fake responses are returned
```

Environment variables: `RATHOLEHUB_HOST`, `RATHOLEHUB_PORT`, `RATHOLEHUB_CONF`, `RATHOLEHUB_INV`, `RATHOLEHUB_MOCK`.

---

## File Layout (v1.6+)

The UI is no longer inlined in `hub.py`; it lives in `ratholehub/ui/` alongside `hub.py`:

```
ratholehub/
├── hub.py          Main server (ThreadingHTTPServer, routing, SSH, API)
├── hubcmds.py      Action→argv map + argument regexes (security-critical, keep small)
└── ui/
    ├── index.html
    ├── app.css
    ├── app.js
    └── i18n.js     Persian/English strings
```

Files are served with a **filename whitelist** (no path joining, so path traversal is impossible). `install-hub.sh` and `update.sh` both install/update the full tree (`hub.py` + `hubcmds.py` + `ui/`).

---

## See also

- [CLI Reference (Wiki)](https://github.com/loopy-iri/tunnelplus/wiki/CLI-Reference) — `ratholectl hub` and all related commands
- [Hub Management (Wiki)](https://github.com/loopy-iri/tunnelplus/wiki/Hub-Management) — Persian wiki version of this page
- [`hub.md`](hub.md) — Persian version of this document
- [`architecture.md`](architecture.md) — System architecture overview
