# Implementation Plan: Ruthless Audit Remediation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all security flaws, memory leaks, XSS risks, uninstaller secret leaks, state inode preservation violations, watchdog flapping, and installer edge-case bugs identified in the whole-project audit.

**Architecture:**
- Backend: Harden `hub.py` rate limiting with bounded memory pruning and loopback-only `X-Real-IP` trust; clean dead code in `hubcmds.py`.
- Frontend: Harden `ui/app.js` with `'` -> `&#39;` escaping and ensure all dynamic server/node variables in HTML templates are escaped.
- Orchestration: Replace `mv` with `rth_commit_config` on `state.json` mutations in `ratholectl` to preserve inode; add path-traversal & symlink checks to `cmd_restore`.
- Node Reliability: Add a consecutive failure threshold (3 failures) to `ratholenode` watchdog probe to eliminate single-packet-drop flapping.
- Installers: Secure uninstallation of secret config files in `uninstall-node.sh` and robust binary search in `install-node.sh`.

**Tech Stack:** Bash (`set -uo pipefail`), Python 3 (standard library only), Vanilla JS / HTML.

---

### Task 1: `hub.py` & `hubcmds.py` Security and Memory Hardening

**Files:**
- Modify: `rathole-manager/ratholehub/hub.py:26-48`, `hub.py:939-950`, `hub.py:445-446`
- Modify: `rathole-manager/ratholehub/hubcmds.py:447-449`
- Modify: `tests/test_hub.py`

**Interfaces:**
- `login_allowed(ip)` with bounded dictionary pruning
- Only trust `X-Real-IP` when `self.client_address[0]` in `("127.0.0.1", "::1")`

- [x] **Step 1: Write unit tests in `tests/test_hub.py` for login rate limiter pruning and IP trust**
- [x] **Step 2: Run test to verify failure**
- [x] **Step 3: Implement bounded pruning in `_LOGIN_FAILS` and trusted peer check in `hub.py`**
- [x] **Step 4: Remove dead `action == "logs"` code in `hubcmds.py` and duplicate comment in `hub.py`**
- [x] **Step 5: Run tests to verify all 35+ tests pass**

---

### Task 2: Frontend DOM Hygiene & XSS Prevention (`ui/app.js`)

**Files:**
- Modify: `rathole-manager/ratholehub/ui/app.js:17`, `app.js:1026-1045`, `app.js:1086`

**Interfaces:**
- `h(t)` escapes `&`, `<`, `>`, `"`, and `'` (`&#39;`)

- [x] **Step 1: Update `h(t)` to include `'` -> `&#39;`**
- [x] **Step 2: Escape `${h(n)}` in `domainTls` and `portsModal` template headers and action handlers**
- [x] **Step 3: Verify JS syntax**

---

### Task 3: Uninstaller Secrets Cleanup (`uninstall-node.sh` & `uninstall-panel.sh`)

**Files:**
- Modify: `rathole-manager/uninstall-node.sh:50-55`
- Modify: `rathole-manager/uninstall-panel.sh:95-101`

- [x] **Step 1: Update `uninstall-node.sh` to remove `services.conf`, `bh-services.conf`, `upstreams.conf`, `watchdog.env`, `failover.state`, `adaptive.env`, `adaptive-state.json`**
- [x] **Step 2: Clean `/etc/rathole` directory completely on uninstall**
- [x] **Step 3: Verify with ShellCheck**

---

### Task 4: State Invariants & Inode Preservation in `ratholectl`

**Files:**
- Modify: `rathole-manager/ratholectl:163-180`, `ratholectl:280`, `ratholectl:341`, `ratholectl:354`, `ratholectl:1169-1184`, `ratholectl:1271-1272`, `ratholectl:1288-1294`, `ratholectl:1582`
- Modify: `rathole-manager/ratholenode:100`

- [x] **Step 1: Replace `mv "$tmp" "$STATE"` with `rth_commit_config "$tmp" "$STATE" 600` in `state_set()`, `cmd_add()`, `cmd_rm()`, `cmd_rename()`, `cmd_rotate()`**
- [x] **Step 2: Harden `cmd_restore()` in `ratholectl` with symlink, pipe, and path traversal checks, plus `chmod 600 "$STATE"` and `chmod 700 "$(dirname "$STATE")"`**
- [x] **Step 3: Fix unused variables in `ratholectl` (`field`, `on`, `off`) and `ratholenode` (`_self`)**
- [x] **Step 4: Run integration test harness `test-harness.sh` to confirm zero regression**

---

### Task 5: Watchdog Flapping Prevention in `ratholenode`

**Files:**
- Modify: `rathole-manager/ratholenode:1395-1413`

- [x] **Step 1: Add consecutive probe failure counter in `wd_check_one` (require at least 3 consecutive probe failures before restarting active service)**
- [x] **Step 2: Reset counter on successful probe**
- [x] **Step 3: Run `test_node_hardening.sh` to confirm watchdog behavior**

---

### Task 6: Multi-Distro & Robustness in Installers & Hardening Tests

**Files:**
- Modify: `rathole-manager/install-node.sh:63-68`, `install-node.sh:79`
- Modify: `rathole-manager/common.sh:243`
- Modify: `rathole-manager/update.sh:93`
- Modify: `tests/test_node_hardening.sh:56`, `tests/test_node_hardening.sh:69`

- [x] **Step 1: In `install-node.sh`, use `find "$tmp" -type f -name rathole` for robust extraction and remove duplicate `SCRIPT_DIR`**
- [x] **Step 2: In `common.sh`, check `[ -f "$bin" ]` instead of `[ -x "$bin" ]` in `install_backhaul_core`**
- [x] **Step 3: In `update.sh`, replace unquoted array split with `read -ra`**
- [x] **Step 4: In `tests/test_node_hardening.sh`, fix case pattern and convert grep to `grep -F`**
- [x] **Step 5: Run full test suite and ShellCheck to verify zero errors and warnings**
