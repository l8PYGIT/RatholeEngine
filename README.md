<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/banner-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/banner-light.png">
  <img src="docs/assets/banner-dark.png" alt="RatholeEngine — Multi-Location Reverse Tunnel System" width="100%">
</picture>

**Multi-location reverse-tunnel engine built on `rathole` + `Nginx`** — _One port · one domain · 8 carriers · central Web Hub_

[![CI](https://github.com/l8PYGIT/RatholeEngine/actions/workflows/ci.yml/badge.svg)](https://github.com/l8PYGIT/RatholeEngine/actions/workflows/ci.yml)
[![Docs](https://github.com/l8PYGIT/RatholeEngine/actions/workflows/docs.yml/badge.svg)](https://l8pygit.github.io/RatholeEngine/)
[![Release](https://img.shields.io/github/v/release/l8PYGIT/RatholeEngine?style=flat-square&sort=semver&color=7c3aed)](https://github.com/l8PYGIT/RatholeEngine/releases/latest)
[![License](https://img.shields.io/github/license/l8PYGIT/RatholeEngine?style=flat-square&color=2563eb)](LICENSE)
[![Stars](https://img.shields.io/github/stars/l8PYGIT/RatholeEngine?style=flat-square&color=16a34a)](https://github.com/l8PYGIT/RatholeEngine/stargazers)
[![Telegram](https://img.shields.io/badge/Telegram-%40l8PY4NET-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://t.me/l8PY4NET)

[**Docs Site**](https://l8pygit.github.io/RatholeEngine/) · [**Wiki**](https://l8pygit.github.io/RatholeEngine/wiki/Home/) · [**Quick Start**](#quick-start) · [**Transport Modes**](#transport--ingress-modes) · [**RatholeHub**](#ratholehub-web-panel-v205) · [**فارسی**](docs/README.fa.md) · [**Telegram**](https://t.me/l8PY4NET)

</div>

---

## Architecture

One **Iran edge server** behind a single domain, TLS certificate, and public `:443` port fronts many **foreign nodes** connected via outbound reverse tunnels (`map $uri $backend_port` in Nginx). The system spans **four roles**: Iran Panel ([`ratholectl`](rathole-manager/ratholectl)), Foreign Node ([`ratholenode`](rathole-manager/ratholenode)), Central Web Hub ([`hub.py`](rathole-manager/ratholehub/hub.py), stdlib Python), and an optional **REST Agent** ([`ratholeagent.py`](rathole-manager/ratholeagent.py), `:8089`). Every mutation edits state only, regenerates configs in place via `rth_commit_config` (preserving inodes for hot-reload), runs `nginx -t`, and reloads safely with automatic rollback.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/architecture.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/architecture-light.svg">
  <img src="docs/assets/architecture.svg" alt="RatholeEngine Architecture" width="100%">
</picture>

## Quick start

Run the one-command interactive installer (`Enter` picks latest release; choose role `1` Iran Panel, `2` Foreign Node, `3` Update, or `7` Uninstall):

```bash
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash
```

> [!TIP]
> **Step-by-step interactive walkthrough** (every prompt, expected answer, and troubleshooting table): [`docs/quickstart.md`](docs/quickstart.md) · [English](docs/quickstart.en.md).

<details>
<summary>⚙️ <b>Non-interactive flags, version pinning &amp; essential panel commands</b></summary>

```bash
# Iran panel (non-interactive)
curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --panel \
  --domain panel.example.ir \
  --fullchain /root/cert/panel.example.ir/fullchain.pem \
  --key       /root/cert/panel.example.ir/privkey.pem

# Foreign node (keep node flags after `--`; pass `--release v2.1.0` before `--panel`/`--node` to pin)
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

*Ingress modes (not tunnel carriers):* **Game / SNI** (L4 `:443` passthrough), **Direct-IP** (`:8081` + `X-Cdn-Id`), **Proxy** (`/<name>/` upstream), and **Fakeweb** (`:8080`). Full details: [`docs/transport-modes.en.md`](docs/transport-modes.en.md) · [فارسی](docs/transport-modes.md).

## RatholeHub web panel (`v2.1.0`)

- **Apple Glass UI (100% offline, stdlib Python)** — Light / Dark / System themes, bundled `vazirmatn.woff2`, Persian RTL / English LTR, native `<dialog>` modals, and **`⌘K / Ctrl+K` Command Palette**.
- **Fast KPI Dashboard & Two-Sided Sync** — 4 KPI cards, live filters, parallel status loading with TTL cache, inline per-node carrier dropdown with auto-revert on node failure, and compact `⋯` service controls (carrier modal, `doctor` check, VLESS link generator, peer jump, dual-side delete).
- **SSH or REST Agent** — drives servers via strict regex-validated `argv` lists over key-auth SSH or token-protected HTTP(S) REST Agent (`:8089`).

<div align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/screenshots/dashboard-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/screenshots/dashboard.png">
  <img src="docs/assets/screenshots/dashboard.png" alt="RatholeHub v2.1.0 Dashboard" width="100%">
</picture>
</div>

<details>
<summary>📸 <b>More Hub screenshots (Iran Server, Foreign Node, Carrier Modal, Routing Map, Ctrl+K, Settings)</b></summary>

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
<summary>🔐 <b>REST Agent setup, private repo updates, manual rollback &amp; uninstall</b></summary>

```bash
# Optional SSH-free REST Agent (:8089, Bearer auth, HTTPS supported)
sudo ratholectl agent on   # or: sudo install-agent.sh --role iran|node --port 8089

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
| [`docs/architecture.md`](docs/architecture.md) · [`en`](docs/architecture.en.md) | 4 roles, management plane & `state→regenerate→reload` |
| [`docs/transport-modes.en.md`](docs/transport-modes.en.md) · [`fa`](docs/transport-modes.md) | All 8 carriers, FRP `7000/TCP+UDP`, GRE, Backhaul & ingress modes |
| [`docs/traffic-flow.md`](docs/traffic-flow.md) · [`en`](docs/traffic-flow.en.md) | Layer-by-layer packet flow & SVG reference |
| [`docs/hub.en.md`](docs/hub.en.md) · [`fa`](docs/hub.md) | RatholeHub UI, REST Agent & security model |
| [`docs/performance.md`](docs/performance.md) · [`README.fa.md`](docs/README.fa.md) | BBR/KCP tuning & full Persian CLI reference |
| [`tools/telegram-bot-worker/`](tools/telegram-bot-worker/README.md) | Serverless Telegram announcer (GitHub Actions reusable workflow + Cloudflare Worker) |
| [`CHANGELOG.md`](CHANGELOG.md) · [`CONTRIBUTING.md`](CONTRIBUTING.md) | Release notes (`v2.1.0`), tests, LF & code rules ([CoC](CODE_OF_CONDUCT.md)) |

## Community & Donate

📢 **[Telegram Channel — @l8PY4NET](https://t.me/l8PY4NET)** (releases & fastest support) · 🐙 **[GitHub Issues](https://github.com/l8PYGIT/RatholeEngine/issues)** (attach `ratholectl doctor`)

<a id="donate"></a>
| USDT (BEP-20 / BSC) | TON | TRX (Tron) |
|---|---|---|
| `0x2364898407e8A42DA554B909989cd9B28eE61314` | `UQCondoXRwQNt0fQvvmYGa_Fn39D9szjQH4eBqIcUd5r1yfH` | `TRhnkJFpj9uxA2aqUxapJAFhkzNPbfxKwp` |

---

## خلاصه‌ی فارسی

**RatholeEngine** یک سیستم تونل معکوس چند-موقعیتی روی **rathole + Nginx** است: یک سرور ایران (پشت یک دامنه، یک گواهی TLS و پورت `443`) جلوی چندین نود خارج قرار می‌گیرد و ترافیک بر اساس **path** هدایت می‌شود. شامل ۴ نقش است: پنل ایران (`ratholectl`)، نود خارج (`ratholenode`)، پنل وب **RatholeHub** (رابط شیشه‌ای Apple Glass در `v2.1.0`، تم روشن/تاریک، پالت فرمان `Ctrl+K`، کارت‌های KPI، بارگذاری موازی و همگام‌سازی صریح دوطرفه) و **REST Agent** اختیاری (`:8089` بدون SSH). از ۸ حامل (**WebSocket/TLS**، **KCP+FEC**، **Plain**، **Noise**، **Backhaul SMUX**، **FRP روی پورت `7000/TCP+UDP`**، **GRE لایه ۳** و **FRP+GRE**) پشتیبانی می‌کند. شروع سریع و مستندات کامل فارسی: [`docs/quickstart.md`](docs/quickstart.md) · [`docs/README.fa.md`](docs/README.fa.md) · [**@l8PY4NET**](https://t.me/l8PY4NET).
