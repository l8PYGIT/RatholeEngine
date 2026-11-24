#!/usr/bin/env bash
# install.sh — nasb-e tak-command az GitHub (curl | sudo bash)
#
# in file baraye ejra be sooratِ pipe tarahi shode:
#   curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --panel \
#        --domain panel.example.ir --fullchain /root/cert/.../fullchain.pem --key /root/cert/.../privkey.pem
#   curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --node -- \
#        --server panel.example.ir:443 --name trk01 --token <T> --inbound-port 2087
#   curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --update
#   curl -fsSL https://raw.githubusercontent.com/l8PYGIT/RatholeEngine/main/install.sh | sudo bash -s -- --rollback
#
# nasb-e YEK NOSKHE-YE KHAS (release pinning) — ba flag، na motghayer-e mohiti:
#   curl -fsSL .../install.sh | sudo bash -s -- --release v1.8.0 --panel --domain ...
#   curl -fsSL .../install.sh | sudo bash -s -- --release v1.7.0 --update
#   curl -fsSL .../install.sh | sudo bash -s -- --beta          # akharin pre-release
#
# bedoon argument (curl ... | sudo bash):
#   - aval noskhe porside mishavad (latest / beta / tag-e khas) — Enter = latest
#   - agar nasb-e mojood (panel/node/hub) tashkhis dade shavad → pishfarz UPDATE ast
#   - vagarna menu-ye taamoli az /dev/tty porside mishavad (nasb-e jadid)
#
# repo slug pishfarz l8PYGIT/RatholeEngine ast؛ baraye estefade az fork-e khodet ba mtghir-e mohiti
# override kon:   RATHOLE_GH="youruser/yourrepo" curl -fsSL .../install.sh | sudo bash -s -- ...
set -euo pipefail

# ---------- tanzimat ----------
GH="${RATHOLE_GH:-l8PYGIT/RatholeEngine}"    # owner/repo — pishfarz، ba RATHOLE_GH override kon
REL="${RATHOLE_RELEASE:-latest}"               # latest | beta | yek tag mesl v1.0.0
GH_TOKEN="${RATHOLE_GH_TOKEN:-${GH_TOKEN:-${GITHUB_TOKEN:-}}}"
UPDATE_PROXY="${RATHOLE_UPDATE_PROXY:-}"
REQUIRE_SIG="${RATHOLE_REQUIRE_SIG:-0}"
SIGNING_PUBKEY="${RATHOLE_SIGNING_PUBKEY:-}"
BASE="https://github.com/${GH}/releases"

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_r(){ printf '\033[1;31m%s\033[0m' "$*"; }
c_y(){ printf '\033[1;33m%s\033[0m' "$*"; }
log(){ printf '%s %s\n' "$(c_g '[+]')" "$*"; }
warn(){ printf '%s %s\n' "$(c_y '[*]')" "$*"; }
err(){ printf '%s %s\n' "$(c_r '[!]')" "$*" >&2; }
die(){ err "$*"; exit 1; }

valid_proxy_url(){
  local v="${1:-}"
  [ -n "$v" ] || return 0
  case "$v" in
    *[[:space:]]*|*[[:cntrl:]]*|*';'*|*'|'*|*'&'*|*'$'*|*'`'*|*'"'*|*"'"*|*'?'*|*'#'*|*'<'*|*'>'*|*'\\'*|*'..'*) return 1 ;;
  esac
  [[ "$v" =~ ^(http|https|socks5|socks5h)://[A-Za-z0-9._:@%+-]+(:[0-9]{1,5})?/?$ ]] || return 1
  return 0
}

redact_proxy_url(){
  printf '%s' "${1:-}" | sed -E 's#^([A-Za-z0-9+.-]+://)[^/@]+@#\1***@#'
}

valid_pubkey_path(){
  local p="${1:-}"
  [ -n "$p" ] || return 0
  case "$p" in
    *..*) return 1 ;;
  esac
  [[ "$p" =~ ^/[A-Za-z0-9_./-]{1,255}$ ]]
}

