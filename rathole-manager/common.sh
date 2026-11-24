# common.sh — tavabe eshteraki beyn ratholectl, ratholenode va nsabha
# in file tvst source frakhvani mishvd; be tnhaii ejra nemishavad.

# noskhe-ye rathole-manager (panel/node/hub). moqe-e release in adad ba tag hamahang mishavad.
# package.sh/CI mitavanad in ra be tag-e vaghei stamp konad; agar dast taghir dadi، bedoon 'v' bezar.
MANAGER_VERSION="2.3.0"

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_r(){ printf '\033[1;31m%s\033[0m' "$*"; }
c_y(){ printf '\033[1;33m%s\033[0m' "$*"; }
log(){ printf '%s %s\n' "$(c_g '[+]')" "$*"; }
warn(){ printf '%s %s\n' "$(c_y '[*]')" "$*"; }
err(){ printf '%s %s\n' "$(c_r '[!]')" "$*" >&2; }
die(){ err "$*"; exit 1; }
need_root(){ [ "$(id -u)" -eq 0 ] || die "bayad ba root ejra shavad (sudo)."; }

# ---------- porsesh-e taamoli-ye amn (tty-safe + bounded) ----------
# CHERA (bug-e «nasb dar marhale-ye tanzimat-e avalie saat-ha motevaghef mishavad»):
#   1) `read -rp` rooye stdin-e GHEYR-terminal (curl|bash vaghti producer hanooz pipe ra
#      nabaste — link-e kond/filter-shode az Iran —، kanal-e SSH، hub) TA ABAD montazer
#      mimanad. bad-tar: bash prompt-e `read -p` ra FAGHAT vaghti minevisad ke vorodi
#      terminal bashad، pas karbar hich payami nemibinad va nasb bi-seda mimirad.
#   2) `[ -r /dev/tty ]` DOROGH migoyad: node-e device hamishe readable ast hatta vaghti
#      process controlling terminal NADARAD — pas shakhes-e «tty darim» nist.
# tanha rah-e motmaen BAZ KARDAN-e /dev/tty ast (haman elgo-ye dorost-e bootstrap.sh).
# agar hich tty-ye vaghei nabashad HARGEZ montazer nemimanim (meghdar-e khali barmigardad).
RTH_TTY=""
if [ ! -t 0 ] && { : < /dev/tty; } 2>/dev/null; then
  exec < /dev/tty
fi
if [ ! -t 0 ] && { : < /dev/tty; } 2>/dev/null; then RTH_TTY="/dev/tty"; fi
has_tty(){ [ -t 0 ] || [ -n "$RTH_TTY" ]; }

# backstop-e zamani: hatta ba tty-ye VAGHEI (masalan screen/tmux-e detach-shode ya terminal-i
# ke kasi payash nist) nabayad ta abad gir konim. sanie — ba RTH_READ_TIMEOUT ghabl-e taghir.
# ghofl-e state (fd 9) nabayad hengam-e entezar baraye TAYP-e karbar negah dashte shavad:
# `menu` yek halghe-ye taamoli-ye bi-payan ast va `init` montazer-e javab mimanad. dar in
# modat HAR ratholectl-e digar (masalan action-e hub az SSH) 30 sanie gir mikard va baad
# BI-GHOFL edame midad — yaani haman mohafezat-e lost-update dor mizad. pas ghabl az read
# ghofl ra AZAD mikonim va baad az javab DOBARE migirim; read-modify-write-e mutator-ha
# hamchenan kamel zir-e ghofl ejra mishavad (next_port/jq baad az porsesh-ha miayad).
# RTH_LOCK_HELD tanha dar masir-e flock set mishavad; fallback-e mkdir (sistem-haye bedoon-e
# flock) hamchenan ghofl ra negah midarad — nadir ast va sadegi mohem-tar.
RTH_LOCK_HELD=0
rth_lock_pause(){ if [ "${RTH_LOCK_HELD:-0}" = 1 ]; then flock -u 9 2>/dev/null || true; fi; }
rth_lock_resume(){
  if [ "${RTH_LOCK_HELD:-0}" = 1 ]; then
    flock -w 30 9 2>/dev/null || warn "ghofl-e state pas az javab azad nashod (30s); edame midaham."
  fi
}

rth_read(){   # estefade: rth_read VAR "prompt"
  local __v="$1" __p="${2:-}" __a="" __t="${RTH_READ_TIMEOUT:-300}"
  rth_lock_pause
  if [ -t 0 ]; then read -rt "$__t" -p "$__p" __a
  elif [ -n "$RTH_TTY" ]; then read -rt "$__t" -p "$__p" __a < "$RTH_TTY"
  else __a=""; fi
  rth_lock_resume
  printf -v "$__v" '%s' "$__a"
}
# bedoon-e tty (ya baad az timeout) javab HAMISHE «na» ast — pishfarz-e amn baraye
# porsesh-haye makhrab (hazf/bazneveshtan).
ask_yn(){ local a; rth_read a "$1 [y/N]: "; [[ "$a" =~ ^[Yy]$ ]]; }

# mirror-haye ghproxy baraye dor-zadan-e filtering-e Iran (hamsan-e install-panel.sh).
RTH_MIRRORS=("" "https://ghproxy.net/" "https://gh-proxy.com/" "https://mirror.ghproxy.com/")

# etebar-sanji-ye proxy URL (bedoon-e metacharacter-e shell va query/fragment)
rth_valid_proxy_url(){
  local v="${1:-}"
  [ -n "$v" ] || return 0
  case "$v" in
    *[[:space:]]*|*[[:cntrl:]]*|*';'*|*'|'*|*'&'*|*'$'*|*'`'*|*'"'*|*"'"*|*'?'*|*'#'*|*'<'*|*'>'*|*'\\'*|*'..'*) return 1 ;;
  esac
  [[ "$v" =~ ^(http|https|socks5|socks5h)://[A-Za-z0-9._:@%+-]+(:[0-9]{1,5})?/?$ ]] || return 1
  return 0
}

rth_redact_proxy_url(){
  printf '%s' "${1:-}" | sed -E 's#^([A-Za-z0-9+.-]+://)[^/@]+@#\1***@#'
}

# peyda kardan-e kelid-e omumi-ye Ed25519 baraye tayid-e SHA256SUMS.sig
rth_find_signing_pubkey(){
  local cand base=""
  [ -n "${BASH_SOURCE[0]:-}" ] && base="${BASH_SOURCE[0]%/*}"
  for cand in "${RATHOLE_SIGNING_PUBKEY:-}" /usr/local/share/rathole/keys/release-ed25519.pub "${base:+$base/keys/release-ed25519.pub}"; do
    [ -n "$cand" ] && [ -s "$cand" ] && { printf '%s\n' "$cand"; return 0; }
  done
  return 1
}

# tayid-e emza-ye Ed25519 (SHA256SUMS + SHA256SUMS.sig).
# ghaede:
#   - agar sig mojood bashad va namotabar bashad → HAMISHE error (hatta agar require_sig=0).
#   - agar require_sig=1 bashad → naboodan-e sig ya pubkey ya openssl error midahad.
# $1=file $2=sig_file (default $1.sig) $3=pubkey (optional) $4=require_sig (default ${RATHOLE_REQUIRE_SIG:-0})
rth_verify_ed25519(){
  local file="${1:-}" sig="${2:-${1:-}.sig}" pub="${3:-}" req="${4:-${RATHOLE_REQUIRE_SIG:-0}}"
  [ -f "$file" ] || { err "file baraye tayid peyda nashod: $file"; return 1; }
  if [ ! -s "$sig" ]; then
    if [ "$req" = "1" ]; then
      err "emza-ye Ed25519 elzami ast vali peyda nashod: $sig"
      return 1
    fi
    return 0
  fi
  if [ -z "$pub" ]; then
    pub="$(rth_find_signing_pubkey || true)"
  fi
  if [ -z "$pub" ] || [ ! -s "$pub" ]; then
    if [ "$req" = "1" ]; then
      err "emza-ye Ed25519 elzami ast vali kelid-e omumi (release-ed25519.pub) peyda nashod."
      return 1
    fi
    warn "file-e emza ($sig) vojood darad vali kelid-e omumi nasb nist; tayid-e Ed25519 rad shod."
    return 0
  fi
  if ! command -v openssl >/dev/null 2>&1; then
    err "openssl baraye tayid-e Ed25519 lazem ast ($sig)."
    return 1
  fi
  local raw_sig ok=0 sz=0
  raw_sig="$(mktemp)"
  if tr -d ' \t\r\n' < "$sig" | base64 -d > "$raw_sig" 2>/dev/null; then
    sz="$(wc -c < "$raw_sig" | tr -d '[:space:]')"
    [ "$sz" = "64" ] && ok=1
  fi
  if [ "$ok" -eq 0 ]; then
    sz="$(wc -c < "$sig" | tr -d '[:space:]')"
    if [ "$sz" = "64" ] && cp "$sig" "$raw_sig" 2>/dev/null; then
      ok=1
    fi
  fi
  if [ "$ok" -ne 1 ]; then
    rm -f "$raw_sig"
    err "format-e emza-ye Ed25519 namotabar ast: $sig"
    return 1
  fi
  if ! openssl pkeyutl -verify -pubin -inkey "$pub" -rawin -sigfile "$raw_sig" -in "$file" >/dev/null 2>&1; then
    rm -f "$raw_sig"
    err "emza-ye Ed25519 motabar NIST! ehtemal-e dastkari: $file"
    return 1
  fi
  rm -f "$raw_sig"
  log "emza-ye Ed25519 tayid shod ($(basename "$file"))."
  return 0
}

# akharin tag-e pre-release (beta/rc/alpha) ra peyda mikonad. $1 = slug-e owner/repo.
# CHERA atom va na API: masir-e `releases/latest/download` dar GitHub pre-release ha ra
# NADIDE migirad, pas baraye beta bayad tag-e daghigh ra bedanim. api.github.com az mirror-haye
# ghproxy obur nemikonad vali github.com/<slug>/releases.atom mikonad — va atom ham be jq niaz
# nadarad (dar node-e taze-nasb momken ast jq nabashad). tartib-e atom: jadidtarin aval.
resolve_beta_tag(){
  local gh="$1" proxy="${2:-${RATHOLE_UPDATE_PROXY:-}}" m out tag
  if [ -n "$proxy" ]; then
    rth_valid_proxy_url "$proxy" || return 1
    out="$(printf 'proxy = "%s"\n' "$proxy" | curl --config - -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 15 --retry 1 "https://github.com/${gh}/releases.atom" 2>/dev/null)" || return 1
    tag="$(printf '%s' "$out" \
      | grep -oE 'releases/tag/v[0-9A-Za-z._-]+' \
      | sed 's#.*releases/tag/##' \
      | grep -E -- '-(beta|rc|alpha)' \
      | head -n1)"
    [ -n "$tag" ] && { printf '%s\n' "$tag"; return 0; }
    return 1
  fi
  for m in "${RTH_MIRRORS[@]}"; do
    out="$(curl -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 15 --retry 1 "${m}https://github.com/${gh}/releases.atom" 2>/dev/null)" || continue
    tag="$(printf '%s' "$out" \
      | grep -oE 'releases/tag/v[0-9A-Za-z._-]+' \
      | sed 's#.*releases/tag/##' \
      | grep -E -- '-(beta|rc|alpha)' \
      | head -n1)"
    [ -n "$tag" ] && { printf '%s\n' "$tag"; return 0; }
  done
  return 1
}

# neveshtan-e amn-e in-place ba lock-e sidecar (hefz inode baraye hot-reload-e rathole).
# $1 = file-e movaqqat (generated); $2 = file-e live (masir-e vaghei config).
# agar src khali bashad (0 byte) rad mikonad ta rathole config-e naghes nabinad.
# flock hamishe mojood nist (image-e minimal bedoon-e util-linux، MSYS/Git-Bash). ghablan
# nabudanash BI-SEDA ghofl ra az beyn mibord: `flock: command not found` be stderr miraft
# vali subshell rc=0 barmigardand — pas `|| return 1` fael nemishod va config BEDOON-e ghofl
# neveshte mishod. do neveshtan-e hamzaman → config-e nim-kare ke rathole hot-reload mikonad.
# pas yek bar tashkhis midahim va agar nabood az mkdir (atomic dar POSIX) ghofl misazim.
_RTH_HAS_FLOCK=""
_rth_has_flock(){
  [ -n "$_RTH_HAS_FLOCK" ] || { command -v flock >/dev/null 2>&1 && _RTH_HAS_FLOCK=1 || _RTH_HAS_FLOCK=0; }
  [ "$_RTH_HAS_FLOCK" = 1 ]
}

rth_commit_config(){
  local src="$1" dst="$2" lock="${2}.lock"
  [ -s "$src" ] || { err "config-e jadid khali ast: $src"; return 1; }
  mkdir -p "$(dirname "$dst")"
  if _rth_has_flock; then
    (
      flock -x 9
      cat "$src" > "$dst"
    ) 9>"$lock" || return 1
  else
    # fallback-e portable: mkdir atomic ast. ta ~5 sanie montazer mimanim؛ agar ghofl azad
    # nashod (masalan process-e ghabli mord va lockdir mande) HOSHDAR midahim va edame —
    # gir kardan-e hamishegi bad-tar az neveshtan-e bedoon-e ghofl ast.
    local d="${dst}.lockd" i=0 held=0 rc=0
    while [ "$i" -lt 50 ]; do
      if mkdir "$d" 2>/dev/null; then held=1; break; fi
      i=$((i+1)); sleep 0.1 2>/dev/null || sleep 1
    done
    [ "$held" -eq 1 ] || warn "ghofl-e '$dst' azad nashod (timeout); bedoon-e ghofl minevisam."
    cat "$src" > "$dst" || rc=1
    [ "$held" -eq 1 ] && rmdir "$d" 2>/dev/null
    [ "$rc" -eq 0 ] || return 1
  fi
  chmod 600 "$dst" 2>/dev/null || true
  rm -f "$src"
}


# chap-e noskhe — ham baraye ensan ham machine-parseable (hub 'manager_version=' ra migirad).
# $1=role (panel|node|hub) faghat baraye namayesh; rathole-version az binari khande mishavad.
print_version(){
  local role="${1:-?}" rv
  rv="$(rathole --version 2>/dev/null | head -n1 | awk '{print $NF}')"
  [ -n "$rv" ] || rv="-"
  echo "manager_version=${MANAGER_VERSION}"
  echo "role=${role}"
  echo "rathole_version=${rv}"
}

# ---------- tashkhis-e poshtibani-ye core az `path` dar websocket ----------
# CHERA: rathole-e upstream (v0.5.0) dar [*.transport.websocket] FAGHAT `tls` ra mipazirad
# (serde ba deny_unknown_fields) — pas `path` KOL-e config ra rad mikonad va client
# crash-loop mishavad. core-e patch-shode-ye ma (core/patches/0001-websocket-retry-path.patch)
# field-e `path` ra ba default "/" ezafe mikonad.
# TAVAJOH: rathole flag-e `--check` NADARAD (faghat -s/-c/--genkey/--version) — pas
# etebar-sanji bayad az rah-e ejra-ye vaghei ba timeout anjam shavad.
# khoruji: rc=0 → poshtibani mikonad، rc=1 → nemikonad (ya nashenakhte → amn: na).
rathole_supports_ws_path(){
  local bin="${1:-/usr/local/bin/rathole}"
  [ -x "$bin" ] || return 1
  # 1) core-e khodemAn: build.sh version ra be '<x.y.z>-ratholeengine.N' pin mikonad.
  "$bin" --version 2>/dev/null | grep -qi 'ratholeengine' && return 0
  # 2) fallback baraye binary-haye digar: config-e test ba `path` bede.
  #    bedoon-e patch: "unknown field `path`" va marg-e foori.
  #    ba patch: config parse mishavad va soraghe ettesal miravad (ke timeout mikoshadesh).
  command -v mktemp >/dev/null 2>&1 || return 1
  local t out; t="$(mktemp)" || return 1
  cat >"$t" <<'RHPROBE'
[client]
remote_addr = "127.0.0.1:1"
[client.transport]
type = "websocket"
[client.transport.websocket]
tls = false
path = "/_probe"
[client.services.probe]
token = "probe"
local_addr = "127.0.0.1:1"
RHPROBE
  out="$(timeout 5 "$bin" -c "$t" 2>&1 | head -n 20)"
  rm -f "$t"
  echo "$out" | grep -qiE 'unknown field.*path' && return 1
  return 0
}

# profile FEC → "datashard parityshard mode sndwnd rcvwnd"
kcp_profile(){
  case "${1:-balanced}" in
    balanced)   echo "10 3 fast2 2048 2048" ;;
    lossy)      echo "10 5 fast2 2048 2048" ;;
    aggressive) echo "10 4 fast3 4096 4096" ;;
    *) return 1 ;;
  esac
}

