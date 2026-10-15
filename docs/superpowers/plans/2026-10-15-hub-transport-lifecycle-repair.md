# Hub, transports and lifecycle repair implementation plan

> **For agentic workers:** Use superpowers:executing-plans and focused parallel investigation for independent lifecycle/backend domains. Track each task below.

**Goal:** Repair the confirmed hub/transport bugs and audit installers, updates and rollback for actionable failures.
**Architecture:** Keep the existing stdlib Python, Bash state → regenerate → reload model and browser UI. Validate command arguments at the hub boundary; keep transport credentials and Iran backend ports consistent across both peers. Report failed or unsupported operations without claiming success.
**Tech Stack:** Bash, Python stdlib unittest, JavaScript Node built-in test/assert, existing shell harnesses.
**Spec:** User request in this chat (2026-10-15), repository AGENTS.md, and confirmed reproductions from the review.

## Global constraints
- No new production dependencies; preserve LF, config inode preservation and secrets exclusions.
- No real server operations, installs or destructive system commands. Repository commit/push subsequently authorized by the user.
- Reproduce defects before production edits; run focused tests then integrated checks.
- Work in the user-selected checkout; commit and push to origin/main after final verification as subsequently requested.
- User explicitly requested plan followed by immediate implementation; no extra plan approval gate.

## Review focus
- Fresh and existing carrier configurations must agree on credentials, port and mode.
- Adding/removing FRP services must regenerate FRP rather than silently update Rathole.
- API-only inventory records must never require SSH host metadata.
- Remote command failures must stop provisioning and preserve an accurate UI state.
- Install/update/rollback failures must return failure and preserve recoverability.

### Task 1: Hub execution and Agent contract
Files: rathole-manager/ratholehub/hub.py, rathole-manager/ratholeagent.py; tests/test_agent.py, new focused hub execution tests.
Interfaces: run_on_server(server, argv, timeout) and deploy_to_server(server) return rc/out/err; Agent accepts validated timeout wrappers.
- [x] Add regression tests proving remote bash script argument preservation, API deploy without host, and diagnostics through Agent.
- [x] Run tests and observe expected failures.
- [x] Fix SSH quoting/stdin and API dispatch; validate bounded timeout wrappers and malformed payloads.
- [x] Run all Python tests and review affected callers.

### Task 2: FRP service/port lifecycle
Files: rathole-manager/ratholenode, rathole-manager/ratholectl; shell regression tests.
Interfaces: add-svc name token inbound [remote_port]; apply selects active carrier and generates its config; Iran FRP listener retains nginx backend mapping.
- [x] Reproduce dropped fourth argument and unchanged FRP config on add/remove.
- [x] Pass remote_port through main; regenerate/restart FRP when active and preserve service mappings.
- [x] Review server FRP binding, transport/token validation and normal transport transitions; fix confirmed defects only.
- [x] Run focused shell tests with filesystem/systemctl stubs.

### Task 3: Hub provisioning and forms
Files: rathole-manager/ratholehub/ui/app.js, hubcmds.py/hub.py only if contracts require extension; Node regression tests.
Interfaces: provisionPatchCircuit returns success only after each checked action; connection helpers provide authoritative carrier metadata.
- [x] Test generated action sequences for ws/kcp/plain/noise/backhaul/frp/gre/frp_gre and failure responses.
- [x] Resolve real peer server unambiguously; use real tokens, listener ports, backend ports and matching profiles.
- [x] Configure both ends; ensure GRE plus FRP runs both stages and FRP uses GRE endpoint in combined mode.
- [x] Expose remote_port in add-service forms and prevent premature optimistic success.
- [x] Test existing transport switching and partial failures; do not promise atomic rollback where unavailable.

