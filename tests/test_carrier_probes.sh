#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
fail(){ echo "FAIL: $*" >&2; exit 1; }

export RATHOLENODE_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholenode"
need_root(){ :; }
ip(){ [ "$1" = link ] && [ "$2" = show ] && [ "$3" = gre1 ]; }
ping(){ printf '%s\n' "$*" > "$D/ping-args"; return "${PING_RC:-0}"; }
cmd_gre probe 10.10.10.1 gre1 || fail 'reachable GRE peer rejected'
grep -q -- '-I gre1' "$D/ping-args" || fail 'GRE probe did not use tunnel interface'
if (PING_RC=1; cmd_gre probe 10.10.10.1 gre1) >/dev/null 2>&1; then fail 'unreachable GRE peer accepted'; fi

export RATHOLECTL_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholectl"
need_root(){ :; }; need_bin(){ :; }; ensure_state(){ :; }; sleep(){ :; }
STATE="$D/state.json"
printf '{"nodes":[{"name":"n1","port":21001}]}' > "$STATE"
ss(){ printf '%s\n' "LISTEN 0 4096 127.0.0.1:21001 0.0.0.0:* users:((\"${SS_OWNER:-frps}\",pid=123,fd=7))"; }
cmd_frp ready n1 || fail 'registered FRP proxy rejected'
if (SS_OWNER=rathole-server; cmd_frp ready n1) >/dev/null 2>&1; then fail 'non-FRP listener accepted'; fi
echo 'ok - GRE peer probe and FRP proxy readiness'
