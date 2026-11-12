#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export RATHOLENODE_LIB_ONLY=1
source "$ROOT/rathole-manager/ratholenode"
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
UP_DIR="$D/upstreams"; ENV_FILE="$D/node.env"; mkdir -p "$UP_DIR"
printf 'SERVER=panel.example:443\n' > "$ENV_FILE"; cp "$ENV_FILE" "$D/original"
need_root(){ :; }
ensure_client_template(){ return 0; }
gen_up_client(){ return "${GEN_RC:-0}"; }
systemctl(){ echo "$*" >> "$D/systemctl"; return 1; }
for action in up_apply up_restart; do
 : > "$D/systemctl"
 if (GEN_RC=1; "$action" x); then echo 'FAIL - config generation failure hidden'; exit 1; fi
 [ ! -s "$D/systemctl" ]
 if "$action" x; then echo 'FAIL - systemd failure hidden'; exit 1; fi
done
echo 'ok - upstream generation/start/restart errors propagate'
printf 'keep\n' > "$D/outside.env"
for sub in rm apply restart add-svc rm-svc status ws; do
 if (cmd_upstream "$sub" ../outside n1 token123 2087) >/dev/null 2>&1; then echo 'FAIL - invalid upstream id accepted'; exit 1; fi
 [ "$(cat "$D/outside.env")" = keep ]
done
for server in panel.example:0 panel.example:65536 $'panel.example\nTUNNEL=plain'; do
 if (cmd_set_main "$server") >/dev/null 2>&1; then echo 'FAIL - invalid server accepted'; exit 1; fi
 cmp "$ENV_FILE" "$D/original"
done
echo 'ok - upstream path traversal and invalid endpoint rejected before mutation'