### Task 4: Installer/updater/rollback audit
Files: install.sh, bootstrap.sh, package.sh, rathole-manager/*install*.sh, update.sh, core-install.sh, ratholehub/install-hub.sh; lifecycle regression tests.
- [x] Read all lifecycle entry points, download/extraction, installation, snapshot, health check and rollback paths.
- [x] Add failing tests for concrete defects found; fix minimally and preserve existing flags.
- [x] Verify Agent and transport units/configs are installed, updated and snapshotted consistently where applicable.
- [x] Run lifecycle shell tests and syntax checks without touching target server paths.

### Task 5: Integrated verification and handoff
- [x] Run Python suite, Node provisioning tests, applicable Bash tests and all tracked script syntax checks.
- [x] Review complete diff and run git diff --check; document platform-dependent checks that cannot run locally.
- [x] Update this plan with outcomes and remaining limitations; report files and results concisely in Persian.

## Execution ledger
- Baseline: main initially clean; 56 Python unit tests passed before changes. No CodeGraph index exists.
- Ruling: execute immediately as requested; separate independent lifecycle/backend work to avoid UI conflicts.


## Outcomes
- Hub SSH preserves remote argument boundaries; deploy supports API-only records. Diagnostic execution rejects invalid requests and terminates the POSIX process group on timeout.
- Connection helpers expose authoritative FRP credentials/listener/backend ports and Rathole control paths. Hub provisioning configures both peers, reports partial failures, initializes fresh node state first, and never silently chooses an unrelated peer.
- GRE uses the configured /30 peer addresses: plain WebSocket over GRE for the standalone lane, FRP over GRE for the combined lane. This is actual data-plane configuration, not only interface creation.
- FRP services preserve per-service remote mappings through add/remove/apply/restart. FRP proxy listeners stay on loopback behind nginx. Independent Backhaul ownership is retained.
- Install/update/rollback checks cover failed snapshots, failed apply, failed health, active lane selection, core verification, bundled-core preference, Agent executable paths, unit cleanup and transport restart coverage.
- Agent credentials are absent from generated systemd units and startup logs; legacy units are migrated to the protected token file.
- New checks are wired into CI. No production dependencies were added, no server was deployed, and repository publication was subsequently authorized by the user.

## Verification ledger
- Ubuntu WSL: 86 Python tests passed, including real POSIX child-process timeout behavior and lifecycle sandboxes.
- Windows Node: 16 provisioning regression tests passed; app.js syntax check passed.
- Ubuntu WSL: all 17 non-network Bash test scripts passed, including prompts/locks/nginx paths, dual-core, release/bundle and new service/failure tests.
- Bash syntax: 38 tracked/new shell scripts checked successfully; ShellCheck error severity passed across that set.
- Initial Git Bash failures involving Linux flock, /proc and MSYS path conversion were resolved by running the Linux tests in Ubuntu. A Linux-only Python test isolation failure caused by inherited /dev/null configuration was fixed at the test boundary.
- WSL cannot resolve github.com in this environment; both pinned core patch checks were retried with Windows Git Bash and passed.
- Fresh-context review identified two integration issues (fresh-node ordering, descendant process timeout); both gained regression tests and were fixed. Follow-up review found no further confirmed high-priority regressions in that scope.

## Practical limits
- Actual apt/systemd/nginx installation and traffic across two remote servers were not exercised; all mutation tests use isolated filesystem/service boundaries.
- Multi-server provisioning reports partial changes on failure; it does not promise a distributed atomic rollback.
- Existing rollback restores snapshotted files and restarts the selected lane; it does not reconstruct every systemd enabled-state symlink or remove every file first introduced by a failed update.

## Private updater and repository publication
- Added tools/update-private.sh with authenticated GitHub Release API asset downloads, hidden token input, and no embedded credentials. Three isolated download/failure tests added.
- Final pre-publication checks: 89 Python tests and 16 JavaScript provisioning tests passed; diff whitespace check clean.
- User explicitly requested committing and pushing the completed changes to GitHub main. Publishing source does not create a Release or update remote servers.
