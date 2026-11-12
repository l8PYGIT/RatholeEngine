# Documentation Website (Web Wiki) — Platform Choice & Setup

This page explains how RatholeEngine's docs become a **static documentation website**, which
platforms fit (including what **Marzban** uses), and how to build, preview and deploy it.

> Three documentation layers:
> 1. **GitHub Wiki** (`docs/wiki/`) — quick Persian knowledge base with `](Page)` links.
> 2. **Docs website** (this site) — unified `docs/` + wiki + English pages, search, light/dark theme.
> 3. **README/CHANGELOG** at the repo root — GitHub landing page and release notes.

---

## 1) What does Marzban use?

Marzban's documentation site (`gozargah.github.io/marzban`) is built with **VitePress**, a static-site
generator on top of Vue/Vite (site markup shows `#VPContent`, the Appearance toggle, `K` search, and the
`English / فارسی / Русский` locale switch). So if you want “exactly like Marzban”, VitePress is the answer.

This repo uses **MkDocs Material** instead because:

- The project is already **Python** (`hub.py`, `ratholeagent.py`, `tools/`), so the build runs in the same
  venv — no `node_modules` tree is added to the repo.
- Output is **fully static and offline** (no Google Fonts/CDN assets — important for users inside Iran).
- Built-in search, light/dark themes, RTL support and tabs/admonitions.
- Easier for bash/Python contributors to maintain than a Vue app.

Switching to VitePress later is mostly a config/nav change: both consume the same Markdown.

## 2) Platform comparison

| Platform | Stack | Build step? | Persian/RTL | Search | Best for |
|---|---|---|---|---|---|
| **MkDocs Material** | Python | yes (seconds) | ✅ excellent (`language: fa`) | ✅ built-in/offline | technical docs, Python/bash projects — **this repo** |
| **VitePress** | Node/Vue | yes | ✅ (`fa` locales) | ✅ | modern fast sites — **what Marzban uses** |
| **Docusaurus** | Node/React | yes | ✅ strong i18n | ✅ | large multi-version docs |
| **Astro Starlight** | Node/Astro | yes | ✅ | ✅ | fast, lightweight sites |
| **Docsify** | browser JS | no (renders MD at runtime) | ✅ | ✅ | quick wiki without build; weaker SEO |
| **GitBook / Notion (SaaS)** | hosted | no | ✅ | ✅ | non-technical teams; cloud-dependent |
| **GitHub Wiki** | GitHub | no | ✅ | weak | quick reference next to code — current layer |

For an Iran-facing audience, keep **all assets local** (fonts, icons, JS). Material does that with
`theme.font: false`; Docsify/VitePress can be configured the same way.

## 3) Building the site in this repo

Config lives at the repo root: [`mkdocs.yml`](../mkdocs.yml) (source `docs/`, output `site/`).
Landing page: [`docs/index.md`](index.md).

```bash
# 1) build environment (once)
python -m venv scratch/venv
scratch/venv/Scripts/python.exe -m pip install mkdocs-material   # on Linux: scratch/venv/bin/python

# 2) build
scratch/venv/Scripts/python.exe -m mkdocs build -f mkdocs.yml    # → site/

# 3) preview
scratch/venv/Scripts/python.exe -m mkdocs serve -f mkdocs.yml -a 127.0.0.1:8090
#   or serve the static output:  python -m http.server 8090 -d site
```

Notes:

- Wiki-style links `](Home)` in `docs/wiki/` are for GitHub's wiki; during the build
  [`tools/mkdocs_wiki_links.py`](../tools/mkdocs_wiki_links.py) rewrites them to real site paths and
  converts links that leave `docs/` (e.g. `../README.md`) to GitHub URLs.
- Mermaid fences render as code blocks; SVGs under `docs/assets/` are embedded directly.
- `site/` is gitignored — always rebuild from source.

## 4) Screenshots

Hub screenshots live in `docs/assets/screenshots/` (dashboard, Iran page, node page, service controls,
routing map, settings). They are captured from **mock mode** so no real inventory/token leaks:

```powershell
$env:RATHOLEHUB_MOCK="1"; $env:RATHOLEHUB_CONF="mock-conf.json"; $env:RATHOLEHUB_INV="mock-inv.json"
python rathole-manager/ratholehub/hub.py        # http://127.0.0.1:8088  (password: admin)
```

Then capture `#/dashboard`, `#/server/<name>`, `#/routing`, `#/settings` with a browser tool
(e.g. `agent-browser`) and drop the PNGs there. Both the site and the wiki reference these filenames.

## 5) Deployment

| Option | Pros | Caveat |
|---|---|---|
| **GitHub Pages** (`gh-pages`) | free, Actions-native | this repo: **<https://l8pygit.github.io/RatholeEngine/>** — workflow `.github/workflows/docs.yml` |
| **Cloudflare Pages** | fast, auto-build from repo | may be slow/restricted in Iran; custom domain + cache helps |
| **Netlify / Vercel** | simple | same reachability caveats |
| **On the Iran server behind nginx** | same domain/cert, no new service | best for the Iranian audience; serve static output under e.g. `/docs/` and set `site_url` to that subpath |
| **Offline bundle** | always available | ship `site/` in a release/bundle and open with a local `python -m http.server` |

Example nginx block (only if `/docs` is free):

```nginx
location ^~ /docs/ {
    alias /var/www/rathole-docs/;
    try_files $uri $uri/ /docs/index.html;
}
```

For GitHub Pages, a short workflow that sets up Python, installs `mkdocs-material`, and uploads `site/`
as the Pages artifact is enough.

## 6) Summary

- This repo: **MkDocs Material** — simple, offline, Python-native, RTL + search out of the box.
- “Exactly like Marzban”: **VitePress** (Vue) — same Markdown content, different config/nav.
- Lightweight no-build wiki: **Docsify**; large multi-version docs: **Docusaurus**.
