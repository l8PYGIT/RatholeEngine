# Code Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix logical bugs, security vulnerabilities (permissions, predictable temp files, input validation), and CRLF/performance issues in `ratholectl` and `ratholenode`.

**Architecture:**
- Address bash logic errors (multi-variable local declaration in ratholenode, plain probe host extraction).
- Fix `gen_server_toml` and `gen_nginx_conf` TSV generation with CRLF stripping to eliminate `base64: invalid input` and fix test-harness test 9.
- Harden file permissions on state and config files (`chmod 600`), eliminate `/tmp/nginx_test.log` predictable file, and validate `domain` / `control-path` in `cmd_set`.
- Synchronize extra domains server blocks with Backhaul, proxy, and control-path blocks.

**Tech Stack:** Bash, Nginx, jq, systemd, rathole, backhaul.

---

### Task 1: Fix ratholenode logical bugs and code quality

**Files:**
- Modify: `rathole-manager/ratholenode:1780-1795` (local bhr/bhh/bhp & plain host probe)
- Modify: `rathole-manager/ratholenode:700` (mojibake)
- Modify: `rathole-manager/ratholenode:67` (export key)
- Modify: `rathole-manager/ratholenode:939` & `1445` (unused variables)

- [ ] **Step 1: Apply fixes in `ratholenode`**
  - Split `local bhr=...` and `local bhh=... bhp=...` onto separate lines.
  - In `adaptive_probe`, extract host and port from `${PLAIN_REMOTE:-$SERVER}`.
  - Fix mojibake `â€”` to `--`.
  - Fix `export "${key?}"`.
  - Remove unused variable declarations (`WS_PATH`, `main_bad`).
- [ ] **Step 2: Verify with shellcheck**
  - Run: `shellcheck.exe rathole-manager/ratholenode --severity=warning`
  - Expected: No warnings on line 1787 (SC2318), line 700 (SC1111), line 67 (SC2163).

---

### Task 2: Fix ratholectl TSV parsing, CRLF stripping, and extra_domains blocks

**Files:**
- Modify: `rathole-manager/ratholectl:396-420` (`gen_server_toml`)
- Modify: `rathole-manager/ratholectl:686-690`, `748-752` (`gen_nginx_conf` map generation)
- Modify: `rathole-manager/ratholectl:950-993` (`gen_nginx_conf` extra_domains server block)

- [ ] **Step 1: Refactor `gen_server_toml` to TSV + CRLF strip**
  - Replace `jq -r '.nodes[] | @base64'` and `_j()` subshells with clean `@tsv` stream and `read -r`.
- [ ] **Step 2: Strip CRLF in `gen_nginx_conf` maps**
  - Strip trailing `\r` from `n` and `p` in both `$backend_port` and `$direct_node` maps.
- [ ] **Step 3: Add missing blocks to `extra_domains` server block**
  - Include `${bh_block}`, `${proxy_block}`, and `${ctrl_path_block}` inside `NGINX2` template.
- [ ] **Step 4: Verify with test-harness**
  - Run: `bash rathole-manager/test-harness.sh`
  - Expected: Test 9 (`trk01 dar map`) PASSES; zero `base64: invalid input` errors.

---

### Task 3: Security hardening in ratholectl

**Files:**
- Modify: `rathole-manager/ratholectl:68-71` (`ensure_state`), `259-270` (`cmd_init`), `1056-1065` (`regenerate`), `1180-1193` (`cmd_set`), `2912-2935` (`menu`)

- [ ] **Step 1: Enforce secure file permissions (`chmod 700` dir, `chmod 600` state & TOMLs)**
  - Ensure `/etc/rathole-manager` is `0700` and `$STATE` is `0600` on creation and check.
- [ ] **Step 2: Fix `/tmp/nginx_test.log`**
  - Replace static `/tmp` path with `rth_mktemp` and cleanup.
- [ ] **Step 3: Add input validation to `cmd_set`**
  - Add regex validation for `domain` (`^[A-Za-z0-9_.-]+$`) and `control-path` (`/` or `^/[A-Za-z0-9_./-]{1,120}$`).
- [ ] **Step 4: Localize interactive variables in `menu()`**
  - Declare `local ch="" n="" ib="" ap="" k="" v="" args=()` in `menu()`.
- [ ] **Step 5: Run full test suite & shellcheck**
  - Run: `shellcheck.exe rathole-manager/ratholectl --severity=warning`
  - Run: `bash rathole-manager/test-harness.sh`
  - Expected: All test-harness assertions PASS.
