#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export RATHOLENODE_LIB_ONLY=1
source "$ROOT/rathole-manager/ratholenode"
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
ENV_FILE="$D/node.env"; SVC_FILE="$D/services.conf"; CLIENT_TOML="$D/client.toml"
ADAPTIVE_ENV="$D/adaptive.env"; ADAPTIVE_STATE="$D/state.json"; ADAPTIVE_LOCK="$D/adaptive.lock"
printf 'SERVER=panel.example:443\nTUNNEL=ws\n' > "$ENV_FILE"
printf 'ADAPTIVE_ENABLED=1\nADAPTIVE_FAILURES=1\nADAPTIVE_RECOVERIES=2\nADAPTIVE_COOLDOWN=300\n' > "$ADAPTIVE_ENV"
printf 'n1|token|2087\n' > "$SVC_FILE"
need_root(){ :; }
adaptive_probe_ws_tls(){ echo "${WS_CLASS:-tcp_refused}:1"; }
adaptive_probe_kcp(){ echo "${KCP_CLASS:-healthy}:1"; }
gen_client(){
 load_env
 if [ "${TUNNEL:-ws}" = kcp ] && [ "${FAIL_KCP:-0}" = 1 ]; then return 1; fi
 printf '%s\n' "${TUNNEL:-ws}" > "$CLIENT_TOML"
}
reload_svc(){ printf '%s\n' "${TUNNEL:-ws}" >> "$D/reloads"; }
cmd_adaptive run
grep -qx 'TUNNEL=kcp' "$ENV_FILE"
python3 - "$ADAPTIVE_STATE" <<'PY_STATE'
import json,sys
d=json.load(open(sys.argv[1]));assert d['last_switch_epoch'] > 0;assert d['consecutive_failures']==0
PY_STATE
WS_CLASS=healthy
cmd_adaptive run
grep -qx 'TUNNEL=kcp' "$ENV_FILE"
adaptive_save_state '{"last_switch_epoch":0}'
cmd_adaptive run
grep -qx 'TUNNEL=ws' "$ENV_FILE"
echo 'ok - enabled config survives reload, failover, cooldown and recovery thresholds'
adaptive_save_state '{"last_switch_epoch":0}'
WS_CLASS=tcp_refused; KCP_CLASS=dead
if cmd_adaptive run; then echo 'FAIL - unhealthy candidate accepted'; exit 1; fi
grep -qx 'TUNNEL=ws' "$ENV_FILE"
KCP_CLASS=healthy; FAIL_KCP=1
if cmd_adaptive run; then echo 'FAIL - generation failure hidden'; exit 1; fi
grep -qx 'TUNNEL=ws' "$ENV_FILE"
grep -qx ws "$CLIENT_TOML"
echo 'ok - dead alternate rejected and failed switch rolls back'
printf 'ADAPTIVE_ENABLED=$(touch %s)\n' "$D/pwned" > "$ADAPTIVE_ENV"
if cmd_adaptive run; then echo 'FAIL - invalid adaptive env accepted'; exit 1; fi
[ ! -e "$D/pwned" ]
echo 'ok - adaptive env is parsed as data'

# Retain real timeout exit classification.
(
 source "$ROOT/rathole-manager/ratholenode"
 timeout(){ return 124; }
 result="$(adaptive_probe_tcp 127.0.0.1 1234 || true)"
 [[ "$result" = tcp_timeout:* ]]
)
echo 'ok - TCP timeout is reported as timeout'

(
 printf 'SERVER=panel.example\nTUNNEL=ws\n' > "$ENV_FILE"
 printf 'ADAPTIVE_ENABLED=1\n' > "$ADAPTIVE_ENV"
 adaptive_probe_ws_tls(){ [ "$2" = 443 ] || return 1; echo healthy:1; }
 result="$(adaptive_run_probe)"
 [ "$result" = healthy ]
)
echo 'ok - adaptive probe uses the same default TLS port as the client'
