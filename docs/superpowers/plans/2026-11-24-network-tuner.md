# Network, Kernel & Tunnel Auto-Tuner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `rathole-tuner`, a zero-dependency Python 3 stdlib bidirectional network, kernel, MTU/MSS, offload, qdisc, buffer, tunnel-carrier, and non-kernel benchmark and auto-tuning engine integrated with `ratholectl`, `ratholenode`, installers/updater, and `RatholeHub` (`#/tuner`).

**Architecture:** Modular split inside `rathole-manager/tuner/` pairing an ephemeral HMAC-SHA256 `TunerResponder` (`--listen`) with a bidirectional `TunerOrchestrator` (`--peer`), protected on both sides by atomic snapshots and an independent Dead-Man's-Switch `WatchdogController`, emitting PII-sanitized `rathole.netprofile.v1` JSON and `rthprof1:...` gzip+Base64url datacenter profiles.

**Tech Stack:** Python 3 stdlib only (no `pip`), Bash (`set -uo pipefail`), vanilla JS / CSS / HTML (Hub UI), Node test runner (`node --test`), `unittest`, `shellcheck`.

**Spec:** [2026-11-24-network-tuner-design.md](../specs/2026-11-24-network-tuner-design.md)

## Global Constraints

- Pure Python 3 stdlib only (`rathole-manager/tuner/` and `rathole-manager/ratholehub/`).
- No mandatory `iperf3`, `mtr`, or `netperf`; Linux tools invoked exclusively via `subprocess.run(..., shell=False)` with graceful `unsupported` fallback on virtualized/restricted hosts.
- Strict LF (`\n`) line endings on every file.
- Bash scripts use `set -uo pipefail` and pass `bash -n` + `shellcheck --shell=bash --severity=error --exclude=SC1091`.
- Control channel enforces HMAC-SHA256, `60s` replay window, nonce deduplication, `1 MiB` frame cap, fixed action allow-list, and zero shell execution.
- Profiles enforce `schema == "rathole.netprofile.v1"`, `rthprof1:` prefix (`<= 65536` chars encoded, `<= 524288` bytes decompressed), `SHA-256` integrity hash, PII stripping by default, strict declarative allow-list validation, `10% RAM` (max `64 MiB`) socket buffer cap, and MTU floor (`>= 1280` IPv6 / `>= 576` IPv4).
- `ratholeagent.py` `ALLOWED_BINARIES` stays unchanged; remote Hub execution uses `ratholectl bench ...` and `ratholenode bench ...`.
- `hubcmds.py` uses `\Z`-anchored regexes and puts all mutators in `WRITE_ACTIONS`; `hub.py` masks HMAC session tokens in audit logs.

---

### Task 1: Core Constants, HMAC Protocol & Portable Profile Codec (`rthprof1:`)

**Files:**
- Create: `rathole-manager/tuner/__init__.py`
- Create: `rathole-manager/tuner/protocol.py`
- Create: `rathole-manager/tuner/profile.py`
- Test: `tests/test_tuner_core.py`

**Interfaces:**
- Produces:
  - `tuner/__init__.py`: `TUNER_VERSION`, `SCHEMA_VERSION`, `PROFILE_PREFIX`, `MAX_FRAME_BYTES`, `MAX_PROFILE_B64_LEN`, `MAX_PROFILE_JSON_BYTES`, `DEFAULT_CTRL_PORT`, `DEFAULT_DATA_PORT`, `ALLOWED_ACTIONS`
  - `tuner/protocol.py`: `ProtocolError`, `canonical_json_bytes(obj)`, `sign_frame(...)`, `verify_frame(...)`, `send_frame(sock, frame)`, `recv_frame(sock, max_bytes=MAX_FRAME_BYTES)`, `ControlClient`
  - `tuner/profile.py`: `ProfileValidationError`, `ALLOWED_QDISCS`, `ALLOWED_OFFLOADS`, `ALLOWED_CC`, `ALLOWED_SYSCTL_SPEC`, `compute_ram_buffer_cap(ram_mb)`, `clamp_config_for_ram(side_cfg, ram_mb)`, `sanitize_pii(obj)`, `compute_integrity_sha256(profile)`, `build_profile(...)`, `validate_profile(profile, host_ram_mb=None, verify_sha=True)`, `encode_profile_b64(profile)`, `decode_profile_b64(text, verify_sha=True)`, `load_profile_any(spec, verify_sha=True)`

- [x] **Step 1:** Write `tests/test_tuner_core.py` testing HMAC sign/verify, replay/stale/tamper/oversize rejection, unknown action rejection, canonical JSON + `rthprof1:` encode/decode round-trip, zip-bomb & length enforcement, PII stripping, and strict allow-list validation.
- [ ] **Step 2:** Run `python -m unittest tests/test_tuner_core.py -v` and confirm failure before implementation.
- [ ] **Step 3:** Implement `tuner/__init__.py`, `tuner/protocol.py`, `tuner/profile.py`.
- [ ] **Step 4:** Re-run `python -m unittest tests/test_tuner_core.py -v` -> PASS.
- [ ] **Step 5:** Commit Task 1.

