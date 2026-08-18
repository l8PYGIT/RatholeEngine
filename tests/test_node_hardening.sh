#!/usr/bin/env bash
set -euo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/test-node-hardening.XXXXXX")"
trap 'rm -rf "$ROOT"' EXIT INT TERM

export RATHOLENODE_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholenode"

ENV_FILE="$ROOT/node.env"
SVC_FILE="$ROOT/services.conf"
BH_SVC_FILE="$ROOT/bh-services.conf"
CLIENT_TOML="$ROOT/client.toml"
ADAPTIVE_STATE="$ROOT/adaptive-state.json"
ADAPTIVE_ENV="$ROOT/adaptive.env"
WD_ENV="$ROOT/watchdog.env"
UP_DIR="$ROOT/upstreams"
need_root(){ :; }
rth_commit_config(){ cp "$1" "$2"; }

printf 'SERVER=panel.example:443\nWS_PATH=/_rh/test\n' > "$ENV_FILE"
printf 'n1|token123|2087\n' > "$SVC_FILE"
gen_client
! grep -q 'path = "/_rh/test"' "$CLIENT_TOML" || fail 'legacy WS_PATH نباید path جدید بسازد'
ok 'env parser config-e legacy ra bekhoand va WS_PATH inert mand'

PWN="$ROOT/pwned"
printf 'SERVER=$(touch %s)\n' "$PWN" > "$ENV_FILE"
if load_env_file "$ENV_FILE" 2>/dev/null; then
  fail 'env parser meghdar-e shell code ra rad nakard'
fi
[ ! -e "$PWN" ] || fail 'env parser shell code ra ejra kard'
ok 'env parser shell injection ra rad kard'

REDACTED="$(printf 'svc|super-secret-token|2087\n' | rth_redact)"
printf '%s\n' "$REDACTED" | grep -Fq 'svc|***REDACTED***|2087' \
  || fail 'rth_redact token-e services.conf ra posht-e pipe leak kard'
! printf '%s\n' "$REDACTED" | grep -q 'super-secret-token' \
  || fail 'rth_redact token-e services.conf ra leak kard'
ok 'logs redact token-e services.conf ra pooshesh midahad'

printf 'SERVER=panel.example:443\nBH_TOKEN=backhaul-secret\n' > "$ENV_FILE"
SHOW="$(cmd_show)"
! printf '%s\n' "$SHOW" | grep -qE 'token123|backhaul-secret' \
  || fail 'cmd_show token ra leak kard'
ok 'cmd_show token-haye node va service ra makhfi negah midarad'

RESTARTED=0
systemctl(){
  case "${1:-} ${2:-}" in
    'is-active --quiet') return 0 ;;
    'restart '*|'restart') RESTARTED=1; return 0 ;;
  esac
  return 0
}
adaptive_run_probe(){ echo ws_rejected; return 0; }
SVC=main
WD_PROBE=1
if wd_check_one main "" main; then
  fail 'watchdog tunnel-e active-vali-gir-karde ra fail tashkhis nadad'
fi
[ "$RESTARTED" -eq 1 ] || fail 'watchdog tunnel-e gir-karde ra restart نکرد'
ok 'watchdog active-but-stuck ra probe mikonad'

grep -q '*/../*' "$REPO_ROOT/rathole-manager/ratholenode" \
  || fail 'restore guard-e path traversal peyda nashod'
ok 'restore guard-e path traversal dar code vojood darad'

for f in rathole-manager/install-node.sh rathole-manager/update.sh rathole-manager/ratholenode; do
  grep -q 'NoNewPrivileges=yes' "$REPO_ROOT/$f" \
    || fail "hardening-e systemd dar $f peyda nashod"
done
ok 'unit-haye node systemd hardening-e paye darand'
