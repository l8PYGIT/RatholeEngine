# Quick start — interactive install in 5 steps

This page is the **shortest path to a working system**: one command, a few questions, done.
For a manual / fully custom install see the [full install manual](install-manual.md).

!!! tip "TL;DR"
    On the Iran server, run this and answer the prompts:

    ```bash
    curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash
    ```

---

## 0) Prerequisites

| Item | Requirement |
|---|---|
| OS | Ubuntu 22.04 / 24.04 (or Debian 12) |
| Access | `root` (or `sudo`) |
| Port | `443/tcp` free on the Iran server |
| Domain | one domain pointing at the Iran server (e.g. `panel.example.ir`) |
| TLS cert | `fullchain.pem` + `privkey.pem` (or let the installer run certbot) |
| Foreign server | a VPS outside Iran for the "node" role (optional, can be added later) |

!!! note "Why a certificate?"
    Users connect to `https://domain`, and nginx is the only place TLS terminates.
    If you don't have a certificate, answer `y` to the certbot question during install.

---

## 1) Install the Iran panel (~5 minutes)

On the **Iran server**:

```bash
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash
```

### What it asks

**a) Version:**

```text
kodam noskhe nasb shavad?
  - Enter        → latest (akharin noskhe-ye paydar — tosiye)
  - yek tag      → masalan v1.8.0 (noskhe-ye khas-e montasher-shode)
  - beta         → akharin pre-release (azmayeshi)
entekhab [latest]:
```

→ just press **Enter**.

**b) Install mode:**

```text
halat nasb ra entekhab kon:
  1) panel (server Iran)
  2) node (server kharej)
  3) update (beroozresani kamel ba snapshot + rollback-e khodkar)
  4) fght amade-sazi (bedoon ejra-ye nasab)
  5) rollback (bazgasht be akharin snapshot-e ghabl az update)
  6) list-e backup-ha (snapshot-haye mojood)
  7) hazf kamel (uninstall — panel/node/hub + config/state)
entekhab [1/2/3/4/5/6/7]:
```

→ on the Iran server choose **`1`**.

**c) Initial setup (`ratholectl init`)** — only the first two answers matter:

```text
damnh (masalan btli.ir):  panel.example.ir
masir fullchain.pem [/root/cert/panel.example.ir/fullchain.pem]:
masir privkey.pem   [/root/cert/panel.example.ir/privkey.pem]:
file config nginx baraye tvlid/riplis [/etc/nginx/conf.d/rathole.conf]:
port kontroli lvkal rathole [2333]:
port sait fik/panel (default) [8080]:
port sabaskripshn [2096]:
shrva shmarh port dita [1001]:
shrva shmarh port mdirit(api) [7001]:
```

- Enter the **domain**, and the certificate paths if they are not in the default location.
- Press **Enter** for everything else (the defaults are fine).
- If the cert is missing: `ba certbot grfth shvd? [y/N]` → answer `y` if DNS points at this server.

!!! warning "No certificate and no certbot?"
    The install continues, but nginx stays down until a certificate exists. Fix it later with
    `ratholectl cert <domain>` or `ratholectl set fullchain <path>`.

---

## 2) Verify the install

```bash
sudo ratholectl status     # dashboard: domain, ports, cert, services, nodes
sudo ratholectl doctor     # health check (everything should be ✓)
sudo ratholectl paths      # every file path with ✓/✗
```

Expected: `rathole-server: active`, `nginx: active`, a valid certificate, and a clean `doctor`.

---

## 3) Add a node (on the Iran panel)

Pick a name and an inbound port (the name becomes the public path):

```bash
sudo ratholectl add trk01 2087
```

It prints a ready-to-paste install command for that node:

```bash
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh \
  | sudo bash -s -- --node -- \
    --server panel.example.ir:443 --name trk01 \
    --token <TOKEN> --inbound-port 2087
```

> Re-print it any time with `sudo ratholectl show trk01`.

### On the foreign server

Run that command — or, if you prefer interactive:

```bash
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash
# install mode → 2 (node)
```

and answer:

```text
adres server Iran (masalan panel.example.ir:443):  panel.example.ir:443
name node (masalan trk01):                         trk01
token service:                                     <TOKEN from the panel>
port inbound Xray rooye node [2087]:               2087
token API (akhtiari, khali=rad):                   ← Enter
```

---

## 4) End-to-end check

On the **Iran panel**:

```bash
sudo ratholectl ls        # trk01 should show as healthy
sudo ratholectl doctor    # final check
```

On the **node**:

```bash
sudo ratholenode status
sudo ratholenode logs 50
```

User path: `https://panel.example.ir/trk01` → nginx → tunnel → Xray on the node.

---

## 5) Hub (optional)

To manage many Iran servers / nodes from one web panel:

```bash
sudo ratholectl hub on 8088     # install + enable behind nginx
sudo ratholectl hub auto-add    # register this server in the inventory
sudo ratholectl hub status
```

Then open `https://panel.example.ir/hub/` — and if you don't want SSH, on each server:

```bash
sudo install-agent.sh --role iran|node   # REST Agent management (port 8089)
```

---

## Quick troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `nginx -t` fails | wrong certificate / path | `ratholectl paths` → fix `fullchain`/`key`, then `ratholectl regen` |
| `rathole-server` won't start | port `2333` in use | `ratholectl set control-port 2334` then `ratholectl regen` |
| Node won't connect | token/address, or 443 blocked | `ratholenode logs 100`; re-read the token from `ratholectl show <name>` |
| `/trk01` shows the decoy site | node not connected | `ratholectl doctor`; check the node state in `ratholectl ls` |
| Certificate expired | not renewed | `ratholectl certs` then `ratholectl cert <domain>` |

Still stuck? [Full troubleshooting](wiki/Troubleshooting.md) · [manual install](install-manual.md)

---

## Non-interactive install (for scripts / CI)

To answer nothing, pass everything as flags:

```bash
# Iran server
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh \
  | sudo bash -s -- --panel \
    --domain panel.example.ir \
    --fullchain /root/cert/panel.example.ir/fullchain.pem \
    --key       /root/cert/panel.example.ir/privkey.pem

# Foreign node (note: node args go after --)
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh \
  | sudo bash -s -- --node -- \
    --server panel.example.ir:443 --name trk01 --token <T> --inbound-port 2087
```

Specific version: `--release v2.0.3` · beta: `--beta` · stable: `--stable`
(`RATHOLE_GH=owner/repo` overrides the repository slug.)