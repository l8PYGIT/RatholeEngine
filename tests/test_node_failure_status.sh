#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
export RATHOLENODE_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholenode"
ENV_FILE="$D/node.env"; SVC_FILE="$D/services.conf"; CLIENT_TOML="$D/client.toml"
printf 'SERVER=panel.example:443\n' > "$ENV_FILE"
printf 'n1|token|2087\n' > "$SVC_FILE"
need_root(){ :; }; check_port_conflict(){ :; }
fail(){ echo "FAIL: $*" >&2; exit 1; }
systemctl(){ case "$1" in restart|start|is-active) return 1;; *) return 0;; esac; }
for action in restart_svc reload_svc cmd_apply 'cmd_plain_on panel.example:8880' cmd_plain_off 'cmd_noise_on panel.example:2334 AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA' cmd_noise_off 'cmd_set_main panel.example:443'; do
  if (eval "$action") >/dev/null 2>&1; then fail "ignored service failure: $action"; fi
done
systemctl(){ :; }
gen_client(){ return 1; }
for action in cmd_apply 'cmd_plain_on panel.example:8880' cmd_plain_off 'cmd_set_main panel.example:443'; do
  if (eval "$action") >/dev/null 2>&1; then fail "ignored config failure: $action"; fi
done
if ! (
  printf 'TUNNEL=frp\n' >> "$ENV_FILE"
  cmd_apply(){ return 0; }
  start_rathole_lane_if_present
) >/dev/null 2>&1; then fail 'Backhaul helper did not preserve active FRP lane'; fi
sed -i '/^TUNNEL=/d' "$ENV_FILE"
gen_client(){ :; }; BH_SVC_FILE="$D/bh-services.conf"
printf 'BH_REMOTE_ADDR=panel.example:443\nBH_TOKEN=shared\n' >> "$ENV_FILE"
gen_backhaul_client_toml(){ return 1; }
if (cmd_bh_add_svc bh1 shared 2088) >/dev/null 2>&1; then fail 'ignored Backhaul service config failure'; fi
gen_backhaul_client_toml(){ :; }; gen_backhaul_client_unit(){ :; }
install_backhaul(){ return 1; }
if (cmd_backhaul on panel.example shared) >/dev/null 2>&1; then fail 'ignored Backhaul install failure'; fi
install_backhaul(){ :; }
systemctl(){ case "$1" in restart|start|is-active) return 1;; *) return 0;; esac; }
if (cmd_backhaul on panel.example shared) >/dev/null 2>&1; then fail 'ignored Backhaul start failure'; fi
export RATHOLECTL_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholectl"
need_root(){ :; }; need_bin(){ :; }; ensure_state(){ :; }; state_set(){ :; }; ensure_backhaul_unit(){ :; }
STATE="$D/state.json"; printf '{}' > "$STATE"
jq(){ echo shared; }; gen_backhaul_server_toml(){ :; }; regenerate(){ :; }; print_backhaul_connect(){ :; }
systemctl(){ case "$1" in restart) return 1;; *) return 0;; esac; }
install_backhaul(){ :; }
if (cmd_backhaul on 3080 wsmux balanced nginx_tls) >/dev/null 2>&1; then fail 'ignored Backhaul server start failure'; fi
echo 'ok - config and service failures propagate from node actions'
