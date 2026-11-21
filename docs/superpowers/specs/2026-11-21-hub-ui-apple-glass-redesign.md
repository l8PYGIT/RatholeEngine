# Hub UI Redesign Spec — macOS Sonoma/Sequoia Blue & Slate Glass + Raycast UX

## Goals
- Deliver a cohesive **Apple / Raycast** glassmorphic admin UI across all Hub views (`login`, `dashboard`, `server`, `routing`, `audit`, `settings`) while staying **100% build-free** (pure HTML/CSS/vanilla JS) and **100% offline** (no external CDN requests, strict CSP `default-src 'self'`).
- Provide **macOS Sonoma/Sequoia Blue** (`#0A84FF` dark / `#007AFF` light) + **Slate Glass** depth, full **Light & Dark** themes with OS `System` option, and tactile spring micro-interactions honoring `prefers-reduced-motion`.
- Keep the collapsible glass sidebar **minimal** (`Dashboard`, `Routing`, `Audit`, `Settings` + `⌘K / Ctrl+K` launcher + footer controls; **no server list** in sidebar).

## Key Architectural Upgrades
1. **Offline Typography:** Bundle variable `vazirmatn.woff2` inside `rathole-manager/ratholehub/ui/`, served from `hub.py` (`UI_FILES`) with `Cache-Control: public, max-age=86400`, and installed/preserved by `install-hub.sh` and `update.sh`.
2. **Native Top-Layer `<dialog>` Modals & Command Palette:** Replace fixed `div#modal` + manual focus trap with native `<dialog>` (`showModal()`, `closedby="any"` + fallback pointer light-dismiss, `overscroll-behavior: contain` on `dialog:modal` & `dialog::backdrop`, `@starting-style` + `transition-behavior: allow-discrete` + Firefox/Safari `data-closing` exit fallback). Add Raycast-style `⌘K / Ctrl+K` Command Palette (`#cmdk`) with keyboard navigation across servers, routes, and quick actions.
3. **Theme Architecture:** `<meta name="color-scheme" content="light dark">` + `:root:has(> head > meta[name="color-scheme"][...])` CSS reflection, instant FOUC-free head bootstrap, 2-state sidebar quick toggle, 3-state segmented Appearance control in Settings, and cross-tab `storage` listener.
4. **Dashboard & Table Filtering:** 4-card KPI strip (`#kpi_grid`), multi-criteria server filter toolbar (search, role, reachability, view mode), live inline filters on Iran/Node service tables and Audit log.
5. **Backward Compatibility:** Preserve all existing API endpoints, SSH/REST Agent behavior, XSS hardening (`data-*` delegation), and test-hooked JS function contracts (`tests/test_hub_provisioning.js`).
