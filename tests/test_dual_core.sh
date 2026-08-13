#!/usr/bin/env bash
# test_dual_core.sh — C1: lane-haye rathole + backhaul rooye yek node
set -euo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/test-dual-core.XXXXXX")"
trap 'rm -rf "$ROOT"' EXIT

export RATHOLENODE_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholenode"

ENV_FILE="$ROOT/node.env"
SVC_FILE="$ROOT/services.conf"
BH_SVC_FILE="$ROOT/bh-services.conf"
CLIENT_TOML="$ROOT/client.toml"
BH_TOML="$ROOT/backhaul-client.toml"
BH_CLI_UNIT="$ROOT/rathole-backhaul-client.service"
CALLS="$ROOT/systemctl.calls"

printf 'SERVER=panel.example:443\nTUNNEL=ws\n' > "$ENV_FILE"
printf 'rathole01|rt-token|1101\n' > "$SVC_FILE"
printf 'backhaul01|bh-token|1201\n' > "$BH_SVC_FILE"

need_root(){ :; }
install_backhaul(){ :; }
systemctl(){ printf '%s\n' "$*" >> "$CALLS"; return 0; }

gen_client
env_set BH_REMOTE_ADDR panel.example:443
env_set BH_TOKEN bh-token
env_set BH_TRANSPORT wssmux
env_set BH_PROFILE balanced
gen_backhaul_client_toml

grep -qF 'local_addr = "127.0.0.1:1101"' "$CLIENT_TOML" || fail 'service-e rathole dar client.toml nist'
grep -qF '# lane-service: backhaul01 -> 127.0.0.1:1201' "$BH_TOML" || fail 'registry-e backhaul dar config-e backhaul nist'
ok 'do registry-e joda TOML-haye lane-haye rathole/backhaul ra sakhte-and'

: > "$CALLS"
cmd_backhaul on panel.example bh-token wssmux balanced

grep -qx 'enable rathole-backhaul-client' "$CALLS" || fail 'backhaul client enable nashod'
grep -qx 'restart rathole-backhaul-client' "$CALLS" || fail 'backhaul client restart nashod'
grep -qx 'enable rathole-client' "$CALLS" || fail 'rathole lane hamzamam enable nashod'
! grep -qx 'disable --now rathole-client' "$CALLS" || fail 'backhaul nabayad rathole-client ra disable konad'
ok 'backhaul on har do lane ra negah midarad va rathole-client ra disable nemikonad'

echo "---"
echo "dual-core C1 PASS"
