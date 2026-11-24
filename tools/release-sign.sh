#!/usr/bin/env bash
# release-sign.sh — emza va tayid-e cryptographic Ed25519 baraye SHA256SUMS (bedoon-e dependency khareji, faghat OpenSSL).
# estefade:
#   bash tools/release-sign.sh keygen <out-dir>
#   bash tools/release-sign.sh sign   <private-key.pem> <file> [sig-out]
#   bash tools/release-sign.sh verify <public-key.pem>  <file> <sig-file>
set -euo pipefail

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_r(){ printf '\033[1;31m%s\033[0m' "$*" >&2; }
err(){ printf '%s %s\n' "$(c_r '[!]')" "$*" >&2; }
die(){ err "$*"; exit 1; }

need_openssl(){
  command -v openssl >/dev/null 2>&1 || die "openssl lazem ast baraye emza/tayid-e Ed25519."
}

usage(){
  cat >&2 <<'USAGE'
release-sign.sh — Ed25519 release signing helper (OpenSSL)

Commands:
  keygen <out-dir>                  tolide joft kelid-e Ed25519 (release-ed25519.key + .pub)
  sign   <priv.pem> <file> [out]    emza-ye <file> → base64 dar [out] (default: <file>.sig)
  verify <pub.pem>  <file> <sig>    barresi-ye emza-ye <file> ba <sig> va <pub.pem>
USAGE
  exit 2
}

cmd_keygen(){
  need_openssl
  local out_dir="${1:-}"
  [ -n "$out_dir" ] || usage
  mkdir -p "$out_dir"
  local priv="$out_dir/release-ed25519.key"
  local pub="$out_dir/release-ed25519.pub"
  if [ -e "$priv" ] || [ -e "$pub" ]; then
    die "file-e kelid az ghabl vojood darad dar: $out_dir"
  fi
  (
    umask 077
    openssl genpkey -algorithm ED25519 -out "$priv" 2>/dev/null
  ) || die "tolid kelid-e Ed25519 shekast khord (openssl >= 1.1.1 lazem ast)."
  chmod 0600 "$priv"
  openssl pkey -in "$priv" -pubout -out "$pub" 2>/dev/null || die "estekhraj-e kelid-e omumi shekast khord."
  chmod 0644 "$pub"
  printf '%s Ed25519 keypair sakhte shod:\n' "$(c_g '[+]')"
  printf '  private key (SECRET — NEVER COMMIT): %s\n' "$priv"
  printf '  public key  (commit to repo):        %s\n' "$pub"
  printf '  badi: mohtava-ye .pub ra dar rathole-manager/keys/release-ed25519.pub bezar\n'
  printf '        va mohtava-ye .key ra dar GitHub Secret RELEASE_ED25519_PRIVATE_KEY sabt kon.\n'
}

cmd_sign(){
  need_openssl
  local key="${1:-}" file="${2:-}" sig_out="${3:-}"
  [ -n "$key" ] && [ -n "$file" ] || usage
  [ -s "$key" ] || die "kelid-e khosusi peyda nashod ya khali ast: $key"
  [ -f "$file" ] || die "file baraye emza peyda nashod: $file"
  [ -n "$sig_out" ] || sig_out="${file}.sig"
  mkdir -p "$(dirname "$sig_out")"
  local tmp
  tmp="$(mktemp "${sig_out}.tmp.XXXXXX")"
  trap 'rm -f "${tmp:-}"' EXIT
  (
    umask 022
    local raw_sig
    raw_sig="$(mktemp)"
    trap 'rm -f "${raw_sig:-}"' EXIT
    openssl pkeyutl -sign -inkey "$key" -rawin -in "$file" -out "$raw_sig" 2>/dev/null \
      || die "emza-ye Ed25519 shekast khord."
    local sz
    sz="$(wc -c < "$raw_sig" | tr -d '[:space:]')"
    [ "$sz" = "64" ] || die "andaze-ye emza-ye Ed25519 namotabar ast ($sz bytes)."
    base64 < "$raw_sig" | tr -d '\r\n' > "$tmp"
    printf '\n' >> "$tmp"
  )
  chmod 0644 "$tmp"
  mv -f "$tmp" "$sig_out"
  trap - EXIT
  printf '%s signed: %s → %s\n' "$(c_g '[+]')" "$file" "$sig_out"
}

cmd_verify(){
  need_openssl
  local pub="${1:-}" file="${2:-}" sig="${3:-}"
  [ -n "$pub" ] && [ -n "$file" ] && [ -n "$sig" ] || usage
  [ -s "$pub" ] || die "kelid-e omumi peyda nashod: $pub"
  [ -f "$file" ] || die "file baraye tayid peyda nashod: $file"
  [ -s "$sig" ] || die "file-e emza peyda nashod ya khali ast: $sig"

  local raw_sig sig_sz decoded=0
  raw_sig="$(mktemp)"
  trap 'rm -f "${raw_sig:-}"' EXIT

  if tr -d ' \t\r\n' < "$sig" | base64 -d > "$raw_sig" 2>/dev/null; then
    sig_sz="$(wc -c < "$raw_sig" | tr -d '[:space:]')"
    [ "$sig_sz" = "64" ] && decoded=1
  fi
  if [ "$decoded" -eq 0 ]; then
    sig_sz="$(wc -c < "$sig" | tr -d '[:space:]')"
    if [ "$sig_sz" = "64" ]; then
      cp "$sig" "$raw_sig"
      decoded=1
    fi
  fi
  [ "$decoded" -eq 1 ] || die "format-e emza-ye Ed25519 namotabar ast (64 bytes ya base64 entezar miravad)."

  openssl pkeyutl -verify -pubin -inkey "$pub" -rawin -sigfile "$raw_sig" -in "$file" >/dev/null 2>&1 \
    || die "emza-ye Ed25519 namotabar ast: $file"
  printf '%s Ed25519 verified: %s\n' "$(c_g '[+]')" "$file"
}

main(){
  local cmd="${1:-}"
  [ -n "$cmd" ] || usage
  shift
  case "$cmd" in
    keygen) cmd_keygen "$@" ;;
    sign)   cmd_sign "$@" ;;
    verify) cmd_verify "$@" ;;
    -h|--help|help) usage ;;
    *) usage ;;
  esac
}

main "$@"