[ "$(id -u)" -eq 0 ] || die "bayad ba root ejra shavad (curl ... | sudo bash -s -- ...)."

# ---------- entekhab-e noskhe (release pinning) ----------
# CHERA flag va na faghat motghayer-e mohiti: dar `RATHOLE_RELEASE=v1 curl ... | sudo bash` an
# motghayer be CURL micshasbad na be bash-e sudo-shode، va `sudo` ham ba env_reset pak-ash mikonad.
# pas karbar amalan hich rahi baraye pin kardan-e noskhe nadasht. flag az har do masir amn ast.
# ARGS-e baghimande dast-nakhorde be bootstrap miravad (--panel/--node/--update/... hamchenan kar mikonad).
RAW_ARGC=$#
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    # Ba separator, baghi-e arg-ha (az jomle token-e node) be bootstrap miravand.
    --) ARGS+=("$@"); break ;;
    --release|--version|-r)
      [ $# -ge 2 ] || die "$1 be yek meghdar niaz darad (masalan: --release v1.8.0 | latest | beta)."
      REL="$2"; shift 2 ;;
    --release=*|--version=*) REL="${1#*=}"; shift ;;
    --token|-t)
      [ $# -ge 2 ] || die "$1 be yek meghdar niaz darad (masalan: --token github_pat_...)."
      GH_TOKEN="$2"; shift 2 ;;
    --token=*) GH_TOKEN="${1#*=}"; shift ;;
    --proxy)
      [ $# -ge 2 ] || die "--proxy be URL-e proxy niaz darad (masalan: socks5h://127.0.0.1:1080)."
      UPDATE_PROXY="$2"; shift 2 ;;
    --proxy=*) UPDATE_PROXY="${1#*=}"; shift ;;
    --require-sig) REQUIRE_SIG=1; shift ;;
    --pubkey)
      [ $# -ge 2 ] || die "--pubkey be masir-e kelid-e omumi niaz darad."
      SIGNING_PUBKEY="$2"; shift 2 ;;
    --pubkey=*) SIGNING_PUBKEY="${1#*=}"; shift ;;
    --beta)   REL="beta"; shift ;;
    --stable) REL="latest"; shift ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
set -- ${ARGS[@]+"${ARGS[@]}"}
if [ -n "$UPDATE_PROXY" ]; then
  valid_proxy_url "$UPDATE_PROXY" || die "URL-e proxy namotabar ast: $(redact_proxy_url "$UPDATE_PROXY")"
fi
if [ -n "$SIGNING_PUBKEY" ]; then
  valid_pubkey_path "$SIGNING_PUBKEY" || die "masir kelid-e omumi namotabar ast: '$SIGNING_PUBKEY'"
fi

# zir-e `curl ... | sudo bash` (ba Defaults use_pty dar Ubuntu/Debian), stdin pipe ast va
# /dev/tty-e jadid-e sudo vorodi keyboard ra nemigirad → `read` ta abad gir mikonad.
sudo_piped_pty(){
  [ ! -t 0 ] && [ -n "${SUDO_USER:-}${SUDO_UID:-}${SUDO_COMMAND:-}" ]
}

# zir-e `curl | bash` mustaghim (root bedoon sudo), agar /dev/tty baz shavad hanooz mitavanim beporsim.
TTY_DEV=""
if [ ! -t 0 ] && ! sudo_piped_pty && { : < /dev/tty; } 2>/dev/null; then TTY_DEV="/dev/tty"; fi

# faghat vaghti karbar NA flag dade va NA env — va terminal darim. Enter = latest.
ask_release(){
  [ -n "${RATHOLE_RELEASE:-}" ] && return 0
  local a="" t="${RTH_READ_TIMEOUT:-10}"
  echo
  echo "$(c_g 'kodam noskhe nasb shavad?')"
  echo "  - Enter        → latest (akharin noskhe-ye paydar — tosiye)"
  echo "  - yek tag      → masalan v1.8.0 (noskhe-ye khas-e montasher-shode)"
  echo "  - beta         → akharin pre-release (azmayeshi)"
  if   [ -n "$TTY_DEV" ]; then IFS= read -rt "$t" -p "entekhab [latest]: " a < "$TTY_DEV" || a=""
  elif [ -t 0 ];         then IFS= read -rt "$t" -p "entekhab [latest]: " a || a=""
  fi
  REL="${a:-latest}"
}