# nasb kcptun (server|client)
install_kcptun(){
  local role="$1" bin="/usr/local/bin/kcptun-$1" ver="${KCPTUN_VER:-v20260129}" base="${KCPTUN_BASE:-https://github.com/ossfork/kcptun/releases/download}" arch tmp url
  [ -x "$bin" ] && return 0
  case "$(uname -m)" in x86_64) arch=amd64 ;; aarch64) arch=arm64 ;; armv7l) arch=armv7 ;; *) die "memari poshtibani nemishavad." ;; esac
  command -v curl >/dev/null 2>&1 || die "curl lazem ast."
  log "download kcptun ${ver} ($role)..."
  tmp="$(mktemp -d)"
  url="${base}/${ver}/kcptun_linux_${arch}.tar.gz"
  # gard-e transfer-e raked (bebin tozih dar install-node.sh): bedoon-e in, curl zir-e DPI
  # ta abad montazer mimanad chon ettesal bargharar shode vali dade nemiayad.
  curl -fsSL --connect-timeout 20 --speed-limit 1024 --speed-time 30 --retry 2 \
       "$url" -o "$tmp/k.tgz" || { rm -rf "$tmp"; die "download kcptun shekast khord."; }
  tar -xzf "$tmp/k.tgz" -C "$tmp" || { rm -rf "$tmp"; die "baz kardan arshiv kcptun shekast khord."; }
  install -m755 "$tmp/${role}_linux_${arch}" "$bin" || { rm -rf "$tmp"; die "nasb bainri kcptun shekast khord."; }
  rm -rf "$tmp"
  log "kcptun-$role nasb shod: $bin"
}

# profile mux-e backhaul (SMUX) → "mux_con mux_version mux_framesize mux_recievebuffer mux_streambuffer connection_pool"
# HAR DO taraf (server/client) bayad haman profile ra dashte bashand ta parametrhaye SMUX yeksan bemanad.
# nokte: 'mux_con' faghat samt-e server mani darad va 'connection_pool' faghat samt-e client —
# har taraf field-e marbut be khodash ra minevisad va baghi ra dor mirizad.
backhaul_mux_profile(){
  case "${1:-balanced}" in
    balanced)   echo "8 1 32768 4194304 65536 8" ;;
    lossy)      echo "4 1 32768 4194304 65536 6" ;;
    aggressive) echo "16 2 65536 8388608 131072 12" ;;
    *) return 1 ;;
  esac
}

# transport-e client az roo-ye transport-e server: TLS FAGHAT ru-ye nginx terminate mishavad,
# pas server hamishe variant-e bedoon-e TLS ast (ws/wsmux) va client variant-e TLS-dar (wss/wssmux)
# ra be nginx:443 mizanad — daghighan haman invariant-e rathole (server tls=false, client tls=true).
backhaul_client_transport(){
  case "${1:-wsmux}" in
    ws)    echo "wss" ;;
    wsmux) echo "wssmux" ;;
    *) return 1 ;;
  esac
}

# nasb backhaul (server|client). binary-e Go tak-fail ast; role faghat dar esm-e khoruji tafavot darad.
# ba halqe-ye mirror ta az dakhel Iran (filtr/thrim github) ham javab begirad — haman elgo-ye install-panel.
# binary-e patch-shode-ye ma (uTLS ClientHello-ye Chrome) agar kenar-e script-ha bashad.
# masir hamsan-e core-e rathole: <SHARE>/core-backhaul/<target>/backhaul + SHA256SUMS.
# idempotent: agar binary-e nasb-shode HAMIN core bashad، dast nemizanad (rc=0).
# bargasht: 0 agar core-e dorost sar-e jash bashad. RATHOLE_NO_CORE_BACKHAUL=1 in masir ra rad mikonad.
install_backhaul_core(){
  # RATHOLE_BIN_DIR faghat baraye test ast (masir-e vaghei /usr/local/bin).
  local role="$1" bin="${RATHOLE_BIN_DIR:-/usr/local/bin}/backhaul-$1" d target want have
  [ "${RATHOLE_NO_CORE_BACKHAUL:-0}" = 1 ] && return 1
  case "$(uname -m)" in x86_64) target=linux-amd64 ;; aarch64) target=linux-arm64 ;; *) return 1 ;; esac
  for d in "${RATHOLE_CORE_BACKHAUL_DIR:-}" /usr/local/share/rathole/core-backhaul \
           "${BASH_SOURCE[0]%/*}/core-backhaul"; do
    [ -n "$d" ] && [ -f "$d/$target/backhaul" ] && [ -f "$d/SHA256SUMS" ] || continue
    if declare -F rth_verify_ed25519 >/dev/null 2>&1; then
      rth_verify_ed25519 "$d/SHA256SUMS" "$d/SHA256SUMS.sig" "${RATHOLE_SIGNING_PUBKEY:-}" "${RATHOLE_REQUIRE_SIG:-0}" || {
        err "emza-ye Ed25519 core-e backhaul motabar nist ($d) — rad shod."; continue; }
    elif [ -s "$d/SHA256SUMS.sig" ] || [ "${RATHOLE_REQUIRE_SIG:-0}" = 1 ]; then
      local _bh_sig="$d/SHA256SUMS.sig" _bh_pub="${RATHOLE_SIGNING_PUBKEY:-}" _bh_req="${RATHOLE_REQUIRE_SIG:-0}" _bh_raw _bh_ok=0 _bh_c _bh_sz=0
      if [ -z "$_bh_pub" ]; then
        for _bh_c in /usr/local/share/rathole/keys/release-ed25519.pub "${BASH_SOURCE[0]%/*}/keys/release-ed25519.pub" "$d/../keys/release-ed25519.pub"; do
          [ -n "$_bh_c" ] && [ -s "$_bh_c" ] && { _bh_pub="$_bh_c"; break; }
        done
      fi
      if [ ! -s "$_bh_sig" ]; then
        [ "$_bh_req" = 1 ] && { err "emza-ye SHA256SUMS.sig peyda nashod ($d) — rad shod."; continue; }
      elif [ -z "$_bh_pub" ] || [ ! -s "$_bh_pub" ]; then
        [ "$_bh_req" = 1 ] && { err "kelid-e Ed25519 peyda nashod baraye core-e backhaul ($d) — rad shod."; continue; }
        warn "SHA256SUMS.sig vojood darad vali kelid-e omumi nasb nist ($d) — rad shod."
      elif ! command -v openssl >/dev/null 2>&1; then
        err "openssl baraye tayid-e Ed25519 lazem ast ($d) — rad shod."; continue
      else
        _bh_raw="$(mktemp)"
        if tr -d ' \t\r\n' < "$_bh_sig" | base64 -d > "$_bh_raw" 2>/dev/null; then
          _bh_sz="$(wc -c < "$_bh_raw" | tr -d '[:space:]')"
          [ "$_bh_sz" = "64" ] && _bh_ok=1
        fi
        if [ "$_bh_ok" -eq 0 ]; then
          _bh_sz="$(wc -c < "$_bh_sig" | tr -d '[:space:]')"
          [ "$_bh_sz" = "64" ] && cp "$_bh_sig" "$_bh_raw" 2>/dev/null && _bh_ok=1
        fi
        if [ "$_bh_ok" -ne 1 ] || ! openssl pkeyutl -verify -pubin -inkey "$_bh_pub" -rawin -sigfile "$_bh_raw" -in "$d/SHA256SUMS" >/dev/null 2>&1; then
          rm -f "$_bh_raw"
          err "emza-ye Ed25519 core-e backhaul motabar nist ($d) — rad shod."
          continue
        fi
        rm -f "$_bh_raw"
      fi
    fi
    ( cd "$d" && sha256sum -c SHA256SUMS --ignore-missing --quiet ) 2>/dev/null || {
      err "checksum-e core-e backhaul motabar nist ($d) — rad shod."; continue; }
    want="$(sha256sum "$d/$target/backhaul" 2>/dev/null | cut -d' ' -f1)"
    have=""; [ -f "$bin" ] && have="$(sha256sum "$bin" 2>/dev/null | cut -d' ' -f1)"
    [ -n "$want" ] && [ "$want" = "$have" ] && return 0   # az ghabl haman core ast
    install -m755 "$d/$target/backhaul" "$bin" || continue
    log "backhaul-$role az core-e patch-shode nasb/berooz shod (uTLS): $bin"
    return 0
  done
  return 1
}

