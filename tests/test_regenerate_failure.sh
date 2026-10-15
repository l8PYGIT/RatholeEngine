#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export RATHOLECTL_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholectl"
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
STATE="$D/state.json"; NGINX_CONF="$D/http.conf"; STREAM_CONF="$D/stream.conf"; SERVER_TOML="$D/server.toml"
printf '{}\n' > "$STATE"; printf 'good\n' > "$NGINX_CONF"
need_root(){ :; }; log(){ :; }; err(){ :; }
jq(){ :; }
gen_server_toml(){ printf 'server\n' > "$SERVER_TOML"; }
gen_nginx_conf(){ printf 'invalid\n' > "$NGINX_CONF"; }
NG_CALL=0
nginx(){ NG_CALL=$((NG_CALL+1)); [ "$NG_CALL" -ne 2 ]; }
systemctl(){ printf '%s\n' "$*" >> "$D/systemctl"; }
if regenerate; then echo 'FAIL: invalid nginx config reported success' >&2; exit 1; fi
grep -qx good "$NGINX_CONF" || { echo 'FAIL: good config was not restored' >&2; exit 1; }
if [ -f "$D/systemctl" ] && grep -q '^start ' "$D/systemctl"; then echo 'FAIL: continued after validation failed' >&2; exit 1; fi
nginx(){ return 0; }
systemctl(){ return 1; }
if regenerate; then echo 'FAIL: reload and restart failure reported success' >&2; exit 1; fi
echo 'ok - regenerate validation and service failures propagate'
regenerate(){ return 1; }
ensure_state(){ :; }; need_bin(){ :; }; state_set(){ :; }; warn(){ :; }; ufw(){ :; }
print_plain_connect(){ echo BAD_SUCCESS; }
if cmd_plain on 8880; then echo 'FAIL: plain_on swallowed regenerate failure' >&2; exit 1; fi
echo 'ok - caller stops when regeneration fails'
