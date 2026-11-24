#!/usr/bin/env bash
# test_m6_updates_signing_and_backhaul_verify.sh — M6: Ed25519 signing, relayed updates (--proxy), & Backhaul TLS CA pinning
set -uo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TEST_TMP_ROOT="${TEST_TMP_ROOT:-${TMPDIR:-/tmp}}"
command -v openssl >/dev/null 2>&1 || fail "openssl lazem ast"

D="$(mktemp -d "${TEST_TMP_ROOT%/}/test-m6.XXXXXX")"
trap 'rm -rf "$D"' EXIT INT TERM

# ---- 1: tools/release-sign.sh syntax + keygen/sign/verify/tamper ----
bash -n "$REPO_ROOT/tools/release-sign.sh" || fail "release-sign.sh syntax error"
KEYDIR="$D/keys"
bash "$REPO_ROOT/tools/release-sign.sh" keygen "$KEYDIR" >/dev/null || fail "keygen shekast"
PRIV="$KEYDIR/release-ed25519.key"
PUB="$KEYDIR/release-ed25519.pub"
[ -s "$PRIV" ] && [ -s "$PUB" ] || fail "kelid-haye Ed25519 sakhte nashodand"

KEYDIR2="$D/keys2"
bash "$REPO_ROOT/tools/release-sign.sh" keygen "$KEYDIR2" >/dev/null || fail "keygen2 shekast"
PUB2="$KEYDIR2/release-ed25519.pub"

SAMPLESUM="$D/sample.SHA256SUMS"
printf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  sample.bin\n' > "$SAMPLESUM"
bash "$REPO_ROOT/tools/release-sign.sh" sign "$PRIV" "$SAMPLESUM" >/dev/null || fail "sign shekast"
[ -s "${SAMPLESUM}.sig" ] || fail "file .sig sakhte nashod"
bash "$REPO_ROOT/tools/release-sign.sh" verify "$PUB" "$SAMPLESUM" "${SAMPLESUM}.sig" >/dev/null || fail "verify motabar fail shod"

cp "$SAMPLESUM" "$D/tampered.SHA256SUMS"
printf '# tampered\n' >> "$D/tampered.SHA256SUMS"
! bash "$REPO_ROOT/tools/release-sign.sh" verify "$PUB" "$D/tampered.SHA256SUMS" "${SAMPLESUM}.sig" >/dev/null 2>&1 \
  || fail "file tampered bayad reject shavad"
! bash "$REPO_ROOT/tools/release-sign.sh" verify "$PUB2" "$SAMPLESUM" "${SAMPLESUM}.sig" >/dev/null 2>&1 \
  || fail "wrong pubkey bayad reject shavad"
printf 'AAAA%s\n' "$(tail -c +5 "${SAMPLESUM}.sig")" > "$D/bad.sig"
! bash "$REPO_ROOT/tools/release-sign.sh" verify "$PUB" "$SAMPLESUM" "$D/bad.sig" >/dev/null 2>&1 \
  || fail "sig tampered bayad reject shavad"
ok "tools/release-sign.sh: keygen/sign/verify + tamper & wrong-key rejection"