install_backhaul(){
  local role="$1" bin="${RATHOLE_BIN_DIR:-/usr/local/bin}/backhaul-$1" ver="${BACKHAUL_VER:-v0.6.5}" arch tmp ok=0 m
  # MOHEM: core AVVAL check mishavad، na baad az `[ -x $bin ]`. vagarna har node-i ke az ghabl
  # binary-e ghadimi darad (yaani HAMEYE node-haye mojood) HARGEZ noskhe-ye uTLS ra nemigirad —
  # hatta baad az update — va bi-seda rooye asar-angosht-e Go mimanad.
  install_backhaul_core "$role" && return 0
  [ -x "$bin" ] && return 0
  case "$(uname -m)" in x86_64) arch=amd64 ;; aarch64) arch=arm64 ;; *) die "memari poshtibani nemishavad." ;; esac
  command -v curl >/dev/null 2>&1 || die "curl lazem ast."
  warn "core-e patch-shode peyda nashod؛ backhaul-e upstream download mishavad (bedoon-e uTLS)."
  log "download backhaul ${ver} ($role)..."
  tmp="$(mktemp -d)"
  for m in "" "https://ghproxy.net/" "https://gh-proxy.com/" "https://mirror.ghproxy.com/"; do
    if curl -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 20 --retry 1 "${m}https://github.com/Musixal/Backhaul/releases/download/${ver}/backhaul_linux_${arch}.tar.gz" -o "$tmp/bh.tgz" 2>/dev/null; then ok=1; break; fi
    warn "in mnba javab nadad, mnba-ye badi..."
  done
  [ "$ok" -eq 1 ] || { rm -rf "$tmp"; die "download backhaul az hame-ye mnaba shekast khord."; }
  tar -xzf "$tmp/bh.tgz" -C "$tmp" || { rm -rf "$tmp"; die "baz kardan arshiv backhaul shekast khord."; }
  local src; src="$(find "$tmp" -maxdepth 2 -type f -name 'backhaul*' ! -name '*.tar.gz' | head -n1)"
  [ -n "$src" ] || { rm -rf "$tmp"; die "binary-e backhaul dar arshiv peyda nashod."; }
  install -m755 "$src" "$bin" || { rm -rf "$tmp"; die "nasb binary backhaul shekast khord."; }
  rm -rf "$tmp"
  log "backhaul-$role nasb shod: $bin"
}

# tanzimat sysctl (BBR + file limits + conntrack)
apply_sysctl_tuning(){
  modprobe nf_conntrack 2>/dev/null || true
  local sysctl_file="${RTH_SYSCTL_FILE:-/etc/sysctl.d/99-rathole-tune.conf}"
  mkdir -p "$(dirname "$sysctl_file")" 2>/dev/null || true
  cat >"$sysctl_file" <<'TUNE'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.ipv4.tcp_mtu_probing=1
net.ipv4.tcp_slow_start_after_idle=0
net.ipv4.tcp_fastopen=3
fs.file-max=2097152
net.core.somaxconn=65535
net.core.netdev_max_backlog=16384
net.ipv4.tcp_max_syn_backlog=65535
net.ipv4.ip_local_port_range=32768 60999
net.netfilter.nf_conntrack_max=1048576
net.core.rmem_max=26214400
net.core.wmem_max=26214400
net.core.rmem_default=26214400
net.core.wmem_default=26214400
TUNE
  sysctl --system >/dev/null 2>&1 || true
  if [ $# -gt 0 ]; then
    apply_reserved_ports "$@"
  fi
  log "BBR=$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null)  conntrack_max=$(sysctl -n net.netfilter.nf_conntrack_max 2>/dev/null || echo n/a)"
}

# rezerv port-haye tunnel/service dar kernel ta ettesalat khuruji eshgaleshan nakonand
apply_reserved_ports(){
  local res_file="${RTH_RESERVED_SYSCTL_FILE:-/etc/sysctl.d/99-rathole-reserved-ports.conf}"
  local tok csv=""
  local -a raw=()
  for tok in "$@"; do
    raw+=("$tok")
  done
  if [ "${#raw[@]}" -gt 0 ]; then
    csv="$(printf '%s\n' "${raw[@]}" | tr ', \t' '\n' | grep -E '^[0-9]{1,5}$' | awk '$1 >= 1 && $1 <= 65535 {print $1+0}' | sort -nu | paste -sd, -)"
  fi
  if [ -z "$csv" ]; then
    rm -f "$res_file" 2>/dev/null || true
    return 0
  fi
  mkdir -p "$(dirname "$res_file")" 2>/dev/null || true
  printf 'net.ipv4.ip_local_reserved_ports=%s\n' "$csv" > "$res_file"
  sysctl -w "net.ipv4.ip_local_reserved_ports=${csv}" >/dev/null 2>&1 || true
}

rth_valid_port(){
  [[ "${1:-}" =~ ^[0-9]{1,5}$ ]] && (( 10#$1 >= 1 && 10#$1 <= 65535 ))
}
rth_valid_path(){
  [[ "${1:-}" =~ ^/[A-Za-z0-9_./-]{1,255}$ ]] && [[ "$1" != *..* ]]
}
rth_valid_hostport(){
  [[ "${1:-}" =~ ^[A-Za-z0-9_.-]+:([0-9]{1,5})$ ]] && rth_valid_port "${BASH_REMATCH[1]}"
}
rth_valid_kcp_key(){
  [[ "${1:-}" =~ ^[A-Za-z0-9._=+/-]{1,256}$ ]]
}
rth_valid_noise_pattern(){
  [[ "${1:-}" =~ ^[A-Za-z0-9_]{1,80}$ ]]
}
rth_is_ipv4(){
  local ip="${1:-}" a b c d
  [[ "$ip" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
  a="${BASH_REMATCH[1]}"; b="${BASH_REMATCH[2]}"; c="${BASH_REMATCH[3]}"; d="${BASH_REMATCH[4]}"
  (( 10#$a <= 255 && 10#$b <= 255 && 10#$c <= 255 && 10#$d <= 255 ))
}
rth_is_ipv6(){
  local ip="${1:-}"
  [[ "$ip" == *:*:* ]] && [[ "$ip" =~ ^[0-9A-Fa-f:]+$ ]] && [[ "$ip" != *:::* ]]
}
rth_valid_ip(){
  rth_is_ipv4 "${1:-}" || rth_is_ipv6 "${1:-}"
}
rth_valid_gre_key(){
  [[ "${1:-}" =~ ^[0-9]{1,10}$ ]] && (( 10#$1 >= 0 && 10#$1 <= 4294967295 ))
}
rth_valid_mtu(){
  [[ "${1:-}" =~ ^[0-9]{3,4}$ ]] && (( 10#$1 >= 576 && 10#$1 <= 1500 ))
}
rth_valid_mac(){
  [[ "${1:-}" =~ ^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$ ]]
}
rth_valid_paqet_mode(){
  case "${1:-}" in normal|fast|fast2|fast3) return 0 ;; *) return 1 ;; esac
}
rth_valid_paqet_block(){
  case "${1:-}" in aes|aes-128|aes-128-gcm|salsa20|xor|sm4|none) return 0 ;; *) return 1 ;; esac
}
rth_valid_uuid(){
  [[ "${1:-}" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$ ]]
}

# service systemd fakeweb (server-e Nginx-namayesh-e deterministic ba python3 stdlib)
fakeweb_service(){
  local svc="$1" port="${2:-8081}" action="${3:-start}" seed_file="${4:-}"
  rth_valid_port "$port" || die "port namotabar."
  command -v python3 >/dev/null 2>&1 || die "python3 nasb nist (apt install -y python3)."
  mkdir -p /var/www/rathole-fake
  local fw_py="" cand
  for cand in /usr/local/share/rathole/fakeweb.py "${BASH_SOURCE[0]%/*}/fakeweb.py"; do
    if [ -f "$cand" ]; then fw_py="$cand"; break; fi
  done
  local exec_line="/usr/bin/python3 -m http.server ${port} --bind 127.0.0.1 --directory /var/www/rathole-fake"
  if [ -n "$fw_py" ]; then
    exec_line="/usr/bin/python3 ${fw_py} --host 127.0.0.1 --port ${port} --root /var/www/rathole-fake"
    [ -n "$seed_file" ] && exec_line="${exec_line} --seed-file ${seed_file}"
  else
    [ -f /var/www/rathole-fake/index.html ] || cat > /var/www/rathole-fake/index.html <<'HTML'
<!doctype html><html><head><meta charset="utf-8"><title>Welcome</title></head>
<body style="font-family:sans-serif"><h1>It works!</h1><p>Default web page.</p></body></html>
HTML
  fi
  case "$action" in
    start)
      cat > "/etc/systemd/system/${svc}.service" <<UNIT
[Unit]
Description=rathole fake web ($svc)
After=network.target
[Service]
ExecStart=${exec_line}
Restart=always
RestartSec=2
[Install]
WantedBy=multi-user.target
UNIT
      systemctl daemon-reload
      systemctl enable --now "$svc" >/dev/null 2>&1
      log "web fik ($svc) rooye 127.0.0.1:${port} bala amad." ;;
    stop)   systemctl stop "$svc" 2>/dev/null && log "motevaghef shod." || warn "ejra naboodan." ;;
    rm)     systemctl disable --now "$svc" 2>/dev/null || true; rm -f "/etc/systemd/system/${svc}.service"; systemctl daemon-reload; log "hazf shod." ;;
    status) systemctl --no-pager status "$svc" | sed -n '1,8p' || true ;;
  esac
}
# ---------------------------------------------------------------------------
# jam-avari-ye log baraye eshkal-zodai (`ratholectl logs` / `ratholenode logs`)
# ---------------------------------------------------------------------------
# HOSHDAR-E AMNIATI: khorooji-ye in tavabe maamoolan dar chat/issue paste mishavad.
# har chizi ke token/kelid/ramz ast BAYAD az inja rad shavad. rth_redact tanha
# darvaze-ye khorooj ast — har file-e jadidi ke ezafe mikoni HATMAN az an rad kon.
rth_redact(){
  sed -E \
    -e 's/("(token|api_token|bh_token|backhaul_token|frp_token|paqet_key|admin_password_sha256|password|secret|key|private_key|local_private_key|remote_public_key|noise_private_key|noise_privkey|privateKey)"[[:space:]]*:[[:space:]]*")[^"]*"/\1***REDACTED***"/g' \
    -e 's/^([[:space:]]*(auth\.token|token|default_token|password|secret|private_key|local_private_key|remote_public_key)[[:space:]]*=[[:space:]]*")[^"]*"/\1***REDACTED***"/' \
    -e 's/^([[:space:]]*key:[[:space:]]*").*"/\1***REDACTED***"/' \
    -e 's/^([[:space:]]*(TOKEN|BH_TOKEN|FRP_TOKEN|PAQET_KEY|paqet_key|NOISE_KEY|PASSWORD|API_TOKEN|XRAY_PRIVATE_KEY|XRAY_UUID)=).*/\1***REDACTED***/' \
    -e 's#(vless://)[0-9A-Fa-f-]{8,64}@#\1***REDACTED***@#g' \
    -e 's/(-key[[:space:]]+)[^[:space:]]+/\1***REDACTED***/g' \
    -e 's/^([^|[:space:]]+\|)[^|]*/\1***REDACTED***/' \
    -e 's#(/_rh/)[A-Fa-f0-9]{8,}#\1***REDACTED***#g' \
    -e 's/([?&](token|password|secret)=)[^&"[:space:]]*/\1***REDACTED***/g'
}

# yek bakhsh-e onvan-dar dar khorooji-ye log
rth_sec(){ printf '\n===== %s =====\n' "$*"; }

# log-e yek unit-e systemd (agar vojood dashte bashad)
rth_unit_log(){ # $1=unit  $2=tedad khat
  local u="$1" n="${2:-80}"
  systemctl list-unit-files "$u.service" >/dev/null 2>&1 || return 0
  [ -f "/etc/systemd/system/$u.service" ] || [ -f "/lib/systemd/system/$u.service" ] || return 0
  rth_sec "unit: $u  (halat: $(systemctl is-active "$u" 2>/dev/null || echo unknown)/$(systemctl is-enabled "$u" 2>/dev/null || echo n/a))"
  journalctl -u "$u" -n "$n" --no-pager 2>/dev/null | rth_redact || true
}

# mohtava-ye yek file-e config (redact-shode)
rth_file_dump(){ # $1=barchasb  $2=masir  [$3=hadaksar khat]
  local label="$1" p="$2" n="${3:-200}"
  [ -f "$p" ] || { rth_sec "$label ($p) — NIST"; return 0; }
  rth_sec "$label ($p)"
  head -n "$n" "$p" 2>/dev/null | rth_redact || true
}

# ---------------------------------------------------------------------------
# FRP Core Integration (fatedier/frp)
# ---------------------------------------------------------------------------
install_frp(){
  local role="$1"
  local bin="${RATHOLE_BIN_DIR:-/usr/local/bin}/frp${role:0:1}" ver="${FRP_VER:-0.61.1}" arch tmp ok=0 m
  # role: server -> frps, client -> frpc
  [ -x "$bin" ] && return 0
  case "$(uname -m)" in x86_64) arch=amd64 ;; aarch64) arch=arm64 ;; *) die "memari poshtibani nemishavad." ;; esac
  command -v curl >/dev/null 2>&1 || die "curl lazem ast."
  log "download FRP ${ver} ($role)..."
  tmp="$(mktemp -d)"
  local fname="frp_${ver}_linux_${arch}.tar.gz"
  for m in "" "https://ghproxy.net/" "https://gh-proxy.com/" "https://mirror.ghproxy.com/"; do
    if curl -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 20 --retry 1 "${m}https://github.com/fatedier/frp/releases/download/v${ver}/${fname}" -o "$tmp/frp.tgz" 2>/dev/null; then ok=1; break; fi
    warn "in mnba javab nadad, mnba-ye badi..."
  done
  [ "$ok" -eq 1 ] || { rm -rf "$tmp"; die "download frp az hame-ye mnaba shekast khord."; }
  tar -xzf "$tmp/frp.tgz" -C "$tmp" || { rm -rf "$tmp"; die "baz kardan arshiv frp shekast khord."; }
  local target_bin="frp${role:0:1}" # frps or frpc
  local src; src="$(find "$tmp" -maxdepth 2 -type f -name "$target_bin" | head -n1)"
  [ -n "$src" ] || { rm -rf "$tmp"; die "binary-e $target_bin dar arshiv peyda nashod."; }
  install -m755 "$src" "$bin" || { rm -rf "$tmp"; die "nasb binary frp shekast khord."; }
  rm -rf "$tmp"
  log "frp $role nasb shod: $bin"
}