# ---------- nasb-e pish-niaz-e hadaghali ----------
install_prereqs(){
  command -v curl >/dev/null 2>&1 && command -v tar >/dev/null 2>&1 && command -v unzip >/dev/null 2>&1 && return 0
  log "nasb pish-niazha (curl tar unzip ca-certificates)..."
  local pkgs="curl unzip tar ca-certificates"
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    export NEEDRESTART_MODE=a
    export NEEDRESTART_SUSPEND=1
    apt-get update -y && apt-get install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" $pkgs
  elif command -v dnf >/dev/null 2>&1; then dnf install -y $pkgs
  elif command -v yum >/dev/null 2>&1; then yum install -y $pkgs
  elif command -v pacman >/dev/null 2>&1; then pacman -Sy --noconfirm curl unzip tar ca-certificates
  elif command -v apk >/dev/null 2>&1; then apk add --no-cache curl unzip tar ca-certificates bash
  else warn "pkijmnijr shnakhth nshd; motmaen shv curl/unzip/tar nasb-and."; fi
}

fetch1(){ # $1=url $2=out [$3=accept] ; ba curl ya wget (yek talash, bedoon afshay-e token/proxy dar argv)
  local url="$1" out="$2" acc="${3:-}"
  local hdr=() is_gh=0
  echo "$url" | grep -qE '(github\.com|githubusercontent\.com)' && is_gh=1
  [ -n "$acc" ] && hdr=(-H "Accept: $acc")
  # gard-e transfer-e raked: bedoon-e --speed-limit dar surate ekhtelal/filtering-e Iran curl ta abad hang mikonad.
  if command -v curl >/dev/null 2>&1; then
    if { [ -n "$GH_TOKEN" ] && [ "$is_gh" -eq 1 ]; } || [ -n "$UPDATE_PROXY" ]; then
      {
        [ -n "$GH_TOKEN" ] && [ "$is_gh" -eq 1 ] && printf 'header = "Authorization: Bearer %s"\n' "$GH_TOKEN"
        [ -n "$UPDATE_PROXY" ] && printf 'proxy = "%s"\n' "$UPDATE_PROXY"
      } | curl --config - -fSL "${hdr[@]}" --connect-timeout 15 --speed-limit 1024 --speed-time 20 --retry 2 "$url" -o "$out"
    else
      curl -fSL "${hdr[@]}" --connect-timeout 15 --speed-limit 1024 --speed-time 20 --retry 2 "$url" -o "$out"
    fi
  elif command -v wget >/dev/null 2>&1; then
    case "$UPDATE_PROXY" in
      socks*) warn "wget az proxy-e SOCKS5 poshtibani nemikonad; curl lazem ast."; return 1 ;;
    esac
    if [ -n "$GH_TOKEN" ] && [ "$is_gh" -eq 1 ]; then
      local wcfg; wcfg="$(umask 077 && mktemp)"
      printf 'header = Authorization: Bearer %s\n' "$GH_TOKEN" > "$wcfg"
      [ -n "$acc" ] && printf 'header = Accept: %s\n' "$acc" >> "$wcfg"
      if [ -n "$UPDATE_PROXY" ]; then
        http_proxy="$UPDATE_PROXY" https_proxy="$UPDATE_PROXY" wget -q --config="$wcfg" --timeout=20 --tries=2 -O "$out" "$url"
      else
        wget -q --config="$wcfg" --timeout=20 --tries=2 -O "$out" "$url"
      fi
      local wrc=$?; rm -f "$wcfg"; return "$wrc"
    else
      local wh=()
      [ -n "$acc" ] && wh=(--header="Accept: $acc")
      if [ -n "$UPDATE_PROXY" ]; then
        http_proxy="$UPDATE_PROXY" https_proxy="$UPDATE_PROXY" wget -q "${wh[@]}" --timeout=20 --tries=2 -O "$out" "$url"
      else
        wget -q "${wh[@]}" --timeout=20 --tries=2 -O "$out" "$url"
      fi
    fi
  else return 1; fi
}

