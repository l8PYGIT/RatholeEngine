# Milestone 6 Design Spec: Tunnel-Relayed Updates, Ed25519 Release Signing & Backhaul `direct_ip` TLS Pinning

**Date:** 2026-11-23
**Branch:** `feat/v2.2-backpack-upgrades`
**Scope:** Tunnel-relayed self-updates (`--proxy` + Hub auto/explicit relay via `hubupdate.py`), Ed25519 `SHA256SUMS.sig` cryptographic signature verification across release packaging and installers, and `core-backhaul` `direct_ip` TLS certificate pinning (`0002-tls-verify-ca-pinning.patch` + `ratholenode` + Hub integration).

---

## 1. Tunnel-Relayed Self-Updates

Inside censored networks, Iran servers (and sometimes the Hub itself) often cannot reach `github.com` or `raw.githubusercontent.com` directly and public `ghproxy` mirrors may be throttled or blocked.

- **Installer & CLI Proxy Support (`install.sh`, `ratholectl update`, `ratholenode update`):**
  - Accepts `--proxy <url>` / `--proxy=<url>` (or `RATHOLE_UPDATE_PROXY`), `--require-sig` (`RATHOLE_REQUIRE_SIG=1`), and `--pubkey <path>` (`RATHOLE_SIGNING_PUBKEY`).
  - Proxy URLs are validated strictly (`http://`, `https://`, `socks5://`, `socks5h://`, no shell metachars or whitespace), passed via `curl --config -` so credentials never appear in `/proc/*/cmdline`, and always redacted (`scheme://***@host`) before logging.
  - When an explicit proxy is configured, downloads route directly through the proxy rather than bouncing through public `ghproxy` mirrors, and both `--beta` atom resolution and release asset downloads honor it.
- **Hub Relayed & Verified Deployment (`rathole-manager/ratholehub/hubupdate.py`):**
  - Supports three relay modes (`update_relay_mode`: `auto`, `direct`, `relay`) plus optional `update_proxy` and `update_require_sig` in Hub `/api/config` and the Settings UI.
  - Transport fallback chain for Hub downloads: configured `update_proxy` -> direct TLS -> live foreign `node` server in inventory via `tg_relay.SshRelayTunnel` (`ssh -N -D 127.0.0.1:<ephemeral>`), torn down immediately after download completes.
  - Downloads and verifies `bootstrap.sh`, `rathole-manager.zip`/`.tar.gz`, `SHA256SUMS`, and `SHA256SUMS.sig` locally on the Hub, then streams a deterministic flat `tar` archive containing `bootstrap.sh` and the bundle over SSH stdin to run `bash "$T/bootstrap.sh" --local "$T/<bundle>" --update` cleanly on the target server (taking `update.sh` snapshots and auto-rolling back on health check failure).
  - In `auto` mode, SSH deployments automatically fall back to Hub-relayed push if direct on-server fetch fails due to filtering/network errors.

---

## 2. Ed25519 Cryptographic Verification of `SHA256SUMS`

SHA256 checksums alone do not authenticate origin if a mirror is compromised.

- **Key Management & Signing Tool (`tools/release-sign.sh`, `rathole-manager/keys/`):**
  - OpenSSL Ed25519 (`openssl genpkey -algorithm ED25519`, `openssl pkeyutl -sign -rawin`, `openssl pkeyutl -verify -pubin -rawin`) using pure bash/stdlib Python — zero `pip` dependencies.
  - `tools/release-sign.sh` supports `keygen`, `sign`, and `verify` (base64-encoded 64-byte Ed25519 signatures stored in `SHA256SUMS.sig`, also accepting raw 64-byte signature files).
  - Public key lives at `/usr/local/share/rathole/keys/release-ed25519.pub` (or `RATHOLE_SIGNING_PUBKEY` / `--pubkey`); private keys stay exclusively out-of-repo in `RELEASE_ED25519_PRIVATE_KEY` GitHub Actions secret.
- **Fail-Closed Verification Policy:**
  - Whenever `SHA256SUMS.sig` is present and verification fails, ALL installers (`install.sh`, `core-install.sh`, `common.sh:install_backhaul_core`, `hubupdate.py`) **always** abort immediately (even when `--require-sig` is off).
  - When `--require-sig` / `RATHOLE_REQUIRE_SIG=1` is enabled, missing `SHA256SUMS`, missing `.sig`, missing public key, or missing `openssl` also fails closed.
  - Default mode remains compatible with unsigned local/fork builds when no `.sig` is present.
- **Release Workflow (`.github/workflows/release.yml`):**
  - Generates `dist/SHA256SUMS` across all release assets (`rathole-manager.zip`, `.tar.gz`, `bootstrap.sh`, `install.sh`).
  - Signs `core/SHA256SUMS`, `core-backhaul/SHA256SUMS`, and `dist/SHA256SUMS` whenever `secrets.RELEASE_ED25519_PRIVATE_KEY` is configured and uploads `dist/SHA256SUMS` + `dist/SHA256SUMS.sig`.

---

## 3. `core-backhaul` `direct_ip` MITM Fix (Pinned Certificate Verification)

Previously, `core-backhaul/patches/0001-utls-chrome-clienthello.patch` set `InsecureSkipVerify: true` unconditionally, leaving `direct_ip` + `wss`/`wssmux` vulnerable to active MITM.

- **Go Core Patch (`core-backhaul/patches/0002-tls-verify-ca-pinning.patch`):**
  - Extends `internal/client/transport/utls.go` while keeping `InsecureSkipVerify: true` to drive Chrome uTLS and plugging in a custom `VerifyPeerCertificate` verifier controlled by:
    - `BACKHAUL_TLS_CA`: path to pinned PEM CA or self-signed IP-SAN leaf certificate.
    - `BACKHAUL_TLS_VERIFY`: `1`/`true` to verify against the OS system cert pool (`x509.SystemCertPool()`).
    - `BACKHAUL_TLS_VERIFY_NAME`: explicit DNS name or IP literal to check against SANs (defaults to the dialed host from `addr`).
  - Performs standard X.509 chain + KeyUsage (`ExtKeyUsageServerAuth`) + hostname/IP SAN verification, plus exact DER leaf-cert pinning + validity-window + `VerifyHostname` check for non-CA self-signed certificates (`ratholectl ip-cert`).
- **Node & Hub Orchestration (`ratholenode`, `hubcmds.py`, `hub.py`, `ui/app.js`):**
  - `ratholenode backhaul on` accepts `--ca <path>`, `--sni <host>`, `--verify`, `--no-verify` while preserving full backwards compatibility with positional arguments.
  - For `direct_ip` `wss`/`wssmux`, `ratholenode` automatically discovers matching SAN-verified certs from `TLS_TRUSTED_ROOT` or `/etc/rathole/certs/<ip>.crt`, stores `BH_TLS_CA`, `BH_TLS_VERIFY`, `BH_TLS_SNI` in `node.env`, and injects `Environment="BACKHAUL_TLS_..."` into `rathole-backhaul-client.service`.
  - For `nginx_tls` domain endpoints, `BH_TLS_VERIFY=1` enables system CA + domain SAN verification by default.
  - Hub `configureServiceCarrier` invokes `ip-tls-prepare` automatically before `backhaul_on` in `direct_ip` `wss`/`wssmux` mode and passes `tls_ca`.
