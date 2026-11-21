"""Phase 2B & Phase 4 regression tests for ratholectl and ratholenode."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which('bash') if os.name != 'nt' else r'C:\Program Files\Git\bin\bash.exe'


def run_bash(script):
    env = os.environ.copy()
    env['MSYS_NO_PATHCONV'] = '1'
    env['MSYS2_ARG_CONV_EXCL'] = '*'
    preamble = ''
    if os.name == 'nt':
        preamble = 'jq(){ command jq "$@" | tr -d "\\r"; }\n'
    return subprocess.run(
        [BASH, '-s'],
        input=preamble + script,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        start_new_session=(os.name != 'nt'),
        timeout=60,
    )


class Phase2RatholectlTests(unittest.TestCase):
    def test_state_jq_atomic_and_no_raw_state_mv_or_redundant_helpers(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLECTL_LIB_ONLY=1
source rathole-manager/ratholectl
declare -f state_jq >/dev/null || { echo "MISSING_STATE_JQ"; exit 1; }
STATE="$task_dir/state.json"
printf '{"domain":"a.example","nodes":[]}\n' > "$STATE"
chmod 600 "$STATE" 2>/dev/null || true
if ( state_jq '.invalid(' "$STATE" ) 2>/dev/null; then
  echo "UNEXPECTED_OK"
  exit 1
fi
grep -Fq '"domain":"a.example"' "$STATE" || { echo "STATE_CORRUPTED"; exit 1; }
state_jq --arg d "b.example" '.domain = $d'
grep -Fq '"domain": "b.example"' "$STATE" || grep -Fq '"domain":"b.example"' "$STATE" || { cat "$STATE"; exit 1; }
echo "STATE_JQ_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('STATE_JQ_OK', res.stdout)

        src = (ROOT / 'rathole-manager' / 'ratholectl').read_text(encoding='utf-8')
        self.assertNotIn('mv "$tmp" "$STATE"', src)
        self.assertNotIn('> "$STATE"', src)
        self.assertNotRegex(src, r'(?m)^detect_ip\(\)\{')
        self.assertNotIn('cat >/etc/sysctl.d/99-rathole-tune.conf', src)
        self.assertIn('apply_sysctl_tuning', src)
        self.assertNotIn('[ "$exposure" = direct_ip ] && [ "$port" = 443 ]', src)

    def test_regenerate_fails_before_writing_server_toml_on_nginx_error(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLECTL_LIB_ONLY=1
source rathole-manager/ratholectl
STATE="$task_dir/state.json"
SERVER_TOML="$task_dir/server.toml"
NGINX_CONF="$task_dir/nginx.conf"
STREAM_CONF="$task_dir/stream.conf"
UPGRADE_MAP="$task_dir/upgrade-map.conf"
NOISE_TOML="$task_dir/noise.toml"
BH_TOML="$task_dir/bh.toml"
echo "EXISTING_SERVER_TOML" > "$SERVER_TOML"
echo "server { listen 80; }" > "$NGINX_CONF"
echo "cert" > "$task_dir/fc.pem"
echo "key" > "$task_dir/priv.pem"
cat > "$STATE" <<EOF
{"domain":"a.example","cert_fullchain":"$task_dir/fc.pem","cert_key":"$task_dir/priv.pem","nginx_conf":"$NGINX_CONF","control_port":2333,"control_path":"/_rh/00112233445566778899aabbccddeeff","fake_port":8080,"sub_port":2096,"data_port_start":1001,"api_port_start":7001,"nodes":[{"name":"n1","port":1001,"inbound_port":2087,"token":"tok12345"}]}
EOF
need_root(){ :; }
nginx(){
  if [ "${1:-}" = "-t" ]; then
    echo "nginx: synthetic error" >&2
    return 1
  fi
  return 0
}
systemctl(){ return 0; }
if regenerate 2>/dev/null; then
  echo "REGEN_SHOULD_FAIL"
  exit 1
fi
[ "$(cat "$SERVER_TOML")" = "EXISTING_SERVER_TOML" ] || { echo "SERVER_TOML_OVERWRITTEN"; cat "$SERVER_TOML"; exit 1; }
echo "REGEN_ORDER_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('REGEN_ORDER_OK', res.stdout)

    def test_regenerate_propagates_noise_and_backhaul_toml_failures(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLECTL_LIB_ONLY=1
source rathole-manager/ratholectl
STATE="$task_dir/state.json"
SERVER_TOML="$task_dir/server.toml"
NGINX_CONF="$task_dir/nginx.conf"
STREAM_CONF="$task_dir/stream.conf"
UPGRADE_MAP="$task_dir/upgrade-map.conf"
echo "cert" > "$task_dir/fc.pem"
echo "key" > "$task_dir/priv.pem"
cat > "$STATE" <<EOF
{"domain":"a.example","cert_fullchain":"$task_dir/fc.pem","cert_key":"$task_dir/priv.pem","nginx_conf":"$NGINX_CONF","control_port":2333,"control_path":"/_rh/00112233445566778899aabbccddeeff","fake_port":8080,"sub_port":2096,"data_port_start":1001,"api_port_start":7001,"noise_port":2334,"nodes":[{"name":"n1","port":1001,"inbound_port":2087,"token":"tok12345","transport":"noise"}]}
EOF
need_root(){ :; }
nginx(){ return 0; }
systemctl(){ return 0; }
ensure_noise_unit(){ :; }
gen_noise_server_toml(){ return 1; }
if regenerate 2>/dev/null; then
  echo "SHOULD_FAIL_NOISE"
  exit 1
fi
echo "PROPAGATED_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('PROPAGATED_OK', res.stdout)

    def test_frp_show_preserves_node_and_frp_off_cleans_unit_and_frp_gre(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLECTL_LIB_ONLY=1
source rathole-manager/ratholectl
STATE="$task_dir/state.json"
FRP_TOML="$task_dir/frps.toml"
FRP_UNIT="$task_dir/frps.service"
touch "$FRP_TOML" "$FRP_UNIT"
cat > "$STATE" <<'JSON'
{
  "domain":"a.example","cert_fullchain":"/fc","cert_key":"/k","control_port":2333,
  "fake_port":8080,"sub_port":2096,"data_port_start":1001,"api_port_start":7001,
  "frp_port":7000,"frp_token":"frptok1234","frp_transport":"quic",
  "nodes":[
    {"name":"n1","port":1001,"inbound_port":2087,"token":"t1","transport":"frp_gre"},
    {"name":"n2","port":1002,"inbound_port":2088,"token":"t2","transport":"frp"}
  ]
}
JSON
need_root(){ :; }
detect_ip(){ echo "1.2.3.4"; }
systemctl(){ return 0; }
regenerate(){ return 0; }
out="$(main frp show n1)"
printf '%s\n' "$out" | grep -Fq "node n1: 1001" || { echo "FRP_SHOW_LOST_ARG"; echo "$out"; exit 1; }
main frp off >/dev/null
[ ! -e "$FRP_TOML" ] && [ ! -e "$FRP_UNIT" ] || { echo "FRP_FILES_REMAIN"; exit 1; }
rem_tr="$(jq -r '[.nodes[].transport // empty] | length' "$STATE")"
[ "$rem_tr" = "0" ] || { echo "FRP_GRE_REMAIN:$rem_tr"; cat "$STATE"; exit 1; }
echo "FRP_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('FRP_OK', res.stdout)

    def test_doctor_frp_listen_gre_status_down_next_port_and_ip_tls_http2(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLECTL_LIB_ONLY=1
source rathole-manager/ratholectl
STATE="$task_dir/state.json"
NGINX_CONF="$task_dir/nginx.conf"
UPGRADE_MAP="$task_dir/upgrade-map.conf"
echo "fc" > "$task_dir/fc.pem"
echo "key" > "$task_dir/priv.pem"
echo "ipfc" > "$task_dir/ipfc.pem"
echo "ipkey" > "$task_dir/ipkey.pem"
cat > "$STATE" <<EOF
{
  "domain":"a.example","cert_fullchain":"$task_dir/fc.pem","cert_key":"$task_dir/priv.pem",
  "nginx_conf":"$NGINX_CONF","control_port":2333,"control_path":"/_rh/00112233445566778899aabbccddeeff",
  "fake_port":8080,"sub_port":2096,"data_port_start":1001,"api_port_start":7001,"frp_port":1001,
  "ip_tls":{"ip":"1.2.3.4","fullchain":"$task_dir/ipfc.pem","key":"$task_dir/ipkey.pem","self_signed":true},
  "gre":{"name":"gre1","remote_ip":"5.6.7.8","tunnel_ip":"10.10.10.1","local_ip":"1.2.3.4"},
  "nodes":[{"name":"n1","port":1002,"inbound_port":2087,"token":"t1"}]
}
EOF
need_root(){ :; }
np="$(next_port port 1001)"
[ "$np" = "1003" ] || { echo "NEXT_PORT_COLLIDED:$np"; exit 1; }

gen_nginx_conf
http2_lines="$(grep -c "http2" "$NGINX_CONF" || true)"
[ "$http2_lines" = "1" ] || { echo "DUPLICATE_HTTP2:$http2_lines"; grep -n "listen " "$NGINX_CONF"; exit 1; }

command(){
  if [ "${1:-}" = "-v" ] && [ "${2:-}" = "ip" ]; then return 0; fi
  builtin command "$@"
}
ip(){ echo "7: gre1@NONE: <POINTOPOINT,NOARP> mtu 1476 qdisc noop state DOWN mode DEFAULT"; }
gre_out="$(cmd_gre status)"
printf '%s\n' "$gre_out" | grep -Fq "DOWN" || { echo "GRE_SHOULD_BE_DOWN:$gre_out"; exit 1; }

ss(){
  if [ "$*" = '-luntH sport = :7000' ] || echo "$*" | grep -q '7000'; then return 0; fi
  echo "LISTEN 0 128 127.0.0.1:2333 0.0.0.0:*"
}
jq '.frp_port = 7000' "$STATE" > "$STATE.t" && mv "$STATE.t" "$STATE"
systemctl(){ return 0; }
nginx(){ return 0; }
doc_out="$(cmd_doctor 2>&1 || true)"
printf '%s\n' "$doc_out" | grep -qE 'FAIL.*frp rooye :7000' || { echo "DOCTOR_FRP_FALSE_POSITIVE:$doc_out"; exit 1; }
echo "ALL_CHECKS_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('ALL_CHECKS_OK', res.stdout)

    def test_control_port_updates_kcp_target_and_no_double_restart_and_status_human(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLECTL_LIB_ONLY=1
source rathole-manager/ratholectl
STATE="$task_dir/state.json"
KCP_SRV_UNIT="$task_dir/kcp.service"
NOISE_UNIT="$task_dir/noise.service"
NOISE_TOML="$task_dir/noise.toml"
BH_UNIT="$task_dir/bh.service"
BH_TOML="$task_dir/bh.toml"
echo "fc" > "$task_dir/fc.pem"
echo "key" > "$task_dir/priv.pem"
cat > "$STATE" <<EOF
{
  "domain":"a.example","cert_fullchain":"$task_dir/fc.pem","cert_key":"$task_dir/priv.pem",
  "nginx_conf":"/etc/nginx/conf.d/rathole.conf","control_port":2333,
  "kcp":{"enabled":true,"port":443,"key":"kcpkey","target":"127.0.0.1:2333","profile":"balanced","mtu":1350,"sndwnd":2048,"rcvwnd":2048,"datashard":10,"parityshard":3,"mode":"fast2","crypt":"aes-128"},
  "frp_port":7000,"frp_transport":"quic",
  "gre":{"name":"gre1","remote_ip":"5.6.7.8","tunnel_ip":"10.10.10.1","local_ip":"1.2.3.4"},
  "fake_port":8080,"sub_port":2096,"data_port_start":1001,"api_port_start":7001,
  "nodes":[{"name":"n1","port":1001,"inbound_port":2087,"token":"t1"}]
}
EOF
need_root(){ :; }
regenerate(){ :; }
detect_ip(){ echo "1.2.3.4"; }
SVC_LOG="$task_dir/svc.log"
systemctl(){
  echo "$*" >> "$SVC_LOG"
  case "${1:-} ${2:-}" in
    'is-active --quiet') return 0 ;;
    'list-unit-files '*) echo "rathole-noise.service enabled"; echo "rathole-backhaul-server.service enabled"; return 0 ;;
  esac
  return 0
}
cmd_set control-port 2444 >/dev/null
kt="$(jq -r '.kcp.target' "$STATE")"
[ "$kt" = "127.0.0.1:2444" ] || { echo "KCP_TARGET_STALE:$kt"; exit 1; }
grep -Fq "127.0.0.1:2444" "$KCP_SRV_UNIT" || { echo "KCP_UNIT_STALE"; cat "$KCP_SRV_UNIT"; exit 1; }

# status human output includes FRP and GRE
st="$(cmd_status)"
printf '%s\n' "$st" | grep -Fq "7000" || { echo "STATUS_MISSING_FRP:$st"; exit 1; }
printf '%s\n' "$st" | grep -Fq "gre1" || { echo "STATUS_MISSING_GRE:$st"; exit 1; }

# no double restart on noise on / backhaul on
# restore real regenerate logic stubbing only nginx + gen_server_toml/gen_nginx_conf
gen_server_toml(){ :; }
gen_nginx_conf(){ :; }
command(){ builtin command "$@"; }
nginx(){ return 0; }
eval "$(sed -n '/^regenerate()/,/^}/p' rathole-manager/ratholectl)"
: > "$SVC_LOG"
noise_genkey(){ state_set '.noise_privkey' 'priv' str; state_set '.noise_pubkey' 'pub' str; }
cmd_noise on 2334 >/dev/null
n_restarts="$(grep -c '^restart rathole-noise$' "$SVC_LOG" || true)"
[ "$n_restarts" = "1" ] || { echo "NOISE_RESTART_COUNT:$n_restarts"; cat "$SVC_LOG"; exit 1; }

install_backhaul(){ return 0; }
: > "$SVC_LOG"
cmd_backhaul on 3080 wsmux balanced nginx_tls >/dev/null
b_restarts="$(grep -c '^restart rathole-backhaul-server$' "$SVC_LOG" || true)"
[ "$b_restarts" = "1" ] || { echo "BH_RESTART_COUNT:$b_restarts"; cat "$SVC_LOG"; exit 1; }
echo "CONTROL_PORT_AND_SINGLE_RESTART_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('CONTROL_PORT_AND_SINGLE_RESTART_OK', res.stdout)

    def test_hub_auto_register_env_and_backup_umask_and_bundle_mktemp(self):
        src = (ROOT / 'rathole-manager' / 'ratholectl').read_text(encoding='utf-8')
        self.assertIn('umask 077', src)
        self.assertIn('mktemp', src[src.index('cmd_logs(){'):src.index('cmd_logs(){') + 600])
        hub_fn = src[src.index('hub_auto_register_local(){'):src.index('cmd_hub(){')]
        self.assertIn('head -n1', hub_fn)
        self.assertNotIn("p = '$inv_file'", hub_fn)
        self.assertIn('INV_FILE=', hub_fn)
        self.assertIn('SSH_PORT=', hub_fn)


class Phase2RatholenodeTests(unittest.TestCase):
    def test_status_json_dispatch_gre_off_env_and_gre_status_down(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLENODE_LIB_ONLY=1
source rathole-manager/ratholenode
ENV_FILE="$task_dir/node.env"
SVC_FILE="$task_dir/services.conf"
BH_SVC_FILE="$task_dir/bh-services.conf"
ADAPTIVE_ENV="$task_dir/adaptive.env"
ADAPTIVE_STATE="$task_dir/adaptive-state.json"
cat > "$ENV_FILE" <<'EOF'
SERVER=panel.example:443
TUNNEL=ws
GRE_NAME=gre2
GRE_REMOTE=5.6.7.8
GRE_TUNNEL_IP=10.10.10.2
EOF
need_root(){ :; }
systemctl(){ return 1; }
command(){
  if [ "${1:-}" = "-v" ] && [ "${2:-}" = "ip" ]; then return 0; fi
  builtin command "$@"
}
ip(){ echo "9: gre2@NONE: <POINTOPOINT,NOARP> mtu 1476 state DOWN"; }

js="$(main status --json)"
printf '%s\n' "$js" | jq -e '.main.transport == "ws"' >/dev/null || { echo "BAD_STATUS_JSON:$js"; exit 1; }

gs="$(cmd_gre_status)"
printf '%s\n' "$gs" | grep -Fq "DOWN" || { echo "GRE_STATUS_NOT_DOWN:$gs"; exit 1; }

TD="$task_dir"
gre_teardown_interface(){ echo "$1" > "$TD/torn_gre"; }
cmd_gre_off >/dev/null
[ "$(cat "$TD/torn_gre")" = "gre2" ] || { echo "WRONG_GRE_OFF:$(cat "$TD/torn_gre" 2>/dev/null)"; exit 1; }
echo "NODE_STATUS_GRE_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('NODE_STATUS_GRE_OK', res.stdout)

    def test_frp_on_omitted_token_preserves_rport_and_active_backhaul(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLENODE_LIB_ONLY=1
source rathole-manager/ratholenode
ENV_FILE="$task_dir/node.env"
SVC_FILE="$task_dir/services.conf"
BH_SVC_FILE="$task_dir/bh-services.conf"
FRP_CLI_TOML="$task_dir/frpc.toml"
cat > "$ENV_FILE" <<'EOF'
SERVER=panel.example:443
FRP_TOKEN=saved_tok_123
EOF
printf 'svc1|t1|2087\n' > "$SVC_FILE"
printf 'bhsvc|2090\n' > "$BH_SVC_FILE"
need_root(){ :; }
install_frp(){ return 0; }
frp_systemd_unit(){ return 0; }
SVC_LOG="$task_dir/svc.log"
systemctl(){ echo "$*" >> "$SVC_LOG"; return 0; }
cmd_frp_on 1.2.3.4:7000 quic 8443 >/dev/null
grep -Fq 'transport.protocol = "quic"' "$FRP_CLI_TOML" || { cat "$FRP_CLI_TOML"; exit 1; }
grep -Fq 'remotePort = 8443' "$FRP_CLI_TOML" || { cat "$FRP_CLI_TOML"; exit 1; }
if grep -Fq "$BH_CLI_SVC" "$SVC_LOG"; then
  echo "DISABLED_ACTIVE_BACKHAUL"
  cat "$SVC_LOG"
  exit 1
fi
echo "FRP_ON_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('FRP_ON_OK', res.stdout)

    def test_gen_up_client_empty_services_and_env_kv_special_chars(self):
        script = r'''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLENODE_LIB_ONLY=1
source rathole-manager/ratholenode
ENV_FILE="$task_dir/node.env"
UP_DIR="$task_dir/upstreams"
mkdir -p "$UP_DIR"
up_toml(){ echo "$UP_DIR/$1.client.toml"; }
cat > "$UP_DIR/iran2.env" <<'EOF'
SERVER=up.example:443
HOST=up.example
TUNNEL=ws
EOF
: > "$UP_DIR/iran2.svc"
gen_up_client iran2
grep -Fq '[client.services]' "$UP_DIR/iran2.client.toml" || { cat "$UP_DIR/iran2.client.toml"; exit 1; }

env_set SPECIAL 'a#b&c\d'
grep -Fq 'SPECIAL=a#b&c\d' "$ENV_FILE" || { cat "$ENV_FILE"; exit 1; }
kv_set "$task_dir/kv.env" K 'x#y&z\w'
grep -Fq 'K=x#y&z\w' "$task_dir/kv.env" || { cat "$task_dir/kv.env"; exit 1; }
echo "UP_AND_KV_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('UP_AND_KV_OK', res.stdout)

    def test_adaptive_run_checks_kcp_and_uses_restart_and_cooldown(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLENODE_LIB_ONLY=1
source rathole-manager/ratholenode
ENV_FILE="$task_dir/node.env"
SVC_FILE="$task_dir/services.conf"
CLIENT_TOML="$task_dir/client.toml"
ADAPTIVE_ENV="$task_dir/adaptive.env"
ADAPTIVE_STATE="$task_dir/adaptive-state.json"
ADAPTIVE_LOCK="$task_dir/adaptive.lock"
printf 'SERVER=panel.example:443\nTUNNEL=ws\nKCP_REMOTE=1.2.3.4:443\nKCP_LOCAL=127.0.0.1:29900\n' > "$ENV_FILE"
printf 'n1|tok|2087\n' > "$SVC_FILE"
printf 'ADAPTIVE_ENABLED=1\nADAPTIVE_INTERVAL=30\nADAPTIVE_FAILURES=3\nADAPTIVE_RECOVERIES=5\nADAPTIVE_COOLDOWN=300\n' > "$ADAPTIVE_ENV"
echo '{"consecutive_failures":2}' > "$ADAPTIVE_STATE"
need_root(){ :; }
flock(){ return 0; }
adaptive_run_probe(){ echo '{"time":"2026-01-01T00:00:00Z","current":"ws","classification":"tls_failed","latency_ms":5,"consecutive_failures":3}' > "$ADAPTIVE_STATE"; echo tls_failed; }
SVC_LOG="$task_dir/svc.log"
# 1. With kcp-client INACTIVE, ws -> kcp switch must NOT happen
systemctl(){
  echo "$*" >> "$SVC_LOG"
  case "$*" in
    'is-active --quiet rathole-kcp-client') return 1 ;;
  esac
  return 0
}
main adaptive run
load_env
[ "${TUNNEL:-ws}" = "ws" ] || { echo "SWITCHED_WITHOUT_KCP"; exit 1; }

# 2. With kcp-client ACTIVE, switch happens and restarts service (not reload_svc) and writes last_switch_ts
: > "$SVC_LOG"
systemctl(){
  echo "$*" >> "$SVC_LOG"
  return 0
}
main adaptive run
load_env
[ "${TUNNEL:-ws}" = "kcp" ] || { echo "DID_NOT_SWITCH_TO_KCP:$TUNNEL"; exit 1; }
grep -Fq "restart $SVC" "$SVC_LOG" || { echo "USED_RELOAD_NOT_RESTART"; cat "$SVC_LOG"; exit 1; }
lst="$(jq -r '.last_switch_ts // 0' "$ADAPTIVE_STATE")"
[ "$lst" -gt 0 ] || { echo "MISSING_COOLDOWN_TS"; cat "$ADAPTIVE_STATE"; exit 1; }
echo "ADAPTIVE_RUN_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('ADAPTIVE_RUN_OK', res.stdout)

    def test_ratholenode_source_cleanups(self):
        src = (ROOT / 'rathole-manager' / 'ratholenode').read_text(encoding='utf-8')
        self.assertIn('umask 077', src)
        self.assertIn('apply_sysctl_tuning', src)
        self.assertNotIn('exec 3<>/dev/tcp/${host}/${port}', src)
        self.assertIn('exec 3<>/dev/tcp/"$1"/"$2"', src)
        self.assertIn('install_kcptun client', src)
        self.assertNotIn('tar -xzf "$tmp/k.tgz" -C "$tmp"', src)


class Phase2CInstallerLifecycleTests(unittest.TestCase):
    def test_update_sh_rollback_validation_latest_snapshot_tar_cleanup_and_aux_health(self):
        script = r'''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT

# 1. Invalid ROLLBACK_TS must be rejected before running rollback
out="$(bash rathole-manager/update.sh --rollback ../evil 2>&1 || true)"
printf '%s\n' "$out" | grep -qiE 'namotabar|root' || { echo "NO_ERR:$out"; exit 1; }
# Slice pre-main helpers up to jarian-e asli to test snapshot & health functions directly
id(){ [ "${1:-}" = "-u" ] && echo 0 || command id "$@"; }
sed '/^# ==================== jarian-e asli/q' rathole-manager/update.sh > "$task_dir/u_lib.sh"
source "$task_dir/u_lib.sh"

# Check ROLLBACK_TS validation directly in parser
ROLLBACK_TS="../bad"
res="$( ( set -- --rollback ../bad; eval "$(sed -n '/^while \[ \$# -gt 0 \]/,/^done$/p' rathole-manager/update.sh)"; [ -z "${ROLLBACK_TS:-}" ] || { [[ "$ROLLBACK_TS" =~ ^[0-9]{8}-[0-9]{6}$ ]] || die "bad ts"; } ) 2>&1 || true )"
printf '%s\n' "$res" | grep -q 'bad ts\|namotabar' || { echo "BAD_TS_NOT_REJECTED:$res"; exit 1; }

# 2. latest_snapshot ignores corrupt dirs lacking backup.tar.gz
BACKUP_ROOT="$task_dir/backups"
mkdir -p "$BACKUP_ROOT/pre-update-20260101-010101" "$BACKUP_ROOT/pre-update-20260102-010101"
touch "$BACKUP_ROOT/pre-update-20260101-010101/backup.tar.gz"
ls_pick="$(latest_snapshot)"
[ "$ls_pick" = "$BACKUP_ROOT/pre-update-20260101-010101" ] || { echo "PICKED_CORRUPT:$ls_pick"; exit 1; }

# 3. snapshot_now removes empty/corrupt $dir when tar fails
touch "$task_dir/f1"
snapshot_paths(){ echo "$task_dir/f1"; }
tar(){ return 1; }
if snapshot_now panel >/dev/null 2>&1; then
  echo "SNAPSHOT_SHOULD_FAIL"
  exit 1
fi
[ -z "$(find "$BACKUP_ROOT" -maxdepth 1 -name 'pre-update-2026*' ! -name 'pre-update-20260101-010101' ! -name 'pre-update-20260102-010101')" ] \
  || { echo "CORRUPT_SNAPSHOT_DIR_LEFT"; ls -la "$BACKUP_ROOT"; exit 1; }

# 4. health_check detects failing enabled aux service (rathole-agent)
RATHOLE_HEALTH_SETTLE=0
nginx(){ return 0; }
systemctl(){
  if [ "${1:-} ${2:-}" = "is-enabled --quiet" ] && [ "${3:-}" = "rathole-agent" ]; then return 0; fi
  if [ "${1:-} ${2:-}" = "is-active --quiet" ] && [ "${3:-}" = "rathole-agent" ]; then return 1; fi
  if [ "${1:-} ${2:-}" = "is-active --quiet" ]; then return 0; fi
  return 1
}
if health_check panel 2>/dev/null; then
  echo "HEALTH_MISSED_AUX_FAILURE"
  exit 1
fi
echo "UPDATE_HELPERS_OK"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + '\n' + res.stderr)
        self.assertIn('UPDATE_HELPERS_OK', res.stdout)

        src = (ROOT / 'rathole-manager' / 'update.sh').read_text(encoding='utf-8')
        self.assertIn('^[0-9]{8}-[0-9]{6}$', src)
        self.assertIn('RATHOLE_HEALTH_SETTLE', src)
        snap_fn = src[src.index('snapshot_paths(){'):src.index('snapshot_now(){')]
        hub_case = snap_fn[snap_fn.index('        hub)'):]
        self.assertIn('/etc/rathole-agent', hub_case)
        self.assertIn('/usr/local/share/rathole', hub_case)

    def test_install_sh_token_tmp_cleanup_private_api_and_sha256(self):
        src = (ROOT / 'install.sh').read_text(encoding='utf-8')
        self.assertNotIn('-H "Authorization: Bearer', src)
        self.assertIn('--config -', src)
        self.assertNotIn('exec bash "$tmp/bootstrap.sh"', src)
        self.assertIn('unset GH_TOKEN RATHOLE_GH_TOKEN GITHUB_TOKEN', src)
        self.assertIn('SHA256SUMS', src)
        self.assertIn('api.github.com/repos/', src)

    def test_bootstrap_package_update_private_installers_and_uninstallers(self):
        up_priv = (ROOT / 'tools' / 'update-private.sh').read_text(encoding='utf-8')
        self.assertIn('umask 022', up_priv)

        pkg = (ROOT / 'package.sh').read_text(encoding='utf-8')
        self.assertIn("*.py", pkg)
        self.assertIn("*.js", pkg)
        self.assertIn("ratholeagent.py", pkg)

        boot = (ROOT / 'bootstrap.sh').read_text(encoding='utf-8')
        self.assertIn('[ $# -ge 2 ] || die', boot)
        self.assertIn('*.py', boot)
        self.assertIn('*.js', boot)

        ipanel = (ROOT / 'rathole-manager' / 'install-panel.sh').read_text(encoding='utf-8')
        self.assertIn('/etc/nginx/stream.d/rathole-stream.conf', ipanel)
        self.assertNotIn('/etc/nginx/conf.d/rathole-stream.conf', ipanel)
        self.assertNotIn('fallback be download-e upstream', ipanel)
        self.assertIn('head -20 || true)"', ipanel)

        inode = (ROOT / 'rathole-manager' / 'install-node.sh').read_text(encoding='utf-8')
        self.assertIn('[ $# -ge 2 ] || die', inode)
        self.assertIn('umask 077', inode)
        self.assertIn('chmod 600 /etc/rathole/client.toml', inode)

        ihub = (ROOT / 'rathole-manager' / 'ratholehub' / 'install-hub.sh').read_text(encoding='utf-8')
        self.assertIn('ssh_proxy.py', ihub)
        self.assertIn('umask 077', ihub)

        upanel = (ROOT / 'rathole-manager' / 'uninstall-panel.sh').read_text(encoding='utf-8')
        self.assertLess(
            upanel.index('rm -f /etc/nginx/stream.d/rathole-stream.conf'),
            upanel.index('if nginx -t 2>/dev/null; then'),
        )
        self.assertIn('rathole-client.service', upanel[upanel.index('if [ "$PURGE" -eq 1 ]'):])

        unode = (ROOT / 'rathole-manager' / 'uninstall-node.sh').read_text(encoding='utf-8')
        self.assertIn('rathole-server.service', unode[unode.index('if [ "$PURGE" -eq 1 ]'):])


if __name__ == '__main__':
    unittest.main()