# mirror-haye ghproxy baraye dor zadan-e filtering-e GitHub az dakhl-e Iran (hamsan-e install-panel.sh).
# dar soorat-e repo-ye private (GH_TOKEN) ya proxy-e sarih (UPDATE_PROXY), mirror-haye omoomi estefade nemishavand.
if [ -n "$GH_TOKEN" ] || [ -n "$UPDATE_PROXY" ]; then
  RATHOLE_MIRRORS=("")
else
  RATHOLE_MIRRORS=("" "https://ghproxy.net/" "https://gh-proxy.com/" "https://mirror.ghproxy.com/")
fi

fetch(){ # $1=url (kamel، mesl https://github.com/...) $2=out ; mostaghim، sps mirror-ha
  local url="$1" out="$2" m
  for m in "${RATHOLE_MIRRORS[@]}"; do
    if fetch1 "${m}${url}" "$out"; then return 0; fi
    [ -n "$m" ] && warn "in mirror javab nadad، badi..."
  done
  return 1
}

verify_sums_ed25519(){ # $1=sha_file $2=sig_file $3=pubkey $4=require_sig
  local sha_file="${1:-}" sig_file="${2:-}" pub="${3:-}" req="${4:-0}" cand
  if [ -z "$sha_file" ] || [ ! -s "$sha_file" ]; then
    [ "$req" = "1" ] && die "emza-ye Ed25519 elzami ast vali SHA256SUMS daryaft nashod."
    return 0
  fi
  if [ -z "$sig_file" ] || [ ! -s "$sig_file" ]; then
    [ "$req" = "1" ] && die "emza-ye Ed25519 elzami ast vali SHA256SUMS.sig daryaft nashod."
    return 0
  fi
  if [ -z "$pub" ]; then
    for cand in /usr/local/share/rathole/keys/release-ed25519.pub; do
      [ -s "$cand" ] && { pub="$cand"; break; }
    done
  fi
  if [ -z "$pub" ] || [ ! -s "$pub" ]; then
    [ "$req" = "1" ] && die "emza-ye Ed25519 elzami ast vali kelid-e omumi (release-ed25519.pub) peyda nashod."
    warn "SHA256SUMS.sig daryaft shod vali kelid-e omumi nasb nist; tayid-e Ed25519 rad shod."
    return 0
  fi
  command -v openssl >/dev/null 2>&1 || die "openssl baraye tayid-e emza-ye Ed25519 lazem ast."
  local raw_sig ok=0 sz=0
  raw_sig="$(mktemp)"
  if tr -d ' \t\r\n' < "$sig_file" | base64 -d > "$raw_sig" 2>/dev/null; then
    sz="$(wc -c < "$raw_sig" | tr -d '[:space:]')"
    [ "$sz" = "64" ] && ok=1
  fi
  if [ "$ok" -eq 0 ]; then
    sz="$(wc -c < "$sig_file" | tr -d '[:space:]')"
    if [ "$sz" = "64" ] && cp "$sig_file" "$raw_sig" 2>/dev/null; then
      ok=1
    fi
  fi
  [ "$ok" -eq 1 ] || { rm -f "$raw_sig"; die "format-e emza-ye Ed25519 dar SHA256SUMS.sig namotabar ast!"; }
  if ! openssl pkeyutl -verify -pubin -inkey "$pub" -rawin -sigfile "$raw_sig" -in "$sha_file" >/dev/null 2>&1; then
    rm -f "$raw_sig"
    die "emza-ye Ed25519 baraye SHA256SUMS motabar NIST (ehtemal-e dastkari)!"
  fi
  rm -f "$raw_sig"
  log "emza-ye Ed25519 SHA256SUMS tayid shod."
}