# ---- 2: core-install.sh --verify-only Ed25519 policy ----
CORE_DIR="$D/core"
mkdir -p "$CORE_DIR/x86_64-unknown-linux-gnu" "$CORE_DIR/aarch64-unknown-linux-gnu"
printf '#!/bin/sh\necho "rathole 0.5.1-ratholeengine.1"\n' > "$CORE_DIR/x86_64-unknown-linux-gnu/rathole"
printf '#!/bin/sh\necho "rathole 0.5.1-ratholeengine.1"\n' > "$CORE_DIR/aarch64-unknown-linux-gnu/rathole"
chmod +x "$CORE_DIR"/*/rathole
( cd "$CORE_DIR" && sha256sum "x86_64-unknown-linux-gnu/rathole" "aarch64-unknown-linux-gnu/rathole" > SHA256SUMS )

# unsigned passes without --require-sig, fails with --require-sig
RATHOLE_CORE_DIR="$CORE_DIR" bash "$REPO_ROOT/rathole-manager/core-install.sh" --verify-only >/dev/null 2>&1 \
  || fail "core-install unsigned bedoon --require-sig bayad pass shavad"
! RATHOLE_CORE_DIR="$CORE_DIR" bash "$REPO_ROOT/rathole-manager/core-install.sh" --verify-only --require-sig >/dev/null 2>&1 \
  || fail "core-install unsigned ba --require-sig bayad fail shavad"

# signed passes with --require-sig + --pubkey
bash "$REPO_ROOT/tools/release-sign.sh" sign "$PRIV" "$CORE_DIR/SHA256SUMS" "$CORE_DIR/SHA256SUMS.sig" >/dev/null
RATHOLE_CORE_DIR="$CORE_DIR" bash "$REPO_ROOT/rathole-manager/core-install.sh" --verify-only --require-sig "--pubkey=$PUB" >/dev/null 2>&1 \
  || fail "core-install signed ba --require-sig bayad pass shavad"

# bad sig fails EVEN WITHOUT --require-sig
cp "$D/bad.sig" "$CORE_DIR/SHA256SUMS.sig"
! RATHOLE_CORE_DIR="$CORE_DIR" bash "$REPO_ROOT/rathole-manager/core-install.sh" --verify-only "--pubkey=$PUB" >/dev/null 2>&1 \
  || fail "core-install ba emza-ye namotabar bayad fail shavad hatta bedoon --require-sig"
ok "core-install.sh: Ed25519 verification + fail-closed policy"

# ---- 3: common.sh install_backhaul_core Ed25519 verification ----
BH_SB="$D/bh-sb"
mkdir -p "$BH_SB/core-backhaul/linux-amd64" "$BH_SB/core-backhaul/linux-arm64" "$BH_SB/bin"
printf 'BH-CORE-M6\n' > "$BH_SB/core-backhaul/linux-amd64/backhaul"
printf 'BH-CORE-M6\n' > "$BH_SB/core-backhaul/linux-arm64/backhaul"
( cd "$BH_SB/core-backhaul" && sha256sum linux-amd64/backhaul linux-arm64/backhaul > SHA256SUMS )
bash "$REPO_ROOT/tools/release-sign.sh" sign "$PRIV" "$BH_SB/core-backhaul/SHA256SUMS" "$BH_SB/core-backhaul/SHA256SUMS.sig" >/dev/null

(
  set -uo pipefail
  # shellcheck disable=SC1091
  source "$REPO_ROOT/rathole-manager/common.sh"
  export RATHOLE_BIN_DIR="$BH_SB/bin" RATHOLE_CORE_BACKHAUL_DIR="$BH_SB/core-backhaul"
  export RATHOLE_SIGNING_PUBKEY="$PUB" RATHOLE_REQUIRE_SIG=1
  install_backhaul_core client >/dev/null 2>&1 || exit 1
  grep -qF 'BH-CORE-M6' "$BH_SB/bin/backhaul-client" || exit 2
) || fail "install_backhaul_core ba emza-ye sahih shekast khord"

rm -f "$BH_SB/bin/backhaul-client"
cp "$D/bad.sig" "$BH_SB/core-backhaul/SHA256SUMS.sig"
(
  set -uo pipefail
  # shellcheck disable=SC1091
  source "$REPO_ROOT/rathole-manager/common.sh"
  export RATHOLE_BIN_DIR="$BH_SB/bin" RATHOLE_CORE_BACKHAUL_DIR="$BH_SB/core-backhaul"
  export RATHOLE_SIGNING_PUBKEY="$PUB" RATHOLE_REQUIRE_SIG=0
  ! install_backhaul_core client >/dev/null 2>&1
) || fail "install_backhaul_core ba emza-ye kharab bayad fail shavad"
ok "common.sh: install_backhaul_core Ed25519 enforcement"

# ---- 4: install.sh --proxy, redaction, Ed25519 sig & checksum verification ----
INST_SB="$D/inst-sb"
mkdir -p "$INST_SB/bin" "$INST_SB/rel" "$INST_SB/log"
cat > "$INST_SB/rel/bootstrap.sh" <<'BOOT'
#!/usr/bin/env bash
printf '%s|%s|%s\n' "${RATHOLE_REQUIRE_SIG:-}" "${RATHOLE_SIGNING_PUBKEY:-}" "$*" > "${TEST_BOOT_OUT}"
BOOT
chmod +x "$INST_SB/rel/bootstrap.sh"
printf 'FAKEZIP_CONTENT_M6\n' > "$INST_SB/rel/rathole-manager.zip"
( cd "$INST_SB/rel" && sha256sum rathole-manager.zip bootstrap.sh > SHA256SUMS )
bash "$REPO_ROOT/tools/release-sign.sh" sign "$PRIV" "$INST_SB/rel/SHA256SUMS" "$INST_SB/rel/SHA256SUMS.sig" >/dev/null

# bad proxy URL must be rejected
sed 's/\r$//' "$REPO_ROOT/install.sh" > "$INST_SB/install.sh"
cat > "$INST_SB/bin/id" <<'IDSH'
#!/bin/sh
echo 0
IDSH
cat > "$INST_SB/bin/curl" <<'CURLSH'
#!/usr/bin/env bash
cfg=""
for a in "$@"; do
  if [ "$a" = "--config" ]; then
    cfg="$(cat)"
    printf '%s\n' "$cfg" >> "$TEST_CURL_LOG/cfg.log"
    break
  fi
done
printf '%s\n' "$*" >> "$TEST_CURL_LOG/argv.log"
url=""
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    http://*|https://*) url="$1"; shift ;;
    *) shift ;;
  esac
done
base="${url##*/}"
if [ -f "$TEST_REL_DIR/$base" ]; then
  cp "$TEST_REL_DIR/$base" "$out"
  exit 0
