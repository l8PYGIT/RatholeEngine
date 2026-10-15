#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
export RATHOLENODE_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholenode"
ENV_FILE="$D/node.env"; SVC_FILE="$D/services.conf"; CLIENT_TOML="$D/client.toml"; FRP_CLI_TOML="$D/frpc.toml"
need_root(){ :; }; check_port_conflict(){ :; }
systemctl(){ printf '%s\n' "$*" >> "$D/systemctl"; }
install_frp(){ :; }; frp_systemd_unit(){ :; }
fail(){ echo "FAIL: $*" >&2; exit 1; }
printf 'SERVER=panel.example:443\nTUNNEL=frp\nFRP_REMOTE=panel.example:7000\nFRP_TOKEN=shared\nFRP_TRANSPORT=tcp\n' > "$ENV_FILE"
: > "$SVC_FILE"
main add-svc n1 token1 2087 12001
grep -qx 'n1|token1|2087|12001' "$SVC_FILE" || fail 'main dropped remote_port'
grep -qx 'remotePort = 12001' "$FRP_CLI_TOML" || fail 'apply did not regenerate FRP'
[ ! -f "$CLIENT_TOML" ] || fail 'FRP apply touched Rathole'
main add-svc n2 token2 2088 12002
main rm-svc n1
! grep -q 'name = "n1"' "$FRP_CLI_TOML" || fail 'removed FRP proxy remains'
grep -qx 'remotePort = 12002' "$FRP_CLI_TOML" || fail 'remaining mapping changed'
printf 'n2|token2|2088\n' > "$SVC_FILE"
cmd_frp_on panel.example:7000 shared tcp 12002
load_env
grep -qx 'remotePort = 12002' "$FRP_CLI_TOML" || fail 'fallback remote port missing'
cmd_apply
grep -qx 'remotePort = 12002' "$FRP_CLI_TOML" || fail 'fallback remote port lost on apply'
main add-svc n3 token3 2089 12003
grep -qx 'remotePort = 12002' "$FRP_CLI_TOML" || fail 'adding a second proxy changed first fallback mapping'
grep -qx 'disable --now rathole-client'  "$D/systemctl" || fail 'FRP left Rathole running'
printf '' > "$D/systemctl"
main restart
grep -qx 'restart frpc' "$D/systemctl" || fail 'restart did not select active FRP carrier'
! grep -qx 'disable --now frpc' "$D/systemctl" || fail 'restart disabled active FRP carrier'
cmd_plain_on panel.example:8880
grep -qx 'disable --now frpc' "$D/systemctl" || fail 'switch left FRP running'
for args in 'panel.example:7000 bad\"token tcp' 'panel.example:7000 shared badtransport' 'panel.example:99999 shared tcp' 'panel.example:7000 shared tcp 0'; do
  if (cmd_frp_on $args) >/dev/null 2>&1; then fail "accepted invalid FRP args: $args"; fi
done
if (main add-svc bad token 2088 70000) >/dev/null 2>&1; then fail 'accepted invalid remote port'; fi
install_frp(){ return 1; }
if (cmd_frp_on panel.example:7000 shared tcp) >/dev/null 2>&1; then fail 'ignored installer failure'; fi
export RATHOLECTL_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholectl"
FRP_TOML="$D/frps.toml"
gen_frp_server_toml 7000 shared tcp
grep -qx 'proxyBindAddr = "127.0.0.1"' "$FRP_TOML" || fail 'FRP proxy ports exposed publicly'
need_root(){ :; }; need_bin(){ :; }; print_backhaul_connect(){ :; }; ensure_state(){ :; }; regenerate(){ :; }; state_set(){ :; }; print_frp_connect(){ :; }
jq(){
  case "$*" in
    *backhaul_port*) echo 3080 ;;
    *frp_token*) echo oldtoken ;;
    *'select(.name=='*) if [[ "$*" == *'.transport'* ]]; then echo ws; elif [[ "$*" == *'length'* ]]; then echo 0; fi ;;
  esac
}
STATE="$D/state.json"; printf '{}' > "$STATE"
cmd_backhaul node n2 on
install_frp(){ :; }; frp_systemd_unit(){ :; }
cmd_frp on 7000
grep -qx 'auth.token = "oldtoken"' "$FRP_TOML" || fail 'FRP re-enable rotated existing token'
echo 'ok - FRP service mapping, apply, validation, transition and loopback binding'