---

### Task 2: 5D Scoring, System State / Snapshot / Watchdog, Non-Kernel Audit & Persistent Apply/Rollback

**Files:**
- Create: `rathole-manager/tuner/scoring.py`
- Create: `rathole-manager/tuner/sysstate.py`
- Create: `rathole-manager/tuner/watchdog.py`
- Create: `rathole-manager/tuner/audit.py`
- Create: `rathole-manager/tuner/apply.py`
- Test: `tests/test_tuner_core.py`

**Interfaces:**
- Consumes: `tuner/__init__.py`, `tuner/profile.py` (`validate_profile`, `clamp_config_for_ram`, `compute_ram_buffer_cap`, `load_profile_any`, `ALLOWED_SYSCTL_SPEC`)
- Produces:
  - `tuner/scoring.py`: `GOAL_WEIGHTS`, `raw_throughput(metrics)`, `check_hard_fail(metrics, baseline=None)`, `score_trials(trials, baseline_id="baseline")`, `diagnose_findings(baseline, winner, pmtu_info, audit_iran=None, audit_node=None)`
  - `tuner/sysstate.py`: `SysDriver`, `RealLinuxDriver`, `MockSysDriver`, `discover_capabilities(driver, peer_ip="")`, `capture_snapshot(driver, iface, peer_ip="", save_path=None)`, `apply_candidate(driver, config, iface, peer_ip="", session_id="tuner", ram_mb=None, ipv6_active=False)`, `restore_snapshot(driver, snapshot, session_id="tuner")`, `read_tcp_info(sock)`, `read_net_counters(driver, iface)`
  - `tuner/watchdog.py`: `WatchdogController` (`arm`, `heartbeat`, `disarm`) + subprocess entry point
  - `tuner/audit.py`: `run_non_kernel_audit(driver, role="iran", paths=None)`
  - `tuner/apply.py`: `apply_persistent(driver, profile, side="iran", paths=None)`, `apply_boot(driver, paths=None)`, `rollback_persistent(driver, paths=None)`, `tuner_status(driver, paths=None)`

- [ ] **Step 1:** Extend `tests/test_tuner_core.py` with tests for 5D goal scoring, Hard-Fail Gate, `MockSysDriver` snapshot/apply/revert + 10% RAM cap + IPv6 MTU floor, real subprocess Watchdog TTL expiration restore, non-kernel nginx/xray/governor audit findings, and persistent apply/rollback (`99-rathole-reserved-ports.conf` preservation + `rathole-net-tune.service`).
- [ ] **Step 2:** Run `python -m unittest tests/test_tuner_core.py -v` and confirm failure.
- [ ] **Step 3:** Implement `scoring.py`, `sysstate.py`, `watchdog.py`, `audit.py`, `apply.py`.
- [ ] **Step 4:** Re-run `python -m unittest tests/test_tuner_core.py -v` -> PASS.
- [ ] **Step 5:** Commit Task 2.

---

### Task 3: Native Probes, Staged Sweep, Isolated Carrier Matrix, Responder, Orchestrator & CLI

**Files:**
- Create: `rathole-manager/tuner/probes.py`
- Create: `rathole-manager/tuner/carriers.py`
- Create: `rathole-manager/tuner/sweep.py`
- Create: `rathole-manager/tuner/responder.py`
- Create: `rathole-manager/tuner/orchestrator.py`
- Create: `rathole-manager/tuner/__main__.py`
- Create: `rathole-manager/rathole-tuner`
- Test: `tests/test_tuner_loopback.py`

**Interfaces:**
- Consumes: Tasks 1 and 2 modules
- Produces:
  - `tuner/probes.py`: `ProbeServer`, `probe_pmtu(...)`, `probe_unloaded_rtt(...)`, `probe_trial(...)`
  - `tuner/carriers.py`: `detect_installed_carriers(...)`, `benchmark_carriers(...)`
  - `tuner/sweep.py`: `compute_bdp_buffers(...)`, `build_stage_candidates(...)`, `run_staged_sweep(...)`
  - `tuner/responder.py`: `TunerResponder`
  - `tuner/orchestrator.py`: `TunerOrchestrator` (`run`, `test_profile`, `compare_profiles`)
  - CLI (`rathole-tuner` / `python3 -m tuner`): `listen`, `run`, `test-profile`, `compare`, `export`, `validate`, `apply`, `apply-boot`, `rollback`, `status`