fi
exit 22
CURLSH
chmod +x "$INST_SB/bin/id" "$INST_SB/bin/curl"

# Invalid proxy URL containing shell metachars fails before curl runs
! PATH="$INST_SB/bin:$PATH" TEST_REL_DIR="$INST_SB/rel" TEST_CURL_LOG="$INST_SB/log" TEST_BOOT_OUT="$INST_SB/boot.out" \
  bash "$INST_SB/install.sh" --proxy 'socks5h://127.0.0.1:1080;id' --update >/dev/null 2>&1 \
  || fail "install.sh bayad proxy-e ba metacharacter ra rad konad"
[ ! -f "$INST_SB/log/argv.log" ] || fail "curl dar proxy-e namotabar nabayad ejra shavad"

# Valid signed update through authenticated proxy redacts creds and verifies Ed25519
out_inst="$(PATH="$INST_SB/bin:$PATH" TEST_REL_DIR="$INST_SB/rel" TEST_CURL_LOG="$INST_SB/log" TEST_BOOT_OUT="$INST_SB/boot.out" \
  bash "$INST_SB/install.sh" --proxy 'socks5h://uproxy:secretpw@127.0.0.1:1080' --require-sig --pubkey "$PUB" --update 2>&1)" \
  || fail "install.sh ba proxy + --require-sig shekast khord: $out_inst"
grep -qF 'proxy = "socks5h://uproxy:secretpw@127.0.0.1:1080"' "$INST_SB/log/cfg.log" \
  || fail "curl --config proxy daryaft nakard"
! grep -qF 'secretpw' "$INST_SB/log/argv.log" || fail "ramz proxy dar argv-e curl nashat kard"
! printf '%s' "$out_inst" | grep -qF 'secretpw' || fail "ramz proxy dar output redact nashod"
printf '%s' "$out_inst" | grep -qF 'socks5h://***@127.0.0.1:1080' || fail "proxy redact-shode namayesh dade nashod"
grep -qF "1|${PUB}|--local " "$INST_SB/boot.out" || fail "bootstrap env/args eshtebah ast: $(cat "$INST_SB/boot.out")"

# Tampered SHA256SUMS rejected by Ed25519 before bootstrap runs
rm -f "$INST_SB/boot.out"
cp "$INST_SB/rel/SHA256SUMS" "$INST_SB/rel/SHA256SUMS.orig"
printf 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb  evil.zip\n' >> "$INST_SB/rel/SHA256SUMS"
! PATH="$INST_SB/bin:$PATH" TEST_REL_DIR="$INST_SB/rel" TEST_CURL_LOG="$INST_SB/log" TEST_BOOT_OUT="$INST_SB/boot.out" \
  bash "$INST_SB/install.sh" --proxy 'socks5h://127.0.0.1:1080' --pubkey "$PUB" --update >/dev/null 2>&1 \
  || fail "install.sh bayad SHA256SUMS-e tampered ra reject konad"
