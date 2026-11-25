<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/banner-light.png">
  <img src="docs/assets/banner-dark.png" alt="RatholeEngine — Multi-Location Reverse Tunnel System" width="100%">
</picture>

**Multi-location reverse-tunnel engine built on `rathole` + `Nginx`** — _One port · one domain · 9 carriers · Auto-Tuner (`rthprof1:`) · Web Hub, Reverse WS Agent & Managed Xray_

[![CI](https://github.com/l8PYGIT/RatholeEngine/actions/workflows/ci.yml/badge.svg)](https://github.com/l8PYGIT/RatholeEngine/actions/workflows/ci.yml)
[![Docs](https://github.com/l8PYGIT/RatholeEngine/actions/workflows/docs.yml/badge.svg)](https://l8pygit.github.io/RatholeEngine/)
[![Release](https://img.shields.io/github/v/release/l8PYGIT/RatholeEngine?style=flat-square&sort=semver&color=7c3aed)](https://github.com/l8PYGIT/RatholeEngine/releases/latest)
[![License](https://img.shields.io/github/license/l8PYGIT/RatholeEngine?style=flat-square&color=2563eb)](LICENSE)
[![Stars](https://img.shields.io/github/stars/l8PYGIT/RatholeEngine?style=flat-square&color=16a34a)](https://github.com/l8PYGIT/RatholeEngine/stargazers)
[![Telegram](https://img.shields.io/badge/Telegram-%40l8PY4NET-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://t.me/l8PY4NET)

[**Docs Site**](https://l8pygit.github.io/RatholeEngine/) · [**Wiki**](https://l8pygit.github.io/RatholeEngine/wiki/Home/) · [**Quick Start**](#quick-start) · [**Transport Modes**](#transport--ingress-modes) · [**Auto-Tuner**](#network--kernel-auto-tuner-rathole-tuner) · [**RatholeHub**](#ratholehub-web-panel-v240) · [**فارسی**](docs/README.fa.md) · [**Telegram**](https://t.me/l8PY4NET)

</div>

---

## Architecture

One **Iran edge server** behind a single domain, TLS certificate, and public `:443` port fronts many **foreign nodes** connected via outbound reverse tunnels (`map $uri $backend_port` in Nginx). The system spans **four roles**: Iran Panel ([`ratholectl`](rathole-manager/ratholectl)), Foreign Node ([`ratholenode`](rathole-manager/ratholenode)), Central Web Hub ([`hub.py`](rathole-manager/ratholehub/hub.py), stdlib Python), and an optional **REST / Reverse WS Agent** ([`ratholeagent.py`](rathole-manager/ratholeagent.py) + [`wsutil.py`](rathole-manager/wsutil.py), direct `:8089` or outbound **Reverse WebSocket (`reverse_ws`)** to `/hub/ws/agent` with zero open inbound ports). Every mutation edits state only, regenerates configs in place via `rth_commit_config` (preserving inodes for hot-reload), runs `nginx -t`, and reloads safely with automatic rollback.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/architecture.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/architecture-light.svg">
  <img src="docs/assets/architecture.svg" alt="RatholeEngine Architecture" width="100%">
</picture>

## Quick start

Run the one-command interactive installer (`Enter` picks latest release; choose role `1` Iran Panel, `2` Foreign Node, `3` Update, or `7` Uninstall):

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh)"
```

> [!TIP]
> **Step-by-step interactive walkthrough:** [`docs/quickstart.md`](docs/quickstart.md) · [English](docs/quickstart.en.md)  
> **Offline / file-based install (`bootstrap.sh --local`):** [`docs/install-offline.md`](docs/install-offline.md) · [English](docs/install-offline.en.md)

<details>
<summary>⚙️ <b>Non-interactive flags, version pinning &amp; essential panel commands</b></summary>

```bash
# Iran panel (non-interactive)
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --panel \
  --domain panel.example.ir \
  --fullchain /root/cert/panel.example.ir/fullchain.pem \
  --key       /root/cert/panel.example.ir/privkey.pem

# Foreign node (keep node flags after `--`; pass `--release v2.1.1` before `--panel`/`--node` to pin)
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --node -- \
  --server panel.example.ir:443 --name trk01 --token <T> --inbound-port 2087

# Essential panel CLI
ratholectl hub on 8088            # enable Web Hub behind nginx /hub/
ratholectl add trk01 2087         # add node on /trk01 & print ready node install command
ratholectl status                 # panel dashboard (--json for Hub)
ratholectl doctor                 # end-to-end health check
```

</details>

## Transport & ingress modes

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/transport-modes.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/transport-modes-light.svg">
  <img src="docs/assets/transport-modes.svg" alt="RatholeEngine Transport & Ingress Modes" width="100%">
</picture>

| Carrier | Core / Layer | Default Port / Proto | Best Used For |
|---|---|---|---|
| **WebSocket + TLS** *(default)* | `rathole` (L7) | `:443/TCP` (`/_rh/<hex>` control) | Stealth HTTPS camouflage behind Nginx |
| **KCP** | `rathole` + `kcptun` | `:443/UDP` (FEC mux) | High packet-loss / congested paths |
| **Plain** | `rathole` (no TLS) | `:8880/TCP` | Minimal CPU overhead (explicit opt-in) |
| **Noise** | Second `rathole` | `:2334/TCP` (X25519) | Cert-free encrypted carrier off Nginx |
| **Backhaul (SMUX)** | `Musixal/Backhaul` | `:443/TCP` (`/channel`+`/tunnel` → `:3080`) | High-concurrency SMUX + uTLS Chrome |
| **FRP** | `fatedier/frp` | `:7000/TCP` (`tcp`/`ws`) + `:7000/UDP` (`kcp`/`quic`) | Flexible mux carrier off `:443` |
| **GRE** | Linux kernel `ip_gre` | IP Proto 47 (`/30` · `MTU 1476`) | Direct L3 IP link without proxy |
| **FRP + GRE** | FRP inside GRE `/30` | Kernel GRE + internal `:7000` | Strict DPI resistance combining L3 + mux |
| **Paqet (Direct PCK)** | `paqet` raw TCP+KCP | Random raw-TCP (`PCAP`/iptables) | Censorship evasion without any TLS handshake |

*Ingress & Edge modes:* **Managed Xray** (`VLESS+REALITY+Vision`, `VLESS+XHTTP` + concurrent **TLS 1.3 + ALPN `h2` Cover Scanner**), **Game / SNI** (L4 `:443` passthrough + PROXY protocol), **Direct-IP** (`:8081` + `X-Cdn-Id`), **Proxy** (`/<name>/` upstream), and **Fakeweb** (`:8080`). Full details: [`docs/transport-modes.en.md`](docs/transport-modes.en.md) · [فارسی](docs/transport-modes.md).

## Network & kernel auto-tuner (`rathole-tuner`)

Ruthless 6-stage bidirectional benchmark & sysctl/interface auto-tuner (`PMTU/MSS` with UDP-blocked `TCP_INFO` fallback, NIC offloads ignoring `[fixed]` capabilities, `BBR/CAKE/FQ`, safe `rmem_default`/`wmem_default` + high-BDP max buffers, loaded Bufferbloat, and live carrier matrix) with throughput non-regression guards, 5D scoring, non-kernel Xray/Nginx audit, and deterministic **two-phase dead-man Watchdog confirmation** (`bench apply --confirm-ttl 45` + `bench confirm <id>`, auto-reverting if connectivity drops). Outputs structured AI-analyzable JSON (`rathole.netprofile.v1`) and portable Base64url **`rthprof1:`** datacenter profiles.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/tuner-architecture.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/tuner-architecture-light.svg">
  <img src="docs/assets/tuner-architecture.svg" alt="rathole-tuner Architecture" width="100%">
</picture>

<details>
<summary>🚀 <b>CLI auto-bench, A/B/N profile test, two-phase apply &amp; rollback commands</b></summary>

```bash
# 1. Start ephemeral HMAC responder on foreign node:
sudo ratholenode bench listen --port 44990 --token <SECRET> --idle-sec 300

# 2. Run 6-stage benchmark on Iran server (emits JSON + rthprof1: profile):
sudo ratholectl bench run --peer <NODE_IP>:44990 --token <SECRET> \
  --mode brutal --goal balanced --iran-dc arvan --node-dc hetzner-fsn1 --out /tmp/dc.json

# 3. Live A/B/N compare, two-phase dead-man apply, live status, or rollback:
sudo ratholectl bench test --peer <NODE_IP>:44990 --token <SECRET> --profile "rthprof1:..."
sudo ratholectl bench apply --profile /tmp/dc.json --confirm-ttl 45
sudo ratholectl bench confirm <CONFIRM_ID>
sudo ratholectl bench status --json
sudo ratholectl bench rollback
```

</details>

## RatholeHub web panel (`v2.4.0`)

- **Reverse WebSocket Agent (`reverse_ws` — zero inbound ports)** — Pure-stdlib RFC 6455 outbound agent (`ratholeagent.py` v2.0.0 + `wsutil.py`) dialing the Hub on `/hub/ws/agent` (port 443 through Nginx TLS) or `/ws/agent` with `--insecure-ssl` and HTTP `CONNECT` proxy support — ideal for filtered or NAT-bound nodes, with 1-click conversion from offline REST servers, a 1-line setup modal, live online/waiting status badges, and token rotation.
- **Apple Glass UI (100% offline, stdlib Python)** — Light / Dark / System themes, bundled `vazirmatn.woff2`, Persian RTL / English LTR, native `<dialog>` modals, and **`⌘K / Ctrl+K` Command Palette**.
- **Network Auto-Tuner UI (`#/tuner`)** — Run async 6-stage benchmarks across server pairs with persistent job state across refreshes, inspect live kernel state (`GET /api/tuner/status`) and winner previews before applying, compare 5D scores (`Balanced`, `Low Latency`, `Max Throughput`, `Anti-Loss`), copy/import `rthprof1:` & JSON AI profiles, and manage a saved Datacenter Profile Library with live A/B testing & two-phase Watchdog rollback.
- **Security, Observability & Fleet Controls** — Scoped API keys (`read`/`operate`/`admin`), opt-in TOTP 2FA + recovery codes, CSRF Origin guard, SHA-256 hash-chained `audit.log` (`Verify chain`), `state.json` history & undo, Prometheus `/metrics`, Bidirectional Link Test, and Read-Only Fleet Drift detection.
- **Standalone Fleet Monitor, Telegram Relay & Signed Relayed Updates** — Independent `ratholemonitor.service` with hysteresis alerts and multi-path Telegram bot relay (`direct` / `proxy` / `node_tunnel`), adaptive fallback chain + EWMA backup endpoints, and Hub-relayed self-updates verified by Ed25519 `SHA256SUMS.sig`.
- **Fast KPI Dashboard, Paqet & Managed Xray UI** — 4 KPI cards, live filters, parallel status loading, inline carrier controls, Paqet client/server autofill + node Xray REALITY/XHTTP setup, VLESS URI generator, and TLS 1.3 cover scanner over SSH, REST Agent (`:8089`), or `reverse_ws`.

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/screenshots/dashboard-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/screenshots/dashboard.png">
  <img src="docs/assets/screenshots/dashboard.png" alt="RatholeHub v2.4.0 Dashboard" width="100%">
</picture>
</div>

<details>
<summary>📸 <b>More Hub screenshots (Auto-Tuner Dark/Light, Iran Server, Foreign Node, Carrier Modal, Routing Map, Ctrl+K, Settings)</b></summary>

| Auto-Tuner Dark (`#/tuner`) | Auto-Tuner & AI Profiles (`#/tuner`) |
|---|---|
| ![Auto-Tuner Dark](docs/assets/screenshots/tuner-dark.png) | ![Auto-Tuner Light](docs/assets/screenshots/tuner.png) |

| Iran Server (`#/server/<iran>`) | Foreign Node (`#/server/<node>`) |
|---|---|
| ![Iran Server](docs/assets/screenshots/server-iran.png) | ![Foreign Node](docs/assets/screenshots/server-node.png) |

| Service Controls Modal | Routing Topology (`#/routing`) |
|---|---|
| ![Service Controls](docs/assets/screenshots/service-controls.png) | ![Routing Map](docs/assets/screenshots/routing-map.png) |

| Command Palette (`⌘K / Ctrl+K`) | Settings (`#/settings`) |
|---|---|
| ![Command Palette](docs/assets/screenshots/command-palette.png) | ![Settings](docs/assets/screenshots/settings.png) |

</details>

## Update, rollback & advanced options

```bash
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --update
# or from an installed host:  sudo ratholectl update  /  sudo ratholenode update
```

Every update takes a pre-change snapshot (`/var/backups/rathole-manager/`), runs health checks, and auto-rolls back on failure.

> [!WARNING]
> **Updating from v2.0.3 or older?** Run `sudo RATHOLE_GH=l8PYGIT/RatholeEngine ratholectl update` (or `ratholenode update`) once to migrate from the old repository slug.

<details>
<summary>🔐 <b>REST &amp; Reverse WS Agent setup, private repo updates, manual rollback &amp; uninstall</b></summary>

```bash
# Direct REST Agent (:8089, Bearer auth, HTTPS supported)
sudo ratholectl agent on   # or: sudo install-agent.sh --role iran|node --port 8089

# Outbound Reverse WebSocket Agent (filtered/NAT nodes, zero inbound ports)
sudo ratholenode agent reverse "wss://<DOMAIN>/hub/ws/agent" "<NAME>" "<TOKEN>"
# or: sudo install-agent.sh --role node --reverse "wss://<DOMAIN>/hub/ws/agent" --name "<NAME>" --token "<TOKEN>"

# Private GitHub repository install / update
curl -fsSL -H "Authorization: Bearer <PAT>" https://raw.githubusercontent.com/owner/repo/main/install.sh | sudo bash -s -- --token <PAT> --panel ...
sudo bash tools/update-private.sh

# Snapshots, manual rollback & uninstall
sudo bash rathole-manager/update.sh --list-backups
sudo bash rathole-manager/update.sh --rollback [<timestamp>]
sudo bash bootstrap.sh --uninstall   # add --purge --yes to remove binaries & hub config
```

</details>

## Documentation

| Doc | Contents |
|---|---|
| [**Docs Site & Wiki**](https://l8pygit.github.io/RatholeEngine/) | Complete Persian + English MkDocs Material site & Wiki ([Troubleshooting](https://l8pygit.github.io/RatholeEngine/wiki/Troubleshooting/)) |
| [`docs/quickstart.md`](docs/quickstart.md) · [`en`](docs/quickstart.en.md) | Interactive install walkthrough & troubleshooting |
| [`docs/architecture.md`](docs/architecture.md) · [`en`](docs/architecture.en.md) | 4 roles, management plane (`ssh` / `api` / `reverse_ws`) & `state→regenerate→reload` |
| [`docs/transport-modes.en.md`](docs/transport-modes.en.md) · [`fa`](docs/transport-modes.md) | All 9 carriers, `paqet`, Managed Xray (`REALITY`/`XHTTP`), FRP, GRE & ingress modes |
| [`docs/traffic-flow.md`](docs/traffic-flow.md) · [`en`](docs/traffic-flow.en.md) | Layer-by-layer packet flow & SVG reference |
| [`docs/hub.en.md`](docs/hub.en.md) · [`fa`](docs/hub.md) | RatholeHub UI, `#/tuner`, REST & Reverse WS Agent, 2FA/RBAC, `/metrics`, Monitor Bot & security |
| [`docs/performance.md`](docs/performance.md) · [`en`](docs/performance.en.md) · [`README.fa.md`](docs/README.fa.md) | `rathole-tuner`, `rthprof1:` AI profiles, BBR/KCP tuning & full CLI reference |
| [`tools/telegram-bot-worker/`](tools/telegram-bot-worker/README.md) | Serverless Telegram announcer & Hub fleet monitor relay |
| [`CHANGELOG.md`](CHANGELOG.md) · [`en`](CHANGELOG.en.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) | Release notes (`v2.4.0`), tests, LF & code rules ([CoC](CODE_OF_CONDUCT.md)) |

## Community & Donate

📢 **[Telegram Channel — @l8PY4NET](https://t.me/l8PY4NET)** (releases & fastest support) · 🐙 **[GitHub Issues](https://github.com/l8PYGIT/RatholeEngine/issues)** (attach `ratholectl doctor`)

<a id="donate"></a>
| USDT (BEP-20 / BSC) | TON | TRX (Tron) |
|---|---|---|
| `0x2364898407e8A42DA554B909989cd9B28eE61314` | `UQCondoXRwQNt0fQvvmYGa_Fn39D9szjQH4eBqIcUd5r1yfH` | `TRhnkJFpj9uxA2aqUxapJAFhkzNPbfxKwp` |

---

## خلاصه‌ی فارسی

**RatholeEngine (`v2.4.0`)** یک سیستم تونل معکوس چند-موقعیتی روی **rathole + Nginx** است: یک سرور ایران (پشت یک دامنه، یک گواهی TLS و پورت `443`) جلوی چندین نود خارج قرار می‌گیرد و ترافیک بر اساس **path** هدایت می‌شود. علاوه‌بر ۹ حامل (**WebSocket/TLS**، **KCP+FEC**، **Plain**، **Noise**، **Backhaul SMUX**، **FRP**، **GRE لایه ۳**، **FRP+GRE** و **Paqet Direct PCK**) و **Managed Xray** (`REALITY+Vision` / `XHTTP` + اسکنر سایت کاور TLS 1.3)، در نسخهٔ `v2.4.0` قابلیت **Reverse WebSocket Agent (`reverse_ws`)** اضافه شده است تا نودهای پشت NAT یا با IP فیلترشده بدون هیچ پورت ورودی باز، خروجی به `/hub/ws/agent` هاب متصل شوند؛ همچنین موتور **تست و تیونر شبکه `rathole-tuner`** دارای **محافظ دوفازه‌ای Watchdog** (`--confirm-ttl 45` + `bench confirm`)، تشخیص انسداد UDP با `TCP_INFO` و ایمن‌سازی مسیر/کارت‌شبکه/بافرهای کرنل همراه با خروجی قابل‌تحلیل توسط هوش مصنوعی (**JSON + `rthprof1:`**) است. شروع سریع و مستندات کامل فارسی: [`docs/quickstart.md`](docs/quickstart.md) · [`docs/README.fa.md`](docs/README.fa.md) · [**@l8PY4NET**](https://t.me/l8PY4NET).