frp_systemd_unit(){
  local role="$1" # server or client
  local sname="frp${role:0:1}"
  local cfg="/etc/frp/${sname}.toml"
  mkdir -p /etc/frp
  cat >"/etc/systemd/system/${sname}.service" <<EOF
[Unit]
Description=FRP ${role} Service
After=network.target

[Service]
Type=simple
User=root
Restart=on-failure
RestartSec=5s
ExecStart=/usr/local/bin/${sname} -c ${cfg}
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# GRE L3 Linux Tunnel Integration (IPv4 gre + IPv6 ip6gre, key, MSS clamp, Auto-MTU)
# ---------------------------------------------------------------------------
_rth_sweep_ipt_comment(){ # $1=ipt_bin $2=table $3=chain $4=comment_tag
  local ipt="$1" tbl="$2" chain="$3" tag="$4"
  command -v "$ipt" >/dev/null 2>&1 || return 0
  local line
  "$ipt" -t "$tbl" -S "$chain" 2>/dev/null | while IFS= read -r line; do
    line="${line%$'\r'}"
    case "$line" in
      -A\ *)
        local -a toks=()
        read -ra toks <<< "${line#-A }"
        [ "${#toks[@]}" -gt 0 ] || continue
        local i matched=0
        for i in "${!toks[@]}"; do
          toks[$i]="${toks[$i]//\"/}"
          if [ "$i" -gt 0 ] && [ "${toks[$((i-1))]}" = "--comment" ] && [ "${toks[$i]}" = "$tag" ]; then
            matched=1
          fi
        done
        [ "$matched" -eq 1 ] || continue
        "$ipt" -t "$tbl" -D "${toks[@]}" >/dev/null 2>&1 || true
        ;;
    esac
  done
}

gre_teardown_interface(){
  local name="${1:-gre1}" quiet="${2:-0}"
  local tag="rathole-gre-${name}"
  ip link set "$name" down 2>/dev/null || true
  ip link del "$name" 2>/dev/null || ip tunnel del "$name" 2>/dev/null || true
  local ipt
  for ipt in iptables ip6tables; do
    _rth_sweep_ipt_comment "$ipt" filter INPUT "$tag"
    _rth_sweep_ipt_comment "$ipt" mangle OUTPUT "$tag"
    _rth_sweep_ipt_comment "$ipt" mangle FORWARD "$tag"
    _rth_sweep_ipt_comment "$ipt" mangle POSTROUTING "$tag"
    "$ipt" -t mangle -D POSTROUTING -p tcp --tcp-flags SYN,RST SYN -o "$name" -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || true
  done
  [ "$quiet" = "1" ] || log "GRE tunnel '$name' pak shod."
}