[ ! -f "$INST_SB/boot.out" ] || fail "bootstrap pas az khata-ye Ed25519 nabayad ejra shavad"
mv -f "$INST_SB/rel/SHA256SUMS.orig" "$INST_SB/rel/SHA256SUMS"

# Missing .sig with --require-sig rejected before bootstrap runs
mv -f "$INST_SB/rel/SHA256SUMS.sig" "$INST_SB/rel/SHA256SUMS.sig.bak"
! PATH="$INST_SB/bin:$PATH" TEST_REL_DIR="$INST_SB/rel" TEST_CURL_LOG="$INST_SB/log" TEST_BOOT_OUT="$INST_SB/boot.out" \
  bash "$INST_SB/install.sh" --require-sig --pubkey "$PUB" --update >/dev/null 2>&1 \
  || fail "install.sh ba --require-sig va naboodan-e .sig bayad reject konad"
[ ! -f "$INST_SB/boot.out" ] || fail "bootstrap ba --require-sig bedoon .sig ejra shod"
ok "install.sh: --proxy via curl stdin, secret redaction, Ed25519 + SHA256 enforcement"

# ---- 5: ratholectl / ratholenode cmd_update --proxy validation & forwarding ----
UPD_SB="$D/upd-sb"
mkdir -p "$UPD_SB/bin" "$UPD_SB/logs"
cat > "$UPD_SB/bin/id" <<'IDSH'
#!/bin/sh
echo 0
IDSH
cat > "$UPD_SB/bin/systemctl" <<'SYSSH'
#!/bin/sh
exit 0
SYSSH
cat > "$UPD_SB/bin/curl" <<'CURL2'
#!/usr/bin/env bash
for a in "$@"; do
  if [ "$a" = "--config" ]; then
    cat > "$TEST_UPD_LOGS/curl.cfg"
    break
  fi
done
printf '%s\n' "$*" > "$TEST_UPD_LOGS/curl.argv"
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
cat > "$out" <<'MININST'
#!/usr/bin/env bash
printf '%s|%s|%s|%s\n' "${RATHOLE_RELEASE:-}" "${RATHOLE_UPDATE_PROXY:-}" "${RATHOLE_REQUIRE_SIG:-}" "$*" > "$TEST_UPD_LOGS/ran.out"
MININST
exit 0
CURL2
chmod +x "$UPD_SB/bin/id" "$UPD_SB/bin/systemctl" "$UPD_SB/bin/curl"

! PATH="$UPD_SB/bin:$PATH" TEST_UPD_LOGS="$UPD_SB/logs" bash "$REPO_ROOT/rathole-manager/ratholectl" update --proxy 'http://1.2.3.4:8080;id' >/dev/null 2>&1 \
  || fail "ratholectl update proxy namotabar ra rad nakard"
PATH="$UPD_SB/bin:$PATH" TEST_UPD_LOGS="$UPD_SB/logs" bash "$REPO_ROOT/rathole-manager/ratholenode" update v2.1.1 --proxy 'socks5h://u:p@127.0.0.1:1080' --require-sig >/dev/null 2>&1 \
  || fail "ratholenode update --proxy --require-sig shekast khord"
grep -qF 'proxy = "socks5h://u:p@127.0.0.1:1080"' "$UPD_SB/logs/curl.cfg" || fail "ratholenode update proxy dar curl --config nist"
! grep -qF 'p@127' "$UPD_SB/logs/curl.argv" || fail "ramz proxy dar argv nashat kard"
grep -qF 'v2.1.1|socks5h://u:p@127.0.0.1:1080|1|--update' "$UPD_SB/logs/ran.out" || fail "ratholenode update env forwarding eshtebah ast"
ok "ratholectl/ratholenode update: --proxy + --require-sig forwarding & redaction"

