#!/usr/bin/env bash
# core-install.sh — verify checksum va nasb-e binary-e rathole core (v1.5.0-ratholeengine.1)
# estefade: sudo bash core-install.sh [--verify-only]
# RATHOLE_CORE_DIR: masir-e core/ (default: kenar-e file)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RATHOLE_CORE_DIR="${RATHOLE_CORE_DIR:-$SCRIPT_DIR/core}"
REQUIRED_VERSION="${RATHOLE_ENGINE_VERSION:-0.5.1-ratholeengine.1}"
VERIFY_ONLY=0
REQUIRE_SIG="${RATHOLE_REQUIRE_SIG:-0}"
SIGNING_PUBKEY="${RATHOLE_SIGNING_PUBKEY:-}"

log(){ printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[*]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[!]\033[0m %s\n' "$*" >&2; }
die(){ err "$*"; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --verify-only) VERIFY_ONLY=1; shift ;;
    --require-sig) REQUIRE_SIG=1; shift ;;
    --core-dir=*) RATHOLE_CORE_DIR="${1#*=}"; shift ;;
    --version=*) REQUIRED_VERSION="${1#*=}"; shift ;;
    --pubkey=*) SIGNING_PUBKEY="${1#*=}"; shift ;;
    --pubkey)
      [ $# -ge 2 ] || die "--pubkey be masir file niaz darad."
      SIGNING_PUBKEY="$2"; shift 2 ;;
    *) shift ;;
  esac
done

verify_sums_sig(){
  local sums_file="$1" sig_file="${1}.sig" pub="$SIGNING_PUBKEY" cand
  if [ -z "$pub" ]; then
    for cand in /usr/local/share/rathole/keys/release-ed25519.pub "$SCRIPT_DIR/keys/release-ed25519.pub"; do
      [ -s "$cand" ] && { pub="$cand"; break; }
    done
  fi
  if [ ! -s "$sig_file" ]; then
    [ "$REQUIRE_SIG" = "1" ] && die "emza-ye Ed25519 elzami ast vali peyda nashod: $sig_file"
    return 0
  fi
  if [ -z "$pub" ] || [ ! -s "$pub" ]; then
    [ "$REQUIRE_SIG" = "1" ] && die "emza-ye Ed25519 elzami ast vali kelid-e omumi (release-ed25519.pub) peyda nashod."
    warn "file-e emza ($sig_file) vojood darad vali kelid-e omumi nasb nist; tayid-e Ed25519 rad shod."
    return 0
  fi
  command -v openssl >/dev/null 2>&1 || die "openssl baraye tayid-e Ed25519 lazem ast ($sig_file)."
  local raw_sig ok=0 sz=0
  raw_sig="$(mktemp)"
  if tr -d ' \t\r\n' < "$sig_file" | base64 -d > "$raw_sig" 2>/dev/null; then
    sz="$(wc -c < "$raw_sig" | tr -d '[:space:]')"
    [ "$sz" = "64" ] && ok=1
  fi
  if [ "$ok" -eq 0 ]; then
    sz="$(wc -c < "$sig_file" | tr -d '[:space:]')"
    [ "$sz" = "64" ] && cp "$sig_file" "$raw_sig" 2>/dev/null && ok=1
  fi
  [ "$ok" -eq 1 ] || { rm -f "$raw_sig"; die "format-e emza-ye Ed25519 namotabar ast: $sig_file"; }
  if ! openssl pkeyutl -verify -pubin -inkey "$pub" -rawin -sigfile "$raw_sig" -in "$sums_file" >/dev/null 2>&1; then
    rm -f "$raw_sig"
    die "emza-ye Ed25519 motabar NIST! ehtemal-e dastkari dar SHA256SUMS."
  fi
  rm -f "$raw_sig"
  log "emza-ye Ed25519 tayid shod ($sig_file)."
}

# architecture: x86_64 → x86_64-unknown-linux-gnu, aarch64 → aarch64-unknown-linux-gnu
case "$(uname -m)" in
  x86_64)  TARGET="x86_64-unknown-linux-gnu" ;;
  aarch64) TARGET="aarch64-unknown-linux-gnu" ;;
  *) die "memari poshtibani-nashode: $(uname -m)" ;;
esac

CORE_BIN="$RATHOLE_CORE_DIR/$TARGET/rathole"
SHA256_FILE="$RATHOLE_CORE_DIR/SHA256SUMS"

# ---- barresi vojood binary ----
[ -f "$CORE_BIN" ] || die "binary-e core peyda nashod: $CORE_BIN (avval core/build.sh ra ejra kon ya az release download kon)"
[ -f "$SHA256_FILE" ] || die "SHA256SUMS peyda nashod: $SHA256_FILE"
verify_sums_sig "$SHA256_FILE"

# ---- verify checksum ----
log "barresi checksum baraye $TARGET..."
# --ignore-missing tanha file-haye list-shode ra check mikonad; binary-e entekhabi bayad dar list bashad.
awk -v target="$TARGET/rathole" '$2 == target || $2 == "*" target || $2 == "./" target || $2 == "*./" target { found=1 } END { exit !found }' "$SHA256_FILE" || \
  die "checksum-e binary-e entekhabi dar SHA256SUMS nist: $TARGET/rathole"
( cd "$RATHOLE_CORE_DIR" && sha256sum -c SHA256SUMS --ignore-missing --quiet ) || \
  die "checksum-e binary motabar nist! binary-e dastkar-shode ya nashenas."

if [ "$VERIFY_ONLY" -eq 1 ]; then
  log "verify OK (--verify-only flag: nasb naShod)."
  exit 0
fi

# ---- ejra va barresi version ----
[ "$(id -u)" -eq 0 ] || die "nasb niyaz be root darad (sudo bash core-install.sh)."
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
cp "$CORE_BIN" "$tmp"
chmod +x "$tmp"
actual_ver="$("$tmp" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+-[a-z0-9]+\.[0-9]+' | head -1 || echo '')"
if [ "$actual_ver" != "$REQUIRED_VERSION" ]; then
  die "version-e binary namotabar: got='$actual_ver', expected='$REQUIRED_VERSION' (binary eshari? rebuild lazem?)"
fi

# ---- nasb binary ----
install -m 0755 "$tmp" /usr/local/bin/rathole
log "rathole core nasb shod: $REQUIRED_VERSION → /usr/local/bin/rathole"
