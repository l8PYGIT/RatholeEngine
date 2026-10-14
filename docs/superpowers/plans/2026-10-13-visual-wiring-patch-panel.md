# Visual Wiring Patch Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive SVG/CSS Network Patch Panel and Wiring Board in RatholeHub that visually represents end-to-end tunnel wiring from Ingress ports through carriers to foreign nodes and Xray services with live pulse animations and circuit inspection.

**Architecture:** Pure SVG and CSS patchboard layout embedded directly in RatholeHub (`app.js`, `app.css`, `i18n.js`) with zero external libraries. It maps Ingress ports (443, 8080, Direct-IP) ➔ Iran sockets ➔ Carrier cables (Bézier curves color-coded by carrier: WebSocket, KCP, Backhaul, Noise) ➔ Foreign node sockets ➔ Backend service ports (Xray). Clicking any cable or socket highlights the full circuit and displays an Inspector popup with live status.

**Tech Stack:** Pure Vanilla JavaScript (ES6+), SVG with CSS keyframe pulse animations, CSS Grid/Flexbox, Python 3 stdlib test runner.

**Spec:** User requirements from session 2026-10-13: Interactive patch panel visual wiring board with live monitoring and circuit inspection.

## Global Constraints
- Zero external libraries or npm dependencies (pure stdlib/vanilla JS & CSS).
- Responsive layout adapting to dark and light themes (`var(--bg)`, `var(--card)`, `var(--bd)`, etc.).
- Non-blocking DOM rendering with lightweight SVG paths.
- Preserves all existing functionality in `ratholectl`, `ratholenode`, and `hub.py`.

---

### Task 1: CSS Patch Panel Styles & Signal Pulse Animations
**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.css`

**Interfaces:**
- Produces CSS classes: `.patch-board`, `.patch-rack`, `.patch-socket`, `.cable-path`, `.cable-pulse`, `.circuit-highlight`, `.circuit-inspector`.

- [ ] **Step 1: Add cable color tokens and pulse keyframes in `app.css`**
- [ ] **Step 2: Add socket and rack card styling in `app.css`**
- [ ] **Step 3: Add circuit inspector floating badge and modal styles**
- [ ] **Step 4: Verify CSS syntax and rules**

---

### Task 2: i18n Localization Tokens for Wiring Board
**Files:**
- Modify: `rathole-manager/ratholehub/ui/i18n.js`

**Interfaces:**
- Produces i18n keys: `wb_title`, `wb_ingress`, `wb_tunnels`, `wb_nodes`, `wb_backend`, `wb_circuit`, `wb_status_up`, `wb_status_down`, `wb_inspect_hint`.

- [ ] **Step 1: Add Persian (fa) and Finglish/English translations in `i18n.js`**
- [ ] **Step 2: Verify `node -c rathole-manager/ratholehub/ui/i18n.js`**

---

### Task 3: Patchboard Data Model & Circuit Graph Builder
**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.js`

**Interfaces:**
- Produces function: `buildWiringModel()` returning `{ ingr: [...], iranSockets: [...], cables: [...], nodeSockets: [...], svcs: [...] }`

- [ ] **Step 1: Implement `buildWiringModel()` parsing live Iran & Node overviews**
- [ ] **Step 2: Implement Bézier curve routing generator `svgCableD(x1, y1, x2, y2)`**
- [ ] **Step 3: Unit test model parsing with Python/Node test**

---

### Task 4: Interactive SVG Patch Panel Renderer (`drawPatchBoard`)
**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.js`

**Interfaces:**
- Produces functions: `drawPatchBoard()`, `highlightCircuit(id)`, `resetCircuit()`, `showCircuitInspector(edge)`
- Updates `renderRouting()` to default or feature the interactive Patch Panel view.

- [ ] **Step 1: Implement SVG rack panels and socket renderers**
- [ ] **Step 2: Implement animated SVG cable paths with carrier colors and pulse markers**
- [ ] **Step 3: Implement click and hover handlers for instant circuit highlighting**
- [ ] **Step 4: Implement floating Circuit Inspector with quick action buttons**
- [ ] **Step 5: Verify JavaScript syntax with `node -c rathole-manager/ratholehub/ui/app.js`**

---

### Task 5: Compact Mini-Wiring Board for Server Details Pages
**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.js`

**Interfaces:**
- Produces function: `renderMiniWiring(serverName, ov)` displayed in `renderIran()` and `renderNode()`.

- [ ] **Step 1: Implement `renderMiniWiring()` generating a sleek single-server circuit ribbon**
- [ ] **Step 2: Inject into `renderIran()` under server header**
- [ ] **Step 3: Inject into `renderNode()` under server header**
- [ ] **Step 4: Verify syntax with `node -c rathole-manager/ratholehub/ui/app.js`**

---

### Task 6: End-to-End Verification & Live Playwright Screenshots
**Files:**
- Test: `tests/test_wiring_ui.py`
- Scratch: `C:\Users\NPC\.gemini\antigravity\brain\f12a37d6-a8c9-4b2d-b19c-a1be53ccbe24\scratch\capture_wiring.py`

- [ ] **Step 1: Run python unit tests and syntax verifications**
- [ ] **Step 2: Capture live screenshot of the new Patch Panel in `#routing` view**
- [ ] **Step 3: Capture live screenshot of circuit highlighting upon clicking a cable**
- [ ] **Step 4: Verify live UI in browser at `http://127.0.0.1:8099/#/routing`**