# ---- 6: ratholenode backhaul TLS CA pinning (explicit --ca, auto IP discovery, domain verify, off) ----
BH_NODE_SB="$D/bh-node"
mkdir -p "$BH_NODE_SB/etc/rathole/certs" "$BH_NODE_SB/systemd" "$BH_NODE_SB/bin"
cat > "$BH_NODE_SB/etc/rathole/node.env" <<'NE'
SERVER=panel.example.ir:443
TLS_HOSTNAME=panel.example.ir
NE
: > "$BH_NODE_SB/etc/rathole/services.conf"
: > "$BH_NODE_SB/etc/rathole/bh-services.conf"
printf 'STUB-BACKHAUL\n' > "$BH_NODE_SB/bin/backhaul-client"
chmod +x "$BH_NODE_SB/bin/backhaul-client"

IP_CERT="$BH_NODE_SB/etc/rathole/certs/198.51.100.10.crt"
IP_KEY="$D/ip.key"
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 30 \
  -subj "/CN=198.51.100.10" -addext "subjectAltName=IP:198.51.100.10" \
  -keyout "$IP_KEY" -out "$IP_CERT" >/dev/null 2>&1 || fail "tolid ip cert baraye test shekast khord"

# Helper runner overriding ratholenode globals cleanly
_run_rn_bh(){
  local tmp_script="$BH_NODE_SB/rn_exec.sh"
  {
    cat <<HDR
export PATH="${BH_NODE_SB}/bin:\$PATH"
export RATHOLE_BIN_DIR="${BH_NODE_SB}/bin"
id(){ echo 0; }
systemctl(){ return 0; }
HDR
    python3 - "$REPO_ROOT/rathole-manager/ratholenode" "$REPO_ROOT/rathole-manager" "$BH_NODE_SB" <<'PY'
import sys
src, rdir, sb = sys.argv[1], sys.argv[2], sys.argv[3]
rep = {
    "SCRIPT_DIR=": f'SCRIPT_DIR="{rdir}"\n',
    "ENV_FILE=": f'ENV_FILE="{sb}/etc/rathole/node.env"\n',
    "SVC_FILE=": f'SVC_FILE="{sb}/etc/rathole/services.conf"\n',
    "BH_SVC_FILE=": f'BH_SVC_FILE="{sb}/etc/rathole/bh-services.conf"\n',
    "BH_TOML=": f'BH_TOML="{sb}/etc/rathole/backhaul-client.toml"\n',
    "BH_CLI_UNIT=": f'BH_CLI_UNIT="{sb}/systemd/rathole-backhaul-client.service"\n',
    "RTH_LOCK=": f'RTH_LOCK="{sb}/node.lock"\n',
}
with open(src, encoding="utf-8") as fh:
    for line in fh:
        for k, v in rep.items():
            if line.startswith(k):
                line = v
                break
        sys.stdout.write(line)
PY
  } > "$tmp_script"
  bash "$tmp_script" "$@"
}

BH_TOK="0123456789abcdef0123456789abcdef"
# a) Explicit --ca + --sni on direct IP
_run_rn_bh backhaul on 198.51.100.10:3080 "$BH_TOK" wssmux balanced --ca "$IP_CERT" --sni cdn.example.com >/dev/null 2>&1 \
  || fail "ratholenode backhaul on ba --ca shekast khord"
UNIT_F="$BH_NODE_SB/systemd/rathole-backhaul-client.service"
grep -qF "Environment=\"BACKHAUL_TLS_CA=${IP_CERT}\"" "$UNIT_F" || fail "BACKHAUL_TLS_CA dar unit neveshte nashod"
grep -qF 'Environment="BACKHAUL_TLS_VERIFY_NAME=198.51.100.10"' "$UNIT_F" || fail "BACKHAUL_TLS_VERIFY_NAME baraye IP neveshte nashod"
grep -qF 'Environment="BACKHAUL_TLS_SNI=cdn.example.com"' "$UNIT_F" || fail "BACKHAUL_TLS_SNI dar unit neveshte nashod"

# b) Auto-discover via TLS_TRUSTED_ROOT when --ca is omitted
printf 'SERVER=198.51.100.10:443\nTLS_HOSTNAME=198.51.100.10\nTLS_TRUSTED_ROOT=%s\n' "$IP_CERT" > "$BH_NODE_SB/etc/rathole/node.env"
_run_rn_bh backhaul on 198.51.100.10:3080 "$BH_TOK" wssmux balanced >/dev/null 2>&1 \
  || fail "auto-discover BACKHAUL_TLS_CA shekast khord"