- [ ] **Step 1:** Write `tests/test_tuner_loopback.py` launching real `TunerResponder` + `TunerOrchestrator` on `127.0.0.1` (`MockSysDriver`, `fast_test=True`) covering `run` -> `export --format base64` -> `validate` -> `test-profile` -> `compare` + CLI smoke tests.
- [ ] **Step 2:** Run `python -m unittest tests/test_tuner_loopback.py -v` and confirm failure.
- [ ] **Step 3:** Implement `probes.py`, `carriers.py`, `sweep.py`, `responder.py`, `orchestrator.py`, `__main__.py`, and `rathole-tuner`.
- [ ] **Step 4:** Re-run `python -m unittest tests/test_tuner_loopback.py -v` -> PASS.
- [ ] **Step 5:** Commit Task 3.

---

### Task 4: Native `ratholectl bench` / `ratholenode bench` Wrappers & Installer/Updater Packaging

**Files:**
- Modify: `rathole-manager/ratholectl`
- Modify: `rathole-manager/ratholenode`
- Modify: `rathole-manager/install-panel.sh`
- Modify: `rathole-manager/install-node.sh`
- Modify: `rathole-manager/update.sh`

- [ ] **Step 1:** Add `cmd_bench` to `rathole-manager/ratholectl` and `rathole-manager/ratholenode` supporting `listen`, `stop-listen`, `run`, `test-profile`, `compare`, `export`, `validate`, `apply`, `rollback`, `status`, `job`.
- [ ] **Step 2:** Update `install-panel.sh`, `install-node.sh`, and `update.sh` to install, snapshot/restore on failure, LF-normalize, and upgrade `tuner/*.py` (`/usr/local/share/rathole/tuner/`) and `rathole-tuner` (`/usr/local/bin/rathole-tuner`).
- [ ] **Step 3:** Verify in WSL via `bash -n` and `shellcheck --shell=bash --severity=error --exclude=SC1091`.
- [ ] **Step 4:** Commit Task 4.

---

### Task 5: Hub Allow-Listed Commands, Async Tuner Endpoints & Datacenter Profile Library

**Files:**
- Modify: `rathole-manager/ratholehub/hubcmds.py`
- Modify: `rathole-manager/ratholehub/hub.py`
- Test: `tests/test_tuner_hub.py`

- [ ] **Step 1:** Write `tests/test_tuner_hub.py` testing `hubcmds.py` bench regex validation / injection rejection / `WRITE_ACTIONS`, audit redaction of `--token`, and full HTTP lifecycle (`/api/tuner/start`, `/api/tuner/jobs/<id>`, `/api/tuner/jobs/<id>/cancel`, `/api/tuner/profiles`, `/api/tuner/apply`, `/api/tuner/rollback`) under `RATHOLEHUB_MOCK=1`.
- [ ] **Step 2:** Run `python -m unittest tests/test_tuner_hub.py -v` and confirm failure.
- [ ] **Step 3:** Implement `hubcmds.py` actions/regexes and `hub.py` async job runner, mock outputs, atomic `tuner-profiles.json` store, and dual-server transactional `apply` (auto-rollback Iran on Node failure).
- [ ] **Step 4:** Re-run `python -m unittest tests/test_tuner_hub.py -v` -> PASS.
- [ ] **Step 5:** Commit Task 5.

---

### Task 6: Hub `#/tuner` UI & JS Regression Tests

**Files:**
- Modify: `rathole-manager/ratholehub/ui/index.html`
- Modify: `rathole-manager/ratholehub/ui/i18n.js`
- Modify: `rathole-manager/ratholehub/ui/app.js`
- Modify: `rathole-manager/ratholehub/ui/app.css`
- Modify: `tests/test_hub_provisioning.js`

- [ ] **Step 1:** Extend `tests/test_hub_provisioning.js` with tests for `#/tuner` route parsing, i18n FA/EN key parity for tuner keys, and tuner UI state/formatting helpers.
- [ ] **Step 2:** Run `node --test tests/test_hub_provisioning.js` and confirm new tests fail.
- [ ] **Step 3:** Implement `<symbol id="i-gauge">` in `index.html`, FA/EN translations in `i18n.js`, sidebar/command-palette/router/page in `app.js`, and styling in `app.css`.
- [ ] **Step 4:** Run `node --test tests/test_hub_provisioning.js` -> PASS.
- [ ] **Step 5:** Commit Task 6.

---

### Task 7: Final Cross-Platform Verification (Windows + WSL)

- [ ] **Step 1:** Enforce LF line endings on all new/modified files.
- [ ] **Step 2:** Run `python -m py_compile` on all Python files in `tuner/` and `ratholehub/`.
- [ ] **Step 3:** Run full Windows + WSL `unittest`, `node --test`, `bash -n`, `shellcheck`, `test_init_interactive.sh`, and `test_release_bundle.sh --workflow`.
- [ ] **Step 4:** Verify `git status --short` is clean before finishing.
