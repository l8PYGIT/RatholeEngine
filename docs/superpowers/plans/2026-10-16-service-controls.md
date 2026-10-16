# Service Controls Implementation Plan

**Goal:** Remove the wiring board and expose service controls on both server pages, including the actual carrier protocol.

**Spec:** ../specs/2026-10-16-service-controls-design.md

**Architecture:** Use one service lookup and carrier workflow for both pages. Keep the existing validated hub action API. Read live state before mutations and preserve the node inbound port when changing carrier.

**Tech stack:** Vanilla JavaScript/CSS, Python stdlib, Bash.

- [x] Add regression tests for preserving inbound ports and reporting actual FRP/Backhaul protocols.
- [x] Remove board navigation, drawing, mini strips, and optimistic circuit state. Move health, copy, configuration and removal actions to Iran/node service rows.
- [x] Use authoritative service ports and per-service lanes. Make failed commands visible and avoid claiming rollback when none occurred.
- [x] Require a real UUID for copied VLESS links and derive public ingress from Iran status.
- [x] Run JavaScript/Python regressions and inspect both pages with the mock hub.
- [x] Update docs/version; publish verified release assets after committing.

Verification: 45 JavaScript regressions and 67 hub Python tests pass. Mock-browser Iran/node pages and protocol dialog inspected. Independent review findings (fresh state before removal, SNI guard) addressed. Live servers were not exercised.
