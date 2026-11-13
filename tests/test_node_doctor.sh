#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export RATHOLENODE_LIB_ONLY=1
source "$ROOT/rathole-manager/ratholenode"
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
ENV_FILE="$D/node.env"; SVC_FILE="$D/services.conf"; UP_DIR="$D/upstreams"
printf 'SERVER=panel.example:443\n' > "$ENV_FILE"
printf 'n1|token|2087\n' > "$SVC_FILE"
command(){
 if [ "$*" = '-v /usr/local/bin/rathole' ]; then return 0; fi
 builtin command "$@"
}
rathole_supports_ws_path(){ return 0; }
node_backend_ready(){ return "${BACKEND_RC:-0}"; }
systemctl(){ return 0; }
cmd_doctor > "$D/good"
grep -q 'FAIL=0' "$D/good"
if (BACKEND_RC=1; cmd_doctor) > "$D/bad"; then echo 'FAIL - missing backend reported success'; exit 1; fi
grep -q 'FAIL=1' "$D/bad"
echo 'ok - doctor returns success when healthy and fails on missing TCP backend'