# akharin tag-e pre-release (beta/rc/alpha) ra az atom-e GitHub darmiavarad.
# CHERA atom: masir-e `releases/latest/download` pre-release ha ra NADIDE migirad، pas baraye
# beta bayad tag-e daghigh ra bedanim. api.github.com az mirror-haye ghproxy obur nemikonad
# vali github.com/<slug>/releases.atom mikonad — va be jq ham niaz nadarad.
# (hamsan-e resolve_beta_tag dar rathole-manager/common.sh؛ inja copy ast chon install.sh
#  be sooratِ mostaghel ba curl|bash ejra mishavad va common.sh hanooz nasb nashode.)
resolve_beta_tag(){
  local m out tag at_tmp
  at_tmp="$(mktemp)"
  for m in "${RATHOLE_MIRRORS[@]}"; do
    fetch1 "${m}https://github.com/${GH}/releases.atom" "$at_tmp" 2>/dev/null || continue
    out="$(cat "$at_tmp" 2>/dev/null || true)"
    # '|| true' ALZAMI ast: install.sh ba 'set -e' ejra mishavad va agar grep hich beta-i
    # peyda nakonad، in enteshab non-zero mishavad va script vasat-e kar mimirad.
    tag="$(printf '%s' "$out" \
      | grep -oE 'releases/tag/v[0-9A-Za-z._-]+' \
      | sed 's#.*releases/tag/##' \
      | grep -E -- '-(beta|rc|alpha)' \
      | head -n1 || true)"
    if [ -n "$tag" ]; then rm -f "$at_tmp"; printf '%s\n' "$tag"; return 0; fi
  done
  rm -f "$at_tmp"
  return 1
}

# masir-e download ra bar asas-e kanal moshakhas mikonad (baad az tarif-e fetch/die چون beta be shabake niaz darad).
resolve_dl(){
  case "$REL" in
    stable) REL="latest" ;;
  esac
  if [ "$REL" = "beta" ]; then
    log "peyda kardan-e akharin noskhe-ye beta..."
    REL="$(resolve_beta_tag)" || die "hich noskhe-ye beta-i montasher nashode (ya dastresi be GitHub nist)."
    warn "kanal-e BETA: $(c_y "$REL") — noskhe-ye azmayeshi، momken ast paydar nabashad."
  fi
  # tag ra etebar-sanji kon: in meghdar dar URL miayad، pas kharakter-e gheyr-mojaz nabayad
  # dashte bashad (jelogiri az path-traversal/tazrigh dar masir-e download).
  if [ "$REL" != "latest" ]; then
    case "$REL" in
      v[0-9]*|[0-9]*) : ;;
      *) die "tag-e noskhe namotabar: '$REL' (masalan: v1.8.0 | latest | beta)." ;;
    esac
    printf '%s' "$REL" | grep -qE '^[0-9A-Za-z._-]+$' \
      || die "tag-e noskhe namotabar: '$REL' (faghat harf/adad/. _ - mojaz ast)."
  fi
  if [ "$REL" = "latest" ]; then DL="$BASE/latest/download"; else DL="$BASE/download/$REL"; fi
}