grep -qF "Environment=\"BACKHAUL_TLS_CA=${IP_CERT}\"" "$UNIT_F" || fail "auto-discovered BACKHAUL_TLS_CA dar unit nist"
grep -qF 'Environment="BACKHAUL_TLS_VERIFY_NAME=198.51.100.10"' "$UNIT_F" || fail "auto BACKHAUL_TLS_VERIFY_NAME nist"

# c) Domain nginx_tls wssmux defaults to system CA verification
_run_rn_bh backhaul on panel.example.ir "$BH_TOK" wssmux balanced >/dev/null 2>&1 \
  || fail "nginx_tls backhaul on shekast khord"
grep -qF 'Environment="BACKHAUL_TLS_VERIFY=1"' "$UNIT_F" || fail "BACKHAUL_TLS_VERIFY=1 baraye domain set nashod"
grep -qF 'Environment="BACKHAUL_TLS_VERIFY_NAME=panel.example.ir"' "$UNIT_F" || fail "BACKHAUL_TLS_VERIFY_NAME baraye domain nist"
! grep -qF 'BACKHAUL_TLS_CA=' "$UNIT_F" || fail "BACKHAUL_TLS_CA dar domain mode nabayad set bashad"

# d) backhaul off clears BH_TLS_* vars
_run_rn_bh backhaul off >/dev/null 2>&1 || fail "backhaul off shekast khord"
! grep -qE '^BH_TLS_' "$BH_NODE_SB/etc/rathole/node.env" || fail "BH_TLS_* baad az backhaul off pak nashod"
ok "ratholenode: Backhaul direct_ip CA pinning, SAN auto-discovery, domain verify & cleanup"

# ---- 7: Offline git apply check for core-backhaul 0001 + 0002 patches ----
if command -v git >/dev/null 2>&1; then
  PDIR="$D/bh-patch"
  mkdir -p "$PDIR/internal/client/transport"
  cat > "$PDIR/internal/client/transport/shared.go" <<'SGO'
package transport

import (
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"net/http"
	"time"
	"github.com/gorilla/websocket"
)

func attemptDialWebSocket(ctx context.Context, addr string, edgeIP string, path string, mode config.TransportType) {
	if false {
	} else if mode == config.WSS || mode == config.WSSMUX {
		wsURL = fmt.Sprintf("wss://%s%s", addr, path)

		// Create a TLS configuration that allows insecure connections
		tlsConfig := &tls.Config{
			InsecureSkipVerify: true, // Skip server certificate verification
		}

		dialer = websocket.Dialer{
			EnableCompression: true,
			TLSClientConfig:   tlsConfig,        // Pass the insecure TLS config here
			HandshakeTimeout:  45 * time.Second, // default handshake timeout
			NetDial: func(_, addr string) (net.Conn, error) {
				conn, err := TcpDialer(ctx, edgeIP, timeout, keepalive, nodelay, 1, SO_RCVBUF, SO_SNDBUF)
				if err != nil {
					return nil, err
				}
				return conn, nil
			},
		}
	}
}
SGO
  git -C "$PDIR" init -q
  git -C "$PDIR" config user.email "t@example.com"
  git -C "$PDIR" config user.name "t"
  git -C "$PDIR" add .
  git -C "$PDIR" commit -qm "base"
  for pf in "$REPO_ROOT"/core-backhaul/patches/*.patch; do
    git -C "$PDIR" apply --check "$pf" || fail "patch apply check failed offline: $(basename "$pf")"
    git -C "$PDIR" apply "$pf" || fail "patch apply failed offline: $(basename "$pf")"
  done
  grep -qF 'VerifyPeerCertificate' "$PDIR/internal/client/transport/utls.go" || fail "VerifyPeerCertificate missing after 0002 patch"
  grep -qF 'BACKHAUL_TLS_CA' "$PDIR/internal/client/transport/utls.go" || fail "BACKHAUL_TLS_CA missing after 0002 patch"
  ok "core-backhaul patches (0001 + 0002): offline git apply & symbols verified"
fi

echo "---"
echo "ALL M6 BASH TESTS PASSED"
