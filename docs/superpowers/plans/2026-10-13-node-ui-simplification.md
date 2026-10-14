# Node UI Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify foreign node management in RatholeHub by replacing 15+ scattered buttons with a unified services table, 1-click connection presets, and a collapsible diagnostics/tools panel.

**Architecture:** Frontend refactoring in `ratholehub/ui/`:
1. `app.js`: `renderNode` renders a clean overview card, a 1-click Preset switch bar, a unified table merging Rathole and Backhaul services with carrier badges, and moves diagnostic/low-frequency buttons into a native `<details>` collapsible section.
2. `app.css`: Adds styling for presets pills, lane badges, and the diagnostics accordion.
3. `i18n.js`: Provides Persian and English labels for presets and the unified service dialog.

**Tech Stack:** Vanilla JavaScript (ES6+), CSS3 (CSS Custom Properties), HTML5 `<details>` / `<summary>`, Python standard library (test suite).

**Spec:** Progressive disclosure and component consolidation based on UI-UX Pro Max recommendations.

## Global Constraints
- No npm / pip dependencies (stdlib Python + vanilla JS/CSS).
- Preserves all existing REST API endpoints and backend commands.
- RTL / LTR bilingual support maintained across Persian and English.
- Clean LF line endings.

---

### Task 1: Add i18n Keys for Presets and Diagnostics

**Files:**
- Modify: `rathole-manager/ratholehub/ui/i18n.js`

- [ ] **Step 1: Add localization tokens for new UI elements**
Add the following keys to both `fa` and `en` in `i18n.js`:
- `diag_tools`: "ابزارهای عیب‌یابی و لاگ‌ها" / "Diagnostics & Tools"
- `preset_title`: "پروفایل‌های سریع" / "Quick Presets"
- `preset_ws`: "🚀 استاندارد (WS)" / "🚀 Standard (WS)"
- `preset_kcp`: "🛡️ ضد اختلال (KCP)" / "🛡️ Resilient (KCP)"
- `preset_bh`: "⚡ ترافیک بالا (Mux)" / "⚡ High-Load (Mux)"
- `unified_services`: "سرویس‌ها و پورت‌ها" / "Services & Inbound Ports"
- `l_lane`: "نوع حامل (Lane)" / "Carrier Lane"
- `lane_standard`: "استاندارد (Rathole)" / "Standard (Rathole)"
- `lane_mux`: "مالتی‌پلکس (Backhaul)" / "Multiplexed (Backhaul)"

- [ ] **Step 2: Verify i18n dictionary syntax**
Run syntax check via node or python to ensure no trailing comma syntax errors.

- [ ] **Step 3: Commit Task 1**
```bash
git add rathole-manager/ratholehub/ui/i18n.js
git commit -m "feat(ui): add i18n keys for node presets and diagnostics"
```

---

### Task 2: Add CSS Styling for Presets and Collapsible Diagnostics

**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.css`

- [ ] **Step 1: Add CSS rules for presets bar and diagnostics details**
Add:
- `.preset-bar`: flex container for quick preset buttons.
- `.diag-sec`: styled native `<details>` with clean `<summary>` toggle, border, and background.
- `.diag-sec[open] summary`: visual cue when expanded.
- `.lane-badge`: subtle badge indicating Mux vs Standard in the unified table.

- [ ] **Step 2: Verify responsive behavior**
Ensure buttons wrap smoothly on mobile screens (<600px).

- [ ] **Step 3: Commit Task 2**
```bash
git add rathole-manager/ratholehub/ui/app.css
git commit -m "feat(ui): style preset buttons and diagnostics accordion"
```

---

### Task 3: Refactor renderNode in app.js for Progressive Disclosure

**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.js:462-520`
- Modify: `rathole-manager/ratholehub/ui/app.js:1178-1190`

- [ ] **Step 1: Unify Services & Backhaul into a single table**
Merge `ov.services` and `ov.backhaul_services` into one unified list:
- Display service name with status dot.
- Display inbound port.
- Display Carrier Lane badge (`Standard` vs `Mux / Backhaul`).
- Delete action automatically invokes `rm_svc` or `rm_bh_svc` depending on lane.

- [ ] **Step 2: Update addSvc modal to support selecting Lane**
Update `addSvc` to offer a dropdown selecting standard Rathole vs Backhaul Mux.

- [ ] **Step 3: Move diagnostics into collapsible details element**
Move `logs`, `backhaul_logs`, `backhaul_status`, `watchdog_status`, `adaptive_status`, `adaptive_test`, and `migrate` into `<details class="diag-sec"><summary>${t('diag_tools')}</summary>...buttons...</details>`.

- [ ] **Step 4: Add Quick Presets Bar**
Render quick buttons at the top of the node card:
- Standard WS: sets carrier to 'ws'.
- Resilient KCP: opens `kcpOnNode`.
- High-Load Mux: opens `bhOnNode`.

- [ ] **Step 5: Verify app.js syntax and run automated tests**
Run Python hub tests and ensure `app.js` loads cleanly.

- [ ] **Step 6: Commit Task 3**
```bash
git add rathole-manager/ratholehub/ui/app.js
git commit -m "refactor(ui): streamline node view with unified services and progressive disclosure"
```

---

### Task 4: Verification and Smoke Testing

**Files:**
- Test: `tests/test_hub.py`

- [ ] **Step 1: Run unit tests**
Execute `python -m unittest tests/test_hub.py`.

- [ ] **Step 2: Check for regressions across all hub endpoints**
Verify mock mode runs cleanly without JS syntax or template errors.