main(){
  install_prereqs
  local tmp; tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT

  # faghat agar hich flag-i dade nashode va stdin vaghean terminal ast ([ -t 0 ]).
  # agar karbar flag dade ya pipe ast (curl | sudo bash), hargez gir nakon va mostaghim be latest boro.
  if [ "$RAW_ARGC" -eq 0 ] && [ -z "$GH_TOKEN" ] && [ "$REL" = "latest" ] && [ -z "${RATHOLE_RELEASE:-}" ] && [ -t 0 ]; then
    ask_release
  fi

  resolve_dl
  [ -n "$UPDATE_PROXY" ] && log "masir proxy baraye download: $(c_y "$(redact_proxy_url "$UPDATE_PROXY")")"
  log "download az GitHub release: $(c_y "$GH ($REL)")"
  local bundle="" sha_file="" sig_file="" priv_ok=0

  # dar repo-ye private ba token, GitHub URL-haye mastaghim-e browser 404 midahand; aval release API ra check kon.
  if [ -n "$GH_TOKEN" ] && command -v python3 >/dev/null 2>&1; then
    local api="https://api.github.com/repos/${GH}"
    local ep="$api/releases/latest"
    [ "$REL" = "latest" ] || ep="$api/releases/tags/$REL"
    if fetch1 "$ep" "$tmp/release.json" "application/vnd.github+json" 2>/dev/null; then
      local meta=""
      meta="$(python3 - "$tmp/release.json" <<'PY' 2>/dev/null || true
import json, sys
assets = json.load(open(sys.argv[1], encoding='utf-8')).get('assets', [])
def aid(name):
    for a in assets:
        if a.get('name') == name and isinstance(a.get('id'), int) and a['id'] > 0:
            return str(a['id'])
    return ''
bs = aid('bootstrap.sh')
bd = aid('rathole-manager.zip'); ext = 'zip'
if not bd:
    bd = aid('rathole-manager.tar.gz'); ext = 'tar.gz'
sh = aid('SHA256SUMS')
sg = aid('SHA256SUMS.sig')
if bs and bd:
    print(bs, bd, ext, sh or '-', sg or '-')
PY
)"
      if [ -n "$meta" ]; then
        local bs_id bd_id bd_ext sh_id sg_id
        read -r bs_id bd_id bd_ext sh_id sg_id <<<"$meta"
        if fetch1 "$api/releases/assets/$bs_id" "$tmp/bootstrap.sh" "application/octet-stream" && \
           fetch1 "$api/releases/assets/$bd_id" "$tmp/rathole-manager.$bd_ext" "application/octet-stream"; then
          bundle="$tmp/rathole-manager.$bd_ext"
          if [ "$sh_id" != "-" ]; then
            fetch1 "$api/releases/assets/$sh_id" "$tmp/SHA256SUMS" "application/octet-stream" 2>/dev/null && sha_file="$tmp/SHA256SUMS" || true
          fi
          if [ "$sg_id" != "-" ]; then
            fetch1 "$api/releases/assets/$sg_id" "$tmp/SHA256SUMS.sig" "application/octet-stream" 2>/dev/null && sig_file="$tmp/SHA256SUMS.sig" || true
          fi
          priv_ok=1
        fi
      fi
    fi
  fi

  if [ "$priv_ok" -eq 0 ]; then
    # 1) bootstrap.sh (mantegh-e amade-sazi va nasb)
    if ! fetch "$DL/bootstrap.sh" "$tmp/bootstrap.sh"; then
      if [ -n "$GH_TOKEN" ]; then
        local raw_ref="${REL}"
        [ "$raw_ref" = "latest" ] && raw_ref="main"
        log "talash-e daryaft bootstrap.sh az private raw content (${raw_ref})..."
        fetch "https://raw.githubusercontent.com/${GH}/${raw_ref}/bootstrap.sh" "$tmp/bootstrap.sh" || {
          err "download bootstrap.sh az repo-ye private shekast khord."
          exit 1
        }
      else
        err "download bootstrap.sh az release shekast khord: $DL/bootstrap.sh"
        err "elal-e ehtemali: release hanooz montasher nashode (tag v* push kon)، slug eshtebah، ya filtering."
        err "rah-e jaygozin: baste ra dasti begir va bootstrap.sh ra ba --local ejra kon (docs/README.fa.md)."
        exit 1
      fi
    fi
    # 2) baste-ye asli
    if fetch "$DL/rathole-manager.zip" "$tmp/rathole-manager.zip"; then
      bundle="$tmp/rathole-manager.zip"
    elif fetch "$DL/rathole-manager.tar.gz" "$tmp/rathole-manager.tar.gz"; then
      bundle="$tmp/rathole-manager.tar.gz"
    elif [ -n "$GH_TOKEN" ]; then
      log "download archive az API-ye private repository..."
      local api_ref="${REL}"
      [ "$api_ref" = "latest" ] && api_ref="main"
      if fetch "https://api.github.com/repos/${GH}/tarball/${api_ref}" "$tmp/bundle.tar.gz"; then
        bundle="$tmp/bundle.tar.gz"
      else
        die "download archive az API-ye private repository shekast khord."
      fi
    else
      die "download baste (rathole-manager.zip/.tar.gz) az release shekast khord: $DL"
    fi
    fetch "$DL/SHA256SUMS" "$tmp/SHA256SUMS" 2>/dev/null && sha_file="$tmp/SHA256SUMS" || rm -f "$tmp/SHA256SUMS"
    fetch "$DL/SHA256SUMS.sig" "$tmp/SHA256SUMS.sig" 2>/dev/null && sig_file="$tmp/SHA256SUMS.sig" || rm -f "$tmp/SHA256SUMS.sig"
  fi

  verify_sums_ed25519 "$sha_file" "$sig_file" "$SIGNING_PUBKEY" "$REQUIRE_SIG"
  if [ -n "$sha_file" ] && [ -s "$sha_file" ] && command -v sha256sum >/dev/null 2>&1; then
    local bbase; bbase="$(basename "$bundle")"
    if grep -qE "[[:space:]](\./)?${bbase}$" "$sha_file" 2>/dev/null; then
      ( cd "$tmp" && grep -E "[[:space:]](\./)?${bbase}$" "$sha_file" | sha256sum -c - --quiet ) \
        || die "checksum SHA256 baste ($bbase) motabeghat nadarad!"
      log "checksum SHA256 baste tayid shod ($bbase)."
    elif [ "$REQUIRE_SIG" = "1" ]; then
      die "checksum baste ($bbase) dar SHA256SUMS nist!"
    fi
    if [ -f "$tmp/bootstrap.sh" ] && grep -qE '[[:space:]](\./)?bootstrap\.sh$' "$sha_file" 2>/dev/null; then
      ( cd "$tmp" && grep -E '[[:space:]](\./)?bootstrap\.sh$' "$sha_file" | sha256sum -c - --quiet ) \
        || die "checksum SHA256 bootstrap.sh motabeghat nadarad!"
    fi
  fi
  log "baste daryaft shod: $(basename "$bundle")  ($(du -h "$bundle" 2>/dev/null | cut -f1))"

  # 3) tahvil be bootstrap.sh (hameye argvman-haye passed be bootstrap miravand)
  # token-haye GitHub ra ghabl az ejra-ye bootstrap pak mikonim ta dar env-e child baghi namanad.
  # az `exec` estefade NEMIKONIM ta EXIT trap file-haye movaghat dar $tmp ra pak konad.
  log "ejra-ye bootstrap..."
  unset GH_TOKEN RATHOLE_GH_TOKEN GITHUB_TOKEN
  export RATHOLE_GH="$GH" RATHOLE_RELEASE="$REL"
  export RATHOLE_REQUIRE_SIG="$REQUIRE_SIG"
  [ -n "$SIGNING_PUBKEY" ] && export RATHOLE_SIGNING_PUBKEY="$SIGNING_PUBKEY"
  [ -n "$UPDATE_PROXY" ] && export RATHOLE_UPDATE_PROXY="$UPDATE_PROXY"
  local rc=0
  if sudo_piped_pty; then
    warn "zir-e 'curl | sudo bash' dastresi-e keyboard be sudo pty baste ast؛ edame dar halat-e bedoon-prompt."
    export RATHOLE_NO_TTY=1
    bash "$tmp/bootstrap.sh" --local "$bundle" "$@" || rc=$?
  elif [ ! -t 0 ] && [ -r /dev/tty ] && { : < /dev/tty; } 2>/dev/null; then
    bash "$tmp/bootstrap.sh" --local "$bundle" "$@" < /dev/tty || rc=$?
  else
    bash "$tmp/bootstrap.sh" --local "$bundle" "$@" || rc=$?
  fi
  exit "$rc"
}

main "$@"
