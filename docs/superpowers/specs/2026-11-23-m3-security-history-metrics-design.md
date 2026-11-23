# Milestone 3 (M3) Design Spec — Hub Security Hardening, Audit Chaining, State History/Undo & Prometheus Metrics

**Branch:** `feat/v2.2-backpack-upgrades`  
**Target Release:** `v2.2.0` (Milestone 3 of 7)

---

## 1. Scope

Milestone 3 hardens the `ratholehub` control plane and `ratholectl` state mutations across five areas while keeping 100% Python stdlib-only zero-pip architecture:

1. **Scoped API Tokens (`read`, `operate`, `admin`):** Hashed-at-rest (`SHA-256`) multi-token management via `/api/tokens`, optional expiration, constant-time lookup, and full backward compatibility with legacy single `api_token` (`admin`).
2. **RFC 6238 TOTP 2FA & Recovery Codes:** Two-step authenticator setup (`/api/2fa/setup`, `/api/2fa/enable`, `/api/2fa/disable`, `/api/2fa/status`), ±1 step tolerance, replay protection (`last_step`), and 8 single-use hashed recovery codes (`XXXX-XXXX`).
3. **Defense-in-Depth CSRF Guard:** Rejects cross-site `POST`/`PUT`/`DELETE` requests authenticated via `rhsession` cookie using `Sec-Fetch-Site` + `Origin`/`Referer` host verification (`Host` / `X-Forwarded-Host`), while leaving `Authorization: Bearer` API clients unaffected.
4. **Tamper-Evident Hash-Chained Audit Log (`prev_hash` + `hash`):** Cryptographic SHA-256 chain over `audit.log` entries plus `GET /api/audit/verify` and Audit UI integrity badge. Legacy unchained prefix entries before upgrade remain supported cleanly.
5. **Panel `state.json` Revision History & Undo + Prometheus `/metrics`:** Automatic pre-mutation snapshots before `state_set` / `state_jq` / `cmd_restore`, `ratholectl history [--json]`, `ratholectl undo [--dry-run] [N]` (+ Hub `state_history` / `state_undo` / `state_undo_dry_run`), and read-scoped `GET /metrics` (`text/plain; version=0.0.4`).

---

## 2. Security & Architectural Contracts

- **Least Privilege Scopes:**
  - `read`: inventory/status/overview/drift/audit/verify/metrics and read-only `link-test` or read-only `action`s. Cannot read `*connect` shared tunnel credentials or run mutating actions.
  - `operate`: all `read` routes + `WRITE_ACTIONS`, `deploy`, `*connect`, and `ip-tls/prepare`. Cannot manage inventory servers, Hub proxy/config, scoped tokens, or 2FA.
  - `admin`: full control including `/api/servers`, `/api/provision`, `/api/config`, `/api/tokens`, `/api/2fa/*`, and cookie sessions.
- **TOTP & Token Storage:** Only hashes (`sha256`), prefixes (`raw[:10]`), and Base32 TOTP secret (when enabled) are persisted in `/etc/ratholehub/config.json` (`0600`); raw scoped tokens and recovery codes are displayed once upon creation and never retrievable via GET endpoints.
- **State Undo Safety:** Snapshots deduplicate identical states (`cmp -s`), keep up to `RTH_HISTORY_MAX` (default 20) revisions under `$(dirname "$STATE")/history` (`0700` dir / `0600` files), support `--dry-run`, and snapshot the current state immediately prior to rolling back so undo itself is reversible.
