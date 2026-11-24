# Release Signing Keys (Ed25519)

This directory holds public Ed25519 keys used to verify `SHA256SUMS.sig` in official releases and core bundles.

## Setup & Rotation

1. Generate a keypair outside the repository (never commit the private key):
   ```bash
   bash tools/release-sign.sh keygen /tmp/rth-keys
   ```
2. Install the public key here:
   ```bash
   cp /tmp/rth-keys/release-ed25519.pub rathole-manager/keys/release-ed25519.pub
   ```
3. Save the contents of `/tmp/rth-keys/release-ed25519.key` in the repository's GitHub Actions secret `RELEASE_ED25519_PRIVATE_KEY`, then delete `/tmp/rth-keys/release-ed25519.key` (or store offline in a password manager).

When `RELEASE_ED25519_PRIVATE_KEY` is configured on a tagged release, `.github/workflows/release.yml` automatically signs:
- `rathole-manager/core/SHA256SUMS` -> `.sig`
- `rathole-manager/core-backhaul/SHA256SUMS` -> `.sig`
- `dist/SHA256SUMS` -> `.sig`