gre_setup_interface(){
  local name="${1:-gre1}" local_ip="$2" remote_ip="$3" tunnel_ip="$4" gre_key="${5:-0}" req_mtu="${6:-0}"
  rth_valid_ip "$remote_ip" || { err "remote_ip namotabar ast: $remote_ip"; return 1; }
  rth_valid_gre_key "$gre_key" || { err "gre_key namotabar ast (0..4294967295): $gre_key"; return 1; }
  [ "${req_mtu:-0}" = "0" ] || rth_valid_mtu "$req_mtu" || { err "mtu namotabar ast (576..1500): $req_mtu"; return 1; }
  gre_key=$((10#$gre_key))
  req_mtu=$((10#${req_mtu:-0}))

  local is_v6=0 mod="ip_gre" gtype="gre" ipt="iptables" overhead=24
  if rth_is_ipv6 "$remote_ip"; then
    is_v6=1; mod="ip6_gre"; gtype="ip6gre"; ipt="ip6tables"
    [ "$gre_key" -gt 0 ] && overhead=48 || overhead=44
  else
    [ "$gre_key" -gt 0 ] && overhead=28 || overhead=24
  fi
  modprobe "$mod" 2>/dev/null || true
  gre_teardown_interface "$name" 1

  local route_out out_dev="" dev_ip="" base_mtu=""
  if [ "$is_v6" -eq 1 ]; then
    route_out="$(ip -6 route get "$remote_ip" 2>/dev/null | head -n1 || true)"
  else
    route_out="$(ip -4 route get "$remote_ip" 2>/dev/null | head -n1 || ip route get "$remote_ip" 2>/dev/null | head -n1 || true)"
  fi
  out_dev="$(printf '%s\n' "$route_out" | sed -n 's/.* dev \([^ ]*\).*/\1/p')"
  dev_ip="$(printf '%s\n' "$route_out" | sed -n 's/.* src \([^ ]*\).*/\1/p')"
  if [ -n "$dev_ip" ]; then
    if [ "$is_v6" -eq 1 ] && rth_is_ipv6 "$dev_ip"; then
      local_ip="$dev_ip"
    elif [ "$is_v6" -eq 0 ] && rth_is_ipv4 "$dev_ip"; then
      local_ip="$dev_ip"
    fi
  fi
  if [ -n "$out_dev" ]; then
    base_mtu="$(ip link show dev "$out_dev" 2>/dev/null | sed -n 's/.* mtu \([0-9]*\).*/\1/p' | head -n1)"
  fi
  [[ "$base_mtu" =~ ^[0-9]+$ ]] || base_mtu=1500

  local mtu="$req_mtu"
  if [ "${mtu:-0}" -le 0 ] 2>/dev/null; then
    mtu=$((base_mtu - overhead))
    [ "$mtu" -lt 576 ] && mtu=576
  fi

  local has_local=0
  if [ -n "$local_ip" ]; then
    if [ "$is_v6" -eq 1 ]; then
      ip -6 addr show 2>/dev/null | grep -q "inet6 ${local_ip}/" && has_local=1
    else
      ip -4 addr show 2>/dev/null | grep -q "inet ${local_ip}/" && has_local=1
    fi
  fi

  local -a add_cmd=(ip link add "$name" type "$gtype" remote "$remote_ip")
  local -a add_cmd_nolocal=(ip link add "$name" type "$gtype" remote "$remote_ip")
  if [ "$has_local" -eq 1 ]; then
    add_cmd+=(local "$local_ip")
  fi
  if [ "$is_v6" -eq 1 ]; then
    add_cmd+=(encaplimit none hoplimit 255)
    add_cmd_nolocal+=(encaplimit none hoplimit 255)
  else
    add_cmd+=(ttl 255)
    add_cmd_nolocal+=(ttl 255)
  fi
  if (( 10#$gre_key > 0 )); then
    add_cmd+=(key "$gre_key")
    add_cmd_nolocal+=(key "$gre_key")
  fi

  if ! "${add_cmd[@]}" 2>/dev/null; then
    if ! "${add_cmd_nolocal[@]}" 2>/dev/null; then
      if [ "$is_v6" -eq 0 ]; then
        local -a tun_cmd=(ip tunnel add "$name" mode gre remote "$remote_ip" ttl 255)
        [ "$has_local" -eq 1 ] && tun_cmd+=(local "$local_ip")
        (( 10#$gre_key > 0 )) && tun_cmd+=(key "$gre_key")
        "${tun_cmd[@]}" || return 1
      else
        return 1
      fi
    fi
  fi

  local tun_cidr="$tunnel_ip" inner_ip="${tunnel_ip%%/*}"
  if [[ "$tun_cidr" != */* ]]; then
    if rth_is_ipv6 "$inner_ip"; then tun_cidr="${inner_ip}/126"; else tun_cidr="${inner_ip}/30"; fi
  fi
  ip addr add "$tun_cidr" dev "$name" || return 1
  ip link set "$name" mtu "$mtu" up || return 1

  local tag="rathole-gre-${name}"
  if command -v "$ipt" >/dev/null 2>&1; then
    "$ipt" -C INPUT -p 47 -s "$remote_ip" -m comment --comment "$tag" -j ACCEPT 2>/dev/null || \
      "$ipt" -I INPUT 1 -p 47 -s "$remote_ip" -m comment --comment "$tag" -j ACCEPT 2>/dev/null || true
  fi
  local inner_ipt="iptables"
  rth_is_ipv6 "$inner_ip" && inner_ipt="ip6tables"
  if command -v "$inner_ipt" >/dev/null 2>&1; then
    local ch
    for ch in OUTPUT FORWARD; do
      "$inner_ipt" -t mangle -C "$ch" -p tcp --tcp-flags SYN,RST SYN -o "$name" -m comment --comment "$tag" -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || \
        "$inner_ipt" -t mangle -I "$ch" 1 -p tcp --tcp-flags SYN,RST SYN -o "$name" -m comment --comment "$tag" -j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || true
    done
  fi
  sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
  [ "$is_v6" -eq 1 ] && sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null 2>&1 || true
  local key_msg=""
  [ "$gre_key" -gt 0 ] && key_msg=", key: $gre_key"
  log "GRE tunnel '$name' ($gtype) faal shod: $tun_cidr (remote: $remote_ip, mtu: $mtu${key_msg})"
}

gre_probe_mtu(){ # $1=iface $2=peer_tunnel_ip
  local iface="${1:-gre1}" peer="${2:-}"
  ip link show "$iface" >/dev/null 2>&1 || { err "GRE interface '$iface' peyda nashod."; return 1; }
  rth_valid_ip "$peer" || { err "peer_tunnel_ip namotabar ast: $peer"; return 1; }
  local cur_mtu; cur_mtu="$(ip link show dev "$iface" 2>/dev/null | sed -n 's/.* mtu \([0-9]*\).*/\1/p' | head -n1)"
  [[ "$cur_mtu" =~ ^[0-9]+$ ]] || cur_mtu=1476
  local hdr=28
  local -a pbase=(ping -I "$iface" -M do -c 1 -W 1)
  if rth_is_ipv6 "$peer"; then
    hdr=48
    pbase=(ping -6 -I "$iface" -M do -c 1 -W 1)
  fi
  local min_mtu=1280
  [ "$cur_mtu" -lt "$min_mtu" ] && min_mtu="$cur_mtu"
  local min_pay=$((min_mtu - hdr))
  if ! "${pbase[@]}" -s "$min_pay" "$peer" >/dev/null 2>&1; then
    warn "ping ba MTU=$min_mtu rooye '$iface' be $peer pasokh nadad; MTU taghir nakard."
    return 1
  fi
  local cur_pay=$((cur_mtu - hdr))
  if "${pbase[@]}" -s "$cur_pay" "$peer" >/dev/null 2>&1; then
    log "MTU fali ($cur_mtu) rooye '$iface' salem ast."
    return 0
  fi
  local lo="$min_mtu" hi="$((cur_mtu - 1))" best="$min_mtu" mid pay
  while [ "$lo" -le "$hi" ]; do
    mid=$(( (lo + hi) / 2 ))
    pay=$((mid - hdr))
    if "${pbase[@]}" -s "$pay" "$peer" >/dev/null 2>&1; then
      best="$mid"
      lo=$((mid + 1))
    else
      hi=$((mid - 1))
    fi
  done
  ip link set "$iface" mtu "$best" || return 1
  log "path MTU=$best rooye '$iface' (az $cur_mtu kahesh yaft)."
}

detect_ip(){
  if [ -n "${RATHOLE_PUBLIC_IP:-}" ]; then printf '%s' "$RATHOLE_PUBLIC_IP"; return; fi
  local ip=""
  if command -v curl >/dev/null 2>&1; then
    ip="$(curl -fsS4 --connect-timeout 2 --max-time 3 https://api.ipify.org 2>/dev/null)"
  fi
  [ -n "$ip" ] || ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  printf '%s' "$ip"
}

# ---------------------------------------------------------------------------
# Certificate expiry, kernel health & argv-safe offsite backup hooks
# ---------------------------------------------------------------------------
rth_cert_days_left(){ # $1=cert_pem -> chap adad rooz (manfi agar monghazi)
  local pem="${1:-}" end_line
  [ -f "$pem" ] && command -v openssl >/dev/null 2>&1 || return 1
  end_line="$(openssl x509 -enddate -noout -in "$pem" 2>/dev/null | sed 's/^notAfter=//')"
  [ -n "$end_line" ] || return 1
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$end_line" <<'PY' 2>/dev/null
import email.utils, datetime, sys
dt = email.utils.parsedate_to_datetime(sys.argv[1].strip())
if dt.tzinfo is None:
    dt = dt.replace(tzinfo=datetime.timezone.utc)
now = datetime.datetime.now(datetime.timezone.utc)
print((dt - now).days)
PY
    return $?
  fi
  local exp_epoch now_epoch
  exp_epoch="$(date -d "$end_line" +%s 2>/dev/null)" || return 1
  now_epoch="$(date +%s)"
  echo $(( (exp_epoch - now_epoch) / 86400 ))
}

rth_check_kernel_health(){ # $1=panel|node
  local role="${1:-panel}" tune_cmd="ratholectl tune"
  [ "$role" = "node" ] && tune_cmd="ratholenode tune"
  echo "$(c_g '== barresi kernel / TCP / Path MTU ==')"
  local pr_start=""
  if [ -r "${RTH_PROC_PORT_RANGE:-/proc/sys/net/ipv4/ip_local_port_range}" ]; then
    pr_start="$(awk '{print $1}' "${RTH_PROC_PORT_RANGE:-/proc/sys/net/ipv4/ip_local_port_range}" 2>/dev/null || true)"
  else
    pr_start="$(sysctl -n net.ipv4.ip_local_port_range 2>/dev/null | awk '{print $1}' || true)"
  fi
  if [[ "$pr_start" =~ ^[0-9]+$ ]]; then
    if [ "$pr_start" -lt 10000 ]; then
      printf '  %s ip_local_port_range az %s shoroo mishavad (khatar-e tadakhol ba port-haye service)\n' "$(c_y 'WARN')" "$pr_start"
      printf '       %s %s\n' "$(c_y '→ rah-e hal:')" "$tune_cmd"
    else
      printf '  %s ip_local_port_range amn ast (start=%s)\n' "$(c_g 'OK ')" "$pr_start"
    fi
  fi
  local cc=""
  if [ -r "${RTH_PROC_CC:-/proc/sys/net/ipv4/tcp_congestion_control}" ]; then
    cc="$(tr -d '[:space:]' < "${RTH_PROC_CC:-/proc/sys/net/ipv4/tcp_congestion_control}" 2>/dev/null || true)"
  else
    cc="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"
  fi
  if [ -n "$cc" ]; then
    if [ "$cc" = "bbr" ]; then
      printf '  %s congestion control = bbr\n' "$(c_g 'OK ')"
    else
      printf '  %s congestion control = %s (pishnahad: bbr)\n' "$(c_y 'WARN')" "$cc"
      printf '       %s %s\n' "$(c_y '→ rah-e hal:')" "$tune_cmd"
    fi
  fi
  if command -v ss >/dev/null 2>&1; then
    local low_mss
    low_mss="$(ss -tinH 2>/dev/null | grep -oE 'mss:[0-9]+' | cut -d: -f2 | awk '$1 > 0 && $1 < 1300 {print $1}' | sort -n | head -n1 || true)"
    if [ -n "$low_mss" ]; then
      printf '  %s socket-e faal ba snd_mss=%s moshahede shod (Path MTU koochak?)\n' "$(c_y 'WARN')" "$low_mss"
      printf '       %s masir MTU ra ba "gre auto-mtu" ya KCP MTU barresi kon.\n' "$(c_y '→ rah-e hal:')"
    fi
  fi
}

rth_offsite_hook_set(){ # $1=cfg_json $2...=argv (hatman {} dashte bashad; bedoon shell)
  local cfg="$1"; shift || true
  command -v python3 >/dev/null 2>&1 || die "baraye hook-e offsite python3 lazem ast."
  [ $# -ge 1 ] || die "estefade: backup offsite set <cmd> [args... {} ...]"
  local bin="$1"
  [ -n "$bin" ] || die "dastoor khali ast."
  [[ ! "$bin" =~ [[:space:]\;\&\|\$\`\<\>] ]] || die "nam-e binary namotabar ast (faghat argv-e mostaghim bedoon shell)."
  local has_ph=0 arg
  for arg in "$@"; do
    case "$arg" in *"{}"*) has_ph=1 ;; esac
  done
  [ "$has_ph" -eq 1 ] || die "dastoor bayad shamel placeholder-e '{}' baraye masir-e file backup bashad."
  mkdir -p "$(dirname "$cfg")" 2>/dev/null || true
  chmod 700 "$(dirname "$cfg")" 2>/dev/null || true
  local tmp="${cfg}.tmp.$$"
  python3 - "$tmp" "$@" <<'PY' || { rm -f "$tmp"; die "neveshtan hook-e offsite shekast khord."; }
import json, sys
out = sys.argv[1]
with open(out, "w", encoding="utf-8", newline="\n") as f:
    json.dump({"argv": sys.argv[2:]}, f)
    f.write("\n")
PY
  rth_commit_config "$tmp" "$cfg"
  chmod 600 "$cfg" 2>/dev/null || true
  log "offsite backup hook zakhire shod ($cfg)."
}

rth_offsite_hook_show(){ # $1=cfg_json
  local cfg="$1"
  if [ ! -f "$cfg" ]; then
    echo "offsite backup: $(c_y 'khamoosh')"
    return 0
  fi
  command -v python3 >/dev/null 2>&1 || { echo "offsite backup: faal ($cfg)"; return 0; }
  python3 - "$cfg" <<'PY'
import json, shlex, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        argv = json.load(f).get("argv", [])
    print("offsite backup: roshan ->", " ".join(shlex.quote(a) for a in argv))
except Exception as e:
    print("offsite backup: khata dar khandan config:", e)
PY
}

rth_offsite_hook_off(){ # $1=cfg_json
  local cfg="$1"
  if [ -f "$cfg" ]; then
    rm -f "$cfg"
    log "offsite backup hook hazf shod."
  else
    warn "offsite backup az ghabl khamoosh bood."
  fi
}

rth_offsite_hook_run(){ # $1=cfg_json $2=backup_file
  local cfg="$1" bfile="$2"
  [ -f "$cfg" ] || return 2
  [ -f "$bfile" ] || { err "file backup baraye ersal peyda nashod: $bfile"; return 1; }
  command -v python3 >/dev/null 2>&1 || { err "python3 baraye ejra-ye offsite hook nist."; return 1; }
  python3 - "$cfg" "$bfile" <<'PY'
import json, subprocess, sys
cfg_path, bfile = sys.argv[1], sys.argv[2]
with open(cfg_path, encoding="utf-8") as f:
    data = json.load(f)
argv = data.get("argv")
if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x != "" for x in argv):
    print("[!] hook-e offsite namotabar ast.", file=sys.stderr)
    sys.exit(1)
expanded = [a.replace("{}", bfile) for a in argv]
try:
    p = subprocess.run(expanded, shell=False, timeout=300)
    sys.exit(p.returncode)
except FileNotFoundError:
    print(f"[!] binary peyda nashod: {expanded[0]}", file=sys.stderr)
    sys.exit(127)
except subprocess.TimeoutExpired:
    print("[!] ersal offsite timeout shod (300s).", file=sys.stderr)
    sys.exit(124)
PY
}

# ---------------------------------------------------------------------------
# Link Test / Bidirectional Probe Helpers (M2)
# ---------------------------------------------------------------------------
rth_gre_peer_ip(){ # $1=local_tunnel_ip (masalan 10.10.10.1 ya fd00::1/126) -> peer host IP
  local tip="${1:-}"
  [ -n "$tip" ] || return 0
  command -v python3 >/dev/null 2>&1 || return 0
  python3 - "$tip" <<'PY' 2>/dev/null || true
import ipaddress, sys
raw = sys.argv[1].strip()
if not raw:
    sys.exit(0)
if "/" in raw:
    iface = ipaddress.ip_interface(raw)
else:
    addr = ipaddress.ip_address(raw)
    iface = ipaddress.ip_interface("%s/%d" % (addr, 30 if addr.version == 4 else 126))
hosts = list(iface.network.hosts())
cands = [h for h in hosts if h != iface.ip]
if not cands:
    cands = [a for a in iface.network if a != iface.ip]
if cands:
    print(str(cands[0]))
PY
}

rth_link_probe(){
  command -v python3 >/dev/null 2>&1 || { echo '{"ok":false,"verdict":"failed","detail":"python3 missing"}'; return 1; }
  python3 - "$@" <<'PY'
import argparse
import base64
import json
import math
import os
import re
import socket
import ssl
import subprocess
import sys
import time


def _stats(rtts):
    if not rtts:
        return None, None
    s = sorted(rtts)
    idx = min(len(s) - 1, max(0, int(math.ceil(0.95 * len(s))) - 1))
    rtt = {
        "min": round(s[0], 2),
        "avg": round(sum(s) / len(s), 2),
        "max": round(s[-1], 2),
        "p95": round(s[idx], 2),
    }
    if len(rtts) >= 2:
        jit = sum(abs(rtts[i] - rtts[i - 1]) for i in range(1, len(rtts))) / (len(rtts) - 1)
    else:
        jit = 0.0
    return rtt, round(jit, 2)


def _format_host_hdr(val):
    if ":" in val and not val.startswith("["):
        return "[%s]" % val
    return val


def _ws_request(path, host_hdr):
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    p = path if path.startswith("/") else "/" + path
    return (
        "GET %s HTTP/1.1\r\n"
        "Host: %s\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: %s\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n" % (p, host_hdr, key)
    ).encode("ascii")


def _parse_http_status(data):
    first = data.split(b"\r\n", 1)[0].split(b"\n", 1)[0].decode("ascii", errors="replace")
    parts = first.split(" ", 2)
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def _run_icmp(host, count, timeout):
    clean = host.strip("[]")
    cmd = ["ping"]
    if ":" in clean:
        cmd.append("-6")
    w_sec = max(1, int(round(timeout)))
    cmd.extend(["-c", str(count), "-W", str(w_sec), clean])
    try:
        proc = subprocess.run(
            cmd, shell=False, capture_output=True, text=True, timeout=max(5, count * w_sec + 4)
        )
    except FileNotFoundError:
        return [], "ping_missing"
    except subprocess.TimeoutExpired:
        return [], "ping_timeout"
    vals = [float(x) for x in re.findall(r"time=([0-9]+(?:\.[0-9]+)?)\s*ms", proc.stdout or "")]
    err = None if vals else ((proc.stderr or proc.stdout or "no_icmp_reply").strip().splitlines()[-1][:120] if (proc.stderr or proc.stdout or "").strip() else "no_icmp_reply")
    return vals, err


def _probe_backends(raw_json):
    out = []
    if not raw_json:
        return out
    try:
        items = json.loads(raw_json)
    except Exception:
        return out
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            port = int(it.get("port"))
        except Exception:
            continue
        name = str(it.get("name", ""))
        lane = str(it.get("lane", "rathole"))
        t0 = time.monotonic()
        up = False
        rtt = None
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.5):
                rtt = round((time.monotonic() - t0) * 1000.0, 2)
                up = True
        except OSError:
            up = False
        out.append({"name": name, "lane": lane, "port": port, "up": up, "rtt_ms": rtt})
    return out


def _probe_gre(iface, peer, count):
    if not iface or not peer:
        return None
    g_cnt = max(1, min(int(count), 4))
    clean = peer.strip("[]")
    cmd = ["ping"]
    if ":" in clean:
        cmd.append("-6")
    cmd.extend(["-I", iface, "-c", str(g_cnt), "-W", "2", clean])
    try:
        proc = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=max(6, g_cnt * 2 + 4))
        vals = [float(x) for x in re.findall(r"time=([0-9]+(?:\.[0-9]+)?)\s*ms", proc.stdout or "")]
    except Exception:
        vals = []
    rtt, jit = _stats(vals)
    loss = round(((g_cnt - len(vals)) / float(g_cnt)) * 100.0, 1)
    return {
        "iface": iface,
        "peer_ip": clean,
        "up": len(vals) > 0,
        "ok_count": len(vals),
        "samples": g_cnt,
        "loss_pct": loss,
        "rtt_ms": rtt,
        "jitter_ms": jit,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["http_ws", "tls_direct", "ws_tls", "ws_plain", "bh_tls", "tcp", "icmp"])
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--path", default="/")
    ap.add_argument("--sni", default="")
    ap.add_argument("--trusted-root", default="")
    ap.add_argument("--insecure-tls", action="store_true")
    ap.add_argument("--backends-json", default="")
    ap.add_argument("--gre-iface", default="")
    ap.add_argument("--gre-peer", default="")
    args = ap.parse_args()

    mode = args.mode
    host = args.host.strip("[]")
    port = int(args.port)
    count = max(1, min(20, int(args.count)))
    timeout = max(0.5, min(10.0, float(args.timeout)))
    sni = (args.sni or host).strip("[]")
    host_hdr = _format_host_hdr(sni)

    rtts = []
    listener_up = False
    open_no_http_count = 0
    http_status = None
    tls_version = None
    last_err = None

    if mode == "icmp":
        rtts, last_err = _run_icmp(host, count, timeout)
        listener_up = len(rtts) > 0
    else:
        for idx in range(count):
            t0 = time.monotonic()
            sock = None
            try:
                sock = socket.create_connection((host, port), timeout=timeout)
                sock.settimeout(timeout)
                listener_up = True

                if mode == "tcp":
                    rtts.append((time.monotonic() - t0) * 1000.0)
                elif mode == "tls_direct":
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    with ctx.wrap_socket(sock, server_hostname=sni) as ssock:
                        sock = None
                        tls_version = ssock.version()
                    rtts.append((time.monotonic() - t0) * 1000.0)
                elif mode in ("http_ws", "ws_plain", "ws_tls", "bh_tls"):
                    conn = sock
                    if mode in ("ws_tls", "bh_tls"):
                        if args.insecure_tls:
                            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        elif args.trusted_root:
                            ctx = ssl.create_default_context(cafile=args.trusted_root)
                        else:
                            ctx = ssl.create_default_context()
                        conn = ctx.wrap_socket(sock, server_hostname=sni)
                        sock = None
                        conn.settimeout(timeout)
                        tls_version = conn.version()
                    try:
                        conn.sendall(_ws_request(args.path, host_hdr))
                        data = conn.recv(2048)
                    finally:
                        try:
                            conn.close()
                        except OSError:
                            pass
                        sock = None
                    if not data:
                        last_err = "remote_closed"
                    elif data.startswith(b"HTTP/"):
                        code = _parse_http_status(data)
                        http_status = code
                        if mode in ("ws_tls", "ws_plain"):
                            if code == 101:
                                rtts.append((time.monotonic() - t0) * 1000.0)
                            else:
                                last_err = "http_%s" % (code if code is not None else "bad")
                        elif mode == "bh_tls":
                            if code in (101, 400, 401, 403, 426):
                                rtts.append((time.monotonic() - t0) * 1000.0)
                            else:
                                last_err = "http_%s" % (code if code is not None else "bad")
                        else:
                            if code in (502, 503, 504):
                                last_err = "http_%d" % code
                            else:
                                rtts.append((time.monotonic() - t0) * 1000.0)
                    else:
                        if mode in ("ws_tls", "ws_plain", "bh_tls"):
                            last_err = "non_http_reply"
                        else:
                            rtts.append((time.monotonic() - t0) * 1000.0)
            except ConnectionRefusedError:
                last_err = "refused"
            except ConnectionResetError:
                last_err = "remote_closed"
            except socket.timeout:
                if mode == "http_ws" and listener_up:
                    open_no_http_count += 1
                    last_err = "open_no_http"
                else:
                    last_err = "timeout"
            except ssl.SSLError as e:
                last_err = "tls_error:%s" % (getattr(e, "reason", None) or str(e))[:80]
            except OSError as e:
                last_err = "os_error:%s" % str(e)[:80]
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            if idx + 1 < count:
                time.sleep(0.05)

    ok_count = len(rtts)
    loss_pct = round(((count - ok_count) / float(count)) * 100.0, 1)
    rtt_ms, jitter_ms = _stats(rtts)
    detail = None
    if ok_count > 0:
        if loss_pct >= 10.0 or (jitter_ms or 0.0) >= 30.0 or rtt_ms["avg"] >= 250.0:
            verdict = "degraded"
        else:
            verdict = "healthy"
        ok = True
    elif mode == "http_ws" and open_no_http_count == count:
        verdict = "open_no_http"
        ok = True
        loss_pct = 0.0
        detail = "TCP tunnel open (non-HTTP backend did not reply to WS probe)"
    else:
        verdict = "failed"
        ok = False
        detail = last_err or "probe failed"

    payload = {
        "ok": ok,
        "verdict": verdict,
        "probe_mode": mode,
        "host": host,
        "port": port if mode != "icmp" else None,
        "count": count,
        "ok_count": ok_count,
        "loss_pct": loss_pct,
        "rtt_ms": rtt_ms,
        "jitter_ms": jitter_ms,
        "listener_up": listener_up,
        "http_status": http_status,
        "tls_version": tls_version,
        "detail": detail,
        "backends": _probe_backends(args.backends_json),
        "gre": _probe_gre(args.gre_iface, args.gre_peer, count) if (args.gre_iface and args.gre_peer) else None,
    }
    print(json.dumps(payload, separators=(",", ":")))


if __name__ == "__main__":
    main()
PY
}

# ---------------------------------------------------------------------------
# paqet (Direct PCK: raw TCP/KCP carrier — hanselime/paqet)
# ---------------------------------------------------------------------------
install_paqet(){
  local bin="${RATHOLE_BIN_DIR:-/usr/local/bin}/paqet" ver="${PAQET_VER:-v1.0.0-alpha.14}" arch tmp ok=0 m
  [ -x "$bin" ] && return 0
  case "$(uname -m)" in x86_64) arch=amd64 ;; aarch64) arch=arm64 ;; *) die "memari poshtibani nemishavad baraye paqet." ;; esac
  command -v curl >/dev/null 2>&1 || die "curl lazem ast."
  local ver_no_v="${ver#v}"
  local url="https://github.com/hanselime/paqet/releases/download/${ver}/paqet-linux-${arch}-${ver_no_v}.tar.gz"
  log "download paqet ${ver}..."
  tmp="$(mktemp -d)"
  if [ -n "${RATHOLE_UPDATE_PROXY:-}" ] && rth_valid_proxy_url "${RATHOLE_UPDATE_PROXY}"; then
    printf 'proxy = "%s"\n' "${RATHOLE_UPDATE_PROXY}" | \
      curl --config - -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 25 --retry 1 "$url" -o "$tmp/paqet.tgz" 2>/dev/null && ok=1
  else
    for m in "${RTH_MIRRORS[@]}"; do
      if curl -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 25 --retry 1 "${m}${url}" -o "$tmp/paqet.tgz" 2>/dev/null; then
        ok=1; break
      fi
      warn "in mnba javab nadad, mnba-ye badi..."
    done
  fi
  [ "$ok" -eq 1 ] || { rm -rf "$tmp"; die "download paqet az hame-ye mnaba shekast khord."; }
  tar -xzf "$tmp/paqet.tgz" -C "$tmp" || { rm -rf "$tmp"; die "baz kardan arshiv paqet shekast khord."; }
  local src
  src="$(find "$tmp" -maxdepth 3 -type f -name 'paqet*' ! -name '*.tar.gz' ! -name '*.yaml' | head -n1)"
  [ -n "$src" ] || { rm -rf "$tmp"; die "binary-e paqet dar arshiv peyda nashod."; }
  mkdir -p "$(dirname "$bin")"
  install -m755 "$src" "$bin" || { rm -rf "$tmp"; die "nasb binary paqet shekast khord."; }
  rm -rf "$tmp"
  log "paqet nasb shod: $bin"
}

paqet_detect_net(){
  command -v ip >/dev/null 2>&1 || { printf '||\n'; return 1; }
  local def iface gw lip mac
  def="$(ip -4 route show default 2>/dev/null | head -n1)"
  iface="$(printf '%s\n' "$def" | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
  gw="$(printf '%s\n' "$def" | awk '{for(i=1;i<=NF;i++) if($i=="via"){print $(i+1); exit}}')"
  lip="$(printf '%s\n' "$def" | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  if [ -z "$lip" ] && [ -n "$iface" ]; then
    lip="$(ip -4 -o addr show dev "$iface" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"
  fi
  if [ -n "$iface" ] && [ -n "$gw" ]; then
    mac="$(ip -4 neigh show "$gw" dev "$iface" 2>/dev/null | grep -oE '([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}' | head -n1 || true)"
    if [ -z "$mac" ]; then
      ping -c1 -W1 "$gw" >/dev/null 2>&1 || true
      mac="$(ip -4 neigh show "$gw" dev "$iface" 2>/dev/null | grep -oE '([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}' | head -n1 || true)"
    fi
  fi
  printf '%s|%s|%s\n' "${iface:-}" "${lip:-}" "${mac:-}"
}

paqet_iptables_remove(){ # $1=port $2=role(server|client)
  local port="$1" role="${2:-server}" tag
  tag="rathole-paqet-${role}-${port}"
  command -v iptables >/dev/null 2>&1 || return 0
  _rth_sweep_ipt_comment iptables raw PREROUTING "$tag"
  _rth_sweep_ipt_comment iptables raw OUTPUT "$tag"
  _rth_sweep_ipt_comment iptables mangle OUTPUT "$tag"
  _rth_sweep_ipt_comment iptables filter INPUT "$tag"
}

paqet_iptables_apply(){ # $1=port $2=role(server|client)
  local port="$1" role="${2:-server}" tag
  rth_valid_port "$port" || die "port paqet namotabar ast."
  tag="rathole-paqet-${role}-${port}"
  if ! command -v iptables >/dev/null 2>&1; then
    warn "iptables nasb nist; rule-haye raw/RST eemal nashodand."
    return 0
  fi
  paqet_iptables_remove "$port" "$role"
  if [ "$role" = "server" ]; then
    iptables -t raw -A PREROUTING -p tcp --dport "$port" -m comment --comment "$tag" -j CT --notrack 2>/dev/null || true
    iptables -t raw -A OUTPUT -p tcp --sport "$port" -m comment --comment "$tag" -j CT --notrack 2>/dev/null || true
    iptables -t mangle -A OUTPUT -p tcp --sport "$port" --tcp-flags RST RST -m comment --comment "$tag" -j DROP 2>/dev/null || true
    iptables -t filter -I INPUT -p tcp --dport "$port" -m comment --comment "$tag" -j ACCEPT 2>/dev/null || true
  else
    iptables -t raw -A PREROUTING -p tcp --sport "$port" -m comment --comment "$tag" -j CT --notrack 2>/dev/null || true
    iptables -t raw -A OUTPUT -p tcp --dport "$port" -m comment --comment "$tag" -j CT --notrack 2>/dev/null || true
    iptables -t mangle -A OUTPUT -p tcp --dport "$port" --tcp-flags RST RST -m comment --comment "$tag" -j DROP 2>/dev/null || true
  fi
}

# ---------------------------------------------------------------------------
# Managed Xray (VLESS+REALITY+Vision / VLESS+XHTTP + TLS Cover Site Scanner)
# ---------------------------------------------------------------------------
install_xray(){
  local bin="${RATHOLE_BIN_DIR:-/usr/local/bin}/xray" ver="${XRAY_VER:-24.12.31}" xarch tmp ok=0 m
  [ -x "$bin" ] && return 0
  case "$(uname -m)" in x86_64) xarch=64 ;; aarch64) xarch=arm64-v8a ;; *) die "memari poshtibani nemishavad baraye Xray." ;; esac
  command -v curl >/dev/null 2>&1 || die "curl lazem ast."
  command -v unzip >/dev/null 2>&1 || die "unzip lazem ast."
  local url="https://github.com/XTLS/Xray-core/releases/download/v${ver#v}/Xray-linux-${xarch}.zip"
  log "download Xray-core v${ver#v}..."
  tmp="$(mktemp -d)"
  if [ -n "${RATHOLE_UPDATE_PROXY:-}" ] && rth_valid_proxy_url "${RATHOLE_UPDATE_PROXY}"; then
    printf 'proxy = "%s"\n' "${RATHOLE_UPDATE_PROXY}" | \
      curl --config - -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 25 --retry 1 "$url" -o "$tmp/xray.zip" 2>/dev/null && ok=1
  else
    for m in "${RTH_MIRRORS[@]}"; do
      if curl -fsSL --connect-timeout 15 --speed-limit 1024 --speed-time 25 --retry 1 "${m}${url}" -o "$tmp/xray.zip" 2>/dev/null; then
        ok=1; break
      fi
      warn "in mnba javab nadad, mnba-ye badi..."
    done
  fi
  [ "$ok" -eq 1 ] || { rm -rf "$tmp"; die "download Xray az hame-ye mnaba shekast khord."; }
  unzip -qo "$tmp/xray.zip" -d "$tmp" || { rm -rf "$tmp"; die "baz kardan zip Xray shekast khord."; }
  [ -f "$tmp/xray" ] || { rm -rf "$tmp"; die "binary-e xray dar zip peyda nashod."; }
  mkdir -p "$(dirname "$bin")"
  install -m755 "$tmp/xray" "$bin" || { rm -rf "$tmp"; die "nasb binary xray shekast khord."; }
  local gf
  for gf in geoip.dat geosite.dat; do
    [ -f "$tmp/$gf" ] && install -m644 "$tmp/$gf" "$(dirname "$bin")/$gf" 2>/dev/null || true
  done
  rm -rf "$tmp"
  log "Xray-core nasb shod: $bin"
}

rth_xray_gen_x25519(){
  local xbin="${RATHOLE_BIN_DIR:-/usr/local/bin}/xray" priv="" pub="" out=""
  if [ -x "$xbin" ]; then
    out="$("$xbin" x25519 2>/dev/null || true)"
    priv="$(printf '%s\n' "$out" | sed -nE 's/^[Pp]rivate[[:space:]]*[Kk]ey:[[:space:]]*([A-Za-z0-9_-]{40,50}).*/\1/p' | head -n1)"
    pub="$(printf '%s\n' "$out" | sed -nE 's/^([Pp]ublic[[:space:]]*[Kk]ey|[Pp]assword):[[:space:]]*([A-Za-z0-9_-]{40,50}).*/\2/p' | head -n1)"
    if [ -n "$priv" ] && [ -n "$pub" ]; then
      printf '%s|%s\n' "$priv" "$pub"
      return 0
    fi
  fi
  command -v openssl >/dev/null 2>&1 || die "openssl ya xray baraye tolid-e kelid X25519 lazem ast."
  command -v python3 >/dev/null 2>&1 || die "python3 baraye tolid-e kelid X25519 lazem ast."
  local kd; kd="$(umask 077 && mktemp -d)"
  openssl genpkey -algorithm X25519 -out "$kd/priv.pem" 2>/dev/null || { rm -rf "$kd"; die "tolid X25519 shekast khord."; }
  openssl pkey -in "$kd/priv.pem" -outform DER -out "$kd/priv.der" 2>/dev/null || { rm -rf "$kd"; die "DER X25519 priv shekast."; }
  openssl pkey -in "$kd/priv.pem" -pubout -outform DER -out "$kd/pub.der" 2>/dev/null || { rm -rf "$kd"; die "DER X25519 pub shekast."; }
  local pair
  pair="$(python3 - "$kd/priv.der" "$kd/pub.der" <<'PY'
import base64, sys
priv_raw = open(sys.argv[1], "rb").read()
pub_raw = open(sys.argv[2], "rb").read()
if len(priv_raw) < 32 or len(pub_raw) < 32:
    sys.exit(1)
priv_b64 = base64.urlsafe_b64encode(priv_raw[-32:]).decode("ascii").rstrip("=")
pub_b64 = base64.urlsafe_b64encode(pub_raw[-32:]).decode("ascii").rstrip("=")
print(f"{priv_b64}|{pub_b64}")
PY
)" || { rm -rf "$kd"; die "ramzgodari kelid X25519 shekast khord."; }
  rm -rf "$kd"
  printf '%s\n' "$pair"
}

rth_xray_scan_cover(){
  command -v python3 >/dev/null 2>&1 || die "python3 baraye scanner-e cover lazem ast."
  local domains="www.microsoft.com,www.apple.com,www.cloudflare.com,www.nvidia.com,www.intel.com,www.amd.com,www.oracle.com,www.cisco.com"
  local port=443 timeout_s=4 top_n=5 as_json=0 target_host="${RATHOLE_SCAN_TARGET_HOST:-}"
  while [ $# -gt 0 ]; do
    case "$1" in
      --domains) [ $# -ge 2 ] || die "--domains list mikhahad."; domains="$2"; shift 2 ;;
      --domains=*) domains="${1#*=}"; shift ;;
      --port) [ $# -ge 2 ] || die "--port adad mikhahad."; port="$2"; shift 2 ;;
      --port=*) port="${1#*=}"; shift ;;
      --timeout) [ $# -ge 2 ] || die "--timeout adad mikhahad."; timeout_s="$2"; shift 2 ;;
      --timeout=*) timeout_s="${1#*=}"; shift ;;
      --top) [ $# -ge 2 ] || die "--top adad mikhahad."; top_n="$2"; shift 2 ;;
      --top=*) top_n="${1#*=}"; shift ;;
      --target-host) [ $# -ge 2 ] || die "--target-host IP/host mikhahad."; target_host="$2"; shift 2 ;;
      --target-host=*) target_host="${1#*=}"; shift ;;
      --json) as_json=1; shift ;;
      *) die "estefade: xray scan [--domains d1,d2,...] [--port 443] [--timeout 4] [--top 5] [--json]" ;;
    esac
  done
  rth_valid_port "$port" || die "port namotabar ast."
  echo "$timeout_s" | grep -qE '^[1-9][0-9]?$' || die "timeout namotabar ast."
  echo "$top_n" | grep -qE '^[1-9][0-9]?$' || die "top namotabar ast."
  local cafile="${RATHOLE_SCAN_CAFILE:-}"
  python3 - "$domains" "$port" "$timeout_s" "$top_n" "$as_json" "$target_host" "$cafile" <<'PY'
import concurrent.futures
import json
import re
import socket
import ssl
import sys
import time

raw_domains, port_s, to_s, top_s, json_s, target_host, cafile = sys.argv[1:8]
port = int(port_s)
timeout_s = float(to_s)
top_n = int(top_s)
as_json = (json_s == "1")
re_dom = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{1,253}$")

domains = []
seen = set()
for item in raw_domains.split(","):
    d = item.strip().lower()
    if not d:
        continue
    if not re_dom.match(d) or ".." in d:
        if as_json:
            print(json.dumps({"ok": False, "error": f"invalid domain: {d}"}))
        else:
            sys.stderr.write(f"[!] domain namotabar: {d}\n")
        sys.exit(1)
    if d not in seen:
        seen.add(d)
        domains.append(d)
    if len(domains) >= 20:
        break

if not domains:
    sys.stderr.write("[!] hich domain-i baraye scan nist.\n")
    sys.exit(1)

ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
try:
    ctx.set_alpn_protocols(["h2", "http/1.1"])
except Exception:
    pass


def probe_one(dom):
    dial_host = target_host or dom
    t0 = time.monotonic()
    sock = None
    try:
        sock = socket.create_connection((dial_host, port), timeout=timeout_s)
        sock.settimeout(timeout_s)
        with ctx.wrap_socket(sock, server_hostname=dom) as ss:
            sock = None
            rtt = round((time.monotonic() - t0) * 1000.0, 1)
            ver = ss.version() or ""
            alpn = ss.selected_alpn_protocol() or ""
        ok = (ver == "TLSv1.3")
        return {
            "domain": dom,
            "ok": ok,
            "verdict": "GOOD" if ok else "SKIP",
            "tls_version": ver,
            "alpn": alpn,
            "rtt_ms": rtt,
            "detail": "" if ok else f"requires TLSv1.3 (got {ver or 'none'})",
        }
    except Exception as exc:
        rtt = round((time.monotonic() - t0) * 1000.0, 1)
        return {
            "domain": dom,
            "ok": False,
            "verdict": "FAIL",
            "tls_version": "",
            "alpn": "",
            "rtt_ms": rtt,
            "detail": str(exc)[:100],
        }
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(domains))) as pool:
    results = list(pool.map(probe_one, domains))


def sort_key(r):
    alpn_rank = 0 if r["alpn"] == "h2" else (1 if r["alpn"] else 2)
    return (0 if r["ok"] else 1, alpn_rank, r["rtt_ms"])


results.sort(key=sort_key)
good = [r for r in results if r["ok"]]
out_list = results[:top_n] if not as_json else results
rec = good[0]["domain"] if good else ""

if as_json:
    print(json.dumps({
        "ok": bool(good),
        "port": port,
        "recommended": rec,
        "results": results[:top_n] if top_n else results,
    }, separators=(",", ":")))
else:
    print(f"{'STATUS':<8} {'DOMAIN':<28} {'TLS':<8} {'ALPN':<9} {'RTT(ms)':<9} {'DETAIL'}")
    print("-" * 74)
    for r in out_list:
        print(f"{r['verdict']:<8} {r['domain']:<28} {r['tls_version'] or '-':<8} {r['alpn'] or '-':<9} {str(r['rtt_ms']):<9} {r['detail']}")
    if rec:
        print(f"\n[+] pishnahad-e cover (REALITY dest/sni): {rec}:{port}")
    else:
        print("\n[!] hich cover site ba TLSv1.3 + cert motabar peyda nashod.")
PY
}

# ---------------------------------------------------------------------------
# rathole-tuner CLI wrapper (moshtarak beyn-e ratholectl va ratholenode)
# ---------------------------------------------------------------------------
rth_bench_exec(){ # $1=role (iran|node) $2=subcommand $@=args
  local role="$1"; shift || true
  local sub="${1:-status}"; shift || true
  local pidfile="${RATHOLE_TUNER_PIDFILE:-/run/rathole-tuner-responder.pid}"
  local logfile="${RATHOLE_TUNER_LOG:-/var/log/rathole-tuner-responder.log}"
  local jobs_dir="${RATHOLE_TUNER_JOBS_DIR:-/var/lib/rathole-tuner/jobs}"

  if [ "$sub" = "stop-listen" ]; then
    need_root
    if [ -f "$pidfile" ]; then
      local pid=""
      pid="$(tr -d '[:space:]' < "$pidfile" 2>/dev/null || true)"
      if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        local w=0
        while [ "$w" -lt 30 ] && kill -0 "$pid" 2>/dev/null; do
          w=$((w + 1)); sleep 0.1
        done
        kill -9 "$pid" 2>/dev/null || true
      fi
      rm -f "$pidfile"
    fi
    echo '{"ok":true,"stopped":true}'
    return 0
  fi

  if [ "$sub" = "job" ]; then
    local jid="${1:-}"
    [[ "$jid" =~ ^[A-Za-z0-9_-]{1,64}$ ]] || die "job_id namotabar ast."
    local pf="${jobs_dir}/${jid}/progress.json"
    if [ -f "$pf" ]; then
      cat "$pf"
    else
      printf '{"ok":false,"job_id":"%s","detail":"progress not found"}\n' "$jid"
    fi
    return 0
  fi

  command -v python3 >/dev/null 2>&1 || die "python3 baraye rathole-tuner lazem ast."
  local tbin="" cand self_dir=""
  [ -n "${BASH_SOURCE[0]:-}" ] && self_dir="${BASH_SOURCE[0]%/*}"
  for cand in "${RATHOLE_TUNER_BIN:-}" /usr/local/bin/rathole-tuner "${self_dir:+$self_dir/rathole-tuner}" /opt/rathole-manager/rathole-tuner; do
    if [ -n "$cand" ] && [ -f "$cand" ]; then
      tbin="$cand"
      break
    fi
  done
  [ -n "$tbin" ] || die "rathole-tuner peyda nashod."

  case "$sub" in
    listen)
      need_root
      local is_daemon=0 arg port_hint="29890" prev=""
      local -a fwd_args=()
      for arg in "$@"; do
        if [ "$arg" = "--daemon" ]; then
          is_daemon=1
        else
          fwd_args+=("$arg")
        fi
        [ "$prev" = "--port" ] && port_hint="$arg"
        prev="$arg"
      done
      if [ "$is_daemon" -eq 1 ]; then
        if [ -f "$pidfile" ]; then
          local old_pid=""
          old_pid="$(tr -d '[:space:]' < "$pidfile" 2>/dev/null || true)"
          if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
            kill "$old_pid" 2>/dev/null || true
            sleep 0.2
          fi
          rm -f "$pidfile"
        fi
        mkdir -p "$(dirname "$pidfile")" "$(dirname "$logfile")" 2>/dev/null || true
        setsid python3 "$tbin" listen "${fwd_args[@]}" --pidfile "$pidfile" >"$logfile" 2>&1 < /dev/null &
        local spawned_pid=$! i=0 ready=0
        while [ "$i" -lt 30 ]; do
          if [ -s "$pidfile" ]; then
            ready=1; break
          fi
          kill -0 "$spawned_pid" 2>/dev/null || break
          i=$((i + 1)); sleep 0.1
        done
        if [ "$ready" -eq 1 ]; then
          printf '{"ok":true,"pid":%s,"port":%s}\n' "$(tr -d '[:space:]' < "$pidfile" 2>/dev/null || echo "$spawned_pid")" "$port_hint"
          return 0
        fi
        err "responder daemon bala nayamad:"
        tail -n 10 "$logfile" >&2 2>/dev/null || true
        return 1
      fi
      python3 "$tbin" listen "${fwd_args[@]}"
      ;;
    run|test-profile|compare|apply|rollback)
      need_root
      local has_side=0 a
      for a in "$@"; do
        [ "$a" = "--side" ] && has_side=1
      done
      if { [ "$sub" = "run" ] || [ "$sub" = "apply" ]; } && [ "$has_side" -eq 0 ]; then
        python3 "$tbin" "$sub" "$@" --side "$role"
      else
        python3 "$tbin" "$sub" "$@"
      fi
      ;;
    export|validate|status)
      python3 "$tbin" "$sub" "$@"
      ;;
    *)
      die "zir-dastoor bench nashenakhte: $sub (listen|stop-listen|run|test-profile|compare|export|validate|apply|rollback|status|job)"
      ;;
  esac
}
