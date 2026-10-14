# Implementation Plan: RatholeHub UI/UX Modernization & Remediation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the RatholeHub UI/UX: convert Finglish strings to clean, authentic Persian in `DICT.fa`, add modern Persian typography and RTL styling, eliminate disruptive raw terminal dump modals on status actions, disambiguate identical button names, separate Danger Zone actions, replace browser `confirm()` with in-app modals, and add missing system status indicators for foreign nodes.

**Architecture:**
- Frontend Translation & Typography: Complete update of `ui/i18n.js` `DICT.fa` with authentic Persian and proper BiDi support. Embed Vazirmatn font stack in `ui/app.css` and add language/theme switches to the login view.
- Interaction Flow: Refactor `run(n, a, args)` in `ui/app.js` to avoid full-screen `outModal` popups for routine actions, show clean inline/toast feedback, and implement `confirmModal(title, message, onOk)` to replace native `window.confirm()`.
- Server Pages Overhaul:
  - Disambiguate duplicate `+ service` buttons in `ui/app.js` across Rathole lane, Backhaul lane, and Upstreams.
  - Add Node system status & daemon indicators in `renderNode()`.
  - Fix string concatenation bugs (`backhaul ${t('status')}`, `${m.live||'unknown'}`).
  - Add visual Danger Zone section for destructive actions (`del_server`, `restart`, `del_up`).

**Tech Stack:** Vanilla JS (ES6+), Vanilla CSS (Custom Properties, Flexbox/Grid), Standard HTML5, Zero external npm/pip dependencies.

---

### Task 1: Complete Translation Overhaul (Finglish $\to$ Authentic Persian & BiDi Typography)

**Files:**
- Modify: `rathole-manager/ratholehub/ui/i18n.js`
- Modify: `rathole-manager/ratholehub/ui/app.css`
- Modify: `rathole-manager/ratholehub/ui/app.js`

- [ ] **Step 1: Replace all Finglish entries in `DICT.fa` (`ui/i18n.js`) with authentic, professional Persian terminology.**
- [ ] **Step 2: Add font stack `"Vazirmatn", "Segoe UI", Tahoma, system-ui, sans-serif` in `ui/app.css` and refine RTL layout rules.**
- [ ] **Step 3: Add language toggle and theme toggle buttons to the login screen in `ui/app.js:shell()`.**
- [ ] **Step 4: Verify JS syntax with `node -c` or browser inspection.**

---

### Task 2: Interaction Flow & Modal Hardening (Eliminate Terminal Dump Modals & Native Confirms)

**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.js`
- Modify: `rathole-manager/ratholehub/ui/app.css`

- [ ] **Step 1: Implement `confirmModal(title, msg, onOk, danger=false)` in `ui/app.js` and replace raw `window.confirm()` calls.**
- [ ] **Step 2: Refactor `run(n, a, args)` so routine actions and status checks show clear toast or inline feedback without popping up raw CLI `outModal` when successful.**
- [ ] **Step 3: Ensure errors still present informative feedback without corrupting layout.**
- [ ] **Step 4: Verify modal interaction in browser.**

---

### Task 3: Foreign Node Management Page Fixes (`renderNode`)

**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.js`
- Modify: `rathole-manager/ratholehub/ui/i18n.js`

- [ ] **Step 1: Disambiguate duplicate `+ service` buttons in `renderNode()` to use clear distinct labels (`+ سرویس رتهول`, `+ سرویس بک‌هال`, `+ سرویس آپ‌استریم`).**
- [ ] **Step 2: Add Node System Status card showing `rathole-client.service` and `backhaul-client.service` status and versions.**
- [ ] **Step 3: Fix string concatenation bugs (`backhaul ${t('status')}`, `${h(m.live||'unknown')}`).**
- [ ] **Step 4: Group destructive actions (`del_server`, `restart_tunnel`, `del_up`) into a distinct Danger Zone.**
- [ ] **Step 5: Verify foreign node view in browser.**

---

### Task 4: Iran Server Management Page Fixes (`renderIran`)

**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.js`
- Modify: `rathole-manager/ratholehub/ui/app.css`

- [ ] **Step 1: Improve Carrier cards visual distinction between enabled/disabled states in dark mode.**
- [ ] **Step 2: Refactor table actions in Nodes & Services table into cleaner responsive buttons.**
- [ ] **Step 3: Fix form row layout in modals so labels and inputs maintain comfortable proximity on wide screens.**
- [ ] **Step 4: Verify Iran server view in browser.**

---

### Task 5: Final Verification & Visual Regression Testing

**Files:**
- Verify: `rathole-manager/ratholehub/ui/`
- Run: Mock hub browser subagent inspection across both pages, all modals, light and dark themes, and RTL/LTR switching.

- [ ] **Step 1: Launch mock hub on port 8089 and use browser subagent to test all modified views.**
- [ ] **Step 2: Verify zero console errors, zero syntax errors, and flawless RTL alignment.**
- [ ] **Step 3: Run existing unit test suite (`python tests/test_hub.py`) to ensure zero backend regression.**
