#!/usr/bin/env bash
set -euo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

find_py(){
  local c
  for c in python3 python python.exe; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import tomllib' >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  return 1
}
PY_BIN="$(find_py)" || fail "Python 3.11+ with tomllib is required"

# ---- Stubs directory on PATH ----
BIN="$D/bin"
mkdir -p "$BIN"
STUB_LOG="$D/stub.log"
: > "$STUB_LOG"

cat > "$BIN/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >> "${TEST_STUB_LOG:?}"
case "${1:-}" in
  is-active|is-enabled) exit 0 ;;
  list-unit-files) exit 0 ;;
esac
exit 0
EOF
cat > "$BIN/nginx" <<'EOF'
#!/usr/bin/env bash
echo "nginx $*" >> "${TEST_STUB_LOG:?}"
exit 0
EOF
cat > "$BIN/sysctl" <<'EOF'
#!/usr/bin/env bash
echo "sysctl $*" >> "${TEST_STUB_LOG:?}"
if [ "${1:-}" = "-n" ] && [ "${2:-}" = "net.ipv4.tcp_congestion_control" ]; then
  echo "bbr"
fi
exit 0
EOF
cat > "$BIN/modprobe" <<'EOF'
#!/usr/bin/env bash
echo "modprobe $*" >> "${TEST_STUB_LOG:?}"
exit 0
EOF
cat > "$BIN/ip" <<'EOF'
#!/usr/bin/env bash
echo "ip $*" >> "${TEST_STUB_LOG:?}"
args=" $* "
if [[ "$args" == *" route get "* ]]; then
  dst=""
  for a in "$@"; do dst="$a"; done
  if [[ "$dst" == *:* ]]; then
    echo "$dst dev eth0 src 2001:db8::10 uid 0"
  else
    echo "$dst dev eth0 src 198.51.100.10 uid 0"
  fi
  exit 0
fi
if [[ "$args" == *" link show "* ]]; then
  echo "3: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq state UP"
  exit 0
fi
if [[ "$args" == *" addr show "* ]]; then
  echo "2: eth0    inet 198.51.100.10/24 scope global eth0"
  echo "2: eth0    inet6 2001:db8::10/64 scope global"
  exit 0
fi
exit 0
EOF
cat > "$BIN/iptables" <<'EOF'
#!/usr/bin/env bash
echo "iptables $*" >> "${TEST_STUB_LOG:?}"
if [ "${1:-}" = "-t" ] && [ "${3:-}" = "-S" ]; then
  if [ "${2:-}" = "filter" ] && [ "${4:-}" = "INPUT" ]; then
    echo '-A INPUT -s 203.0.113.5/32 -p 47 -m comment --comment "rathole-gre-gre1" -j ACCEPT'
    echo '-A INPUT -s 203.0.113.9/32 -p 47 -m comment --comment "rathole-gre-gre10" -j ACCEPT'
  elif [ "${2:-}" = "mangle" ] && [ "${4:-}" = "OUTPUT" ]; then
    echo '-A OUTPUT -o gre1 -p tcp -m tcp --tcp-flags SYN,RST SYN -m comment --comment "rathole-gre-gre1" -j TCPMSS --clamp-mss-to-pmtu'
  fi
  exit 0
fi
if [ "${1:-}" = "-C" ] || [ "${3:-}" = "-C" ]; then
  exit 1
fi
exit 0
EOF
cat > "$BIN/ip6tables" <<'EOF'
#!/usr/bin/env bash
echo "ip6tables $*" >> "${TEST_STUB_LOG:?}"
if [ "${1:-}" = "-C" ] || [ "${3:-}" = "-C" ]; then
  exit 1
fi
exit 0
EOF
cat > "$BIN/ping" <<'EOF'
#!/usr/bin/env bash
echo "ping $*" >> "${TEST_STUB_LOG:?}"
sz=0
prev=""
for a in "$@"; do
  if [ "$prev" = "-s" ]; then sz="$a"; break; fi
  prev="$a"
done
# Simulate path MTU 1380 -> max IPv4 payload 1352
if [ "$sz" -le 1352 ]; then
  exit 0
fi
exit 1
EOF
chmod +x "$BIN"/*
export TEST_STUB_LOG="$STUB_LOG"
export PATH="$BIN:$PATH"

# ---- Load ratholectl in library mode ----
export RATHOLECTL_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholectl"
need_root(){ :; }

# 1) sysctl ip_local_port_range & ip_local_reserved_ports
export RTH_SYSCTL_FILE="$D/99-rathole-tune.conf"
export RTH_RESERVED_SYSCTL_FILE="$D/99-rathole-reserved-ports.conf"
apply_sysctl_tuning 7000 2333 7000 1001 8089 badport 70000
grep -qx 'net.ipv4.ip_local_port_range=32768 60999' "$RTH_SYSCTL_FILE" || fail "ip_local_port_range was not 32768 60999"
! grep -q '1024 65535' "$RTH_SYSCTL_FILE" || fail "unsafe 1024 65535 still present"
grep -qx 'net.ipv4.ip_local_reserved_ports=1001,2333,7000,8089' "$RTH_RESERVED_SYSCTL_FILE" || fail "reserved ports CSV mismatch"
ok "sysctl ip_local_port_range=32768 60999 and sorted reserved ports"

# 2) GRE IPv4 + key + OUTPUT/FORWARD MSS clamp + Proto 47 + teardown + Auto-MTU
: > "$STUB_LOG"
gre_setup_interface gre1 198.51.100.10 203.0.113.5 10.10.10.1 41007 0
grep -q 'ip link add gre1 type gre remote 203.0.113.5 local 198.51.100.10 ttl 255 key 41007' "$STUB_LOG" || fail "gre IPv4 key setup failed"
grep -q 'ip link set gre1 mtu 1472 up' "$STUB_LOG" || fail "gre IPv4 key MTU should be 1472"
grep -q 'iptables -I INPUT 1 -p 47 -s 203.0.113.5 -m comment --comment rathole-gre-gre1 -j ACCEPT' "$STUB_LOG" || fail "proto 47 ACCEPT rule missing"
grep -q 'iptables -t mangle -I OUTPUT 1 -p tcp --tcp-flags SYN,RST SYN -o gre1 -m comment --comment rathole-gre-gre1 -j TCPMSS --clamp-mss-to-pmtu' "$STUB_LOG" || fail "mangle OUTPUT clamp missing"
grep -q 'iptables -t mangle -I FORWARD 1 -p tcp --tcp-flags SYN,RST SYN -o gre1 -m comment --comment rathole-gre-gre1 -j TCPMSS --clamp-mss-to-pmtu' "$STUB_LOG" || fail "mangle FORWARD clamp missing"

: > "$STUB_LOG"
gre_probe_mtu gre1 10.10.10.2
grep -q 'ip link set gre1 mtu 1380' "$STUB_LOG" || fail "gre_probe_mtu did not converge to 1380"

: > "$STUB_LOG"
gre_teardown_interface gre1
grep -q 'iptables -t filter -D INPUT -s 203.0.113.5/32 -p 47 -m comment --comment rathole-gre-gre1 -j ACCEPT' "$STUB_LOG" || fail "teardown did not delete INPUT rule"
! grep -q -- 'rathole-gre-gre10' "$STUB_LOG" || fail "teardown wrongly deleted sibling gre10 rule"
! grep -q -- '203\.0\.113\.9' "$STUB_LOG" || fail "teardown wrongly matched sibling gre10 rule"
grep -q 'iptables -t mangle -D OUTPUT -o gre1' "$STUB_LOG" || fail "teardown did not delete OUTPUT rule"

: > "$STUB_LOG"
gre_setup_interface gre6 2001:db8::10 2001:db8::20 fd00::1 99 0
grep -q 'ip link add gre6 type ip6gre remote 2001:db8::20 local 2001:db8::10 encaplimit none hoplimit 255 key 99' "$STUB_LOG" || fail "ip6gre setup failed"
grep -q 'ip addr add fd00::1/126 dev gre6' "$STUB_LOG" || fail "ip6gre /126 addr missing"
grep -q 'ip6tables -I INPUT 1 -p 47 -s 2001:db8::20' "$STUB_LOG" || fail "ip6tables proto 47 rule missing"
ok "GRE IPv4/ip6gre, key, proto47, OUTPUT+FORWARD clamp, teardown, and Auto-MTU"

# 3) Game/SNI opt-in PROXY protocol & FRP proxy-protocol
STATE="$D/state.json"
SERVER_TOML="$D/server.toml"
NGINX_CONF="$D/rathole.conf"
STREAM_CONF="$D/rathole-stream.conf"
FAKE_FC="$D/fullchain.pem"
FAKE_KEY="$D/privkey.pem"
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$FAKE_KEY" -out "$FAKE_FC" -days 5 -subj "/CN=panel.example.com" >/dev/null 2>&1
cat > "$STATE" <<JSON
{
  "domain": "panel.example.com",
  "cert_fullchain": "$FAKE_FC",
  "cert_key": "$FAKE_KEY",
  "nginx_conf": "$NGINX_CONF",
  "control_port": 2333,
  "fake_port": 8080,
  "sub_port": 2096,
  "internal_port": 8443,
  "data_port_start": 1001,
  "api_port_start": 7001,
  "nodes": [
    {"name": "game1", "port": 1001, "inbound_port": 443, "token": "short", "sni": "game.example.com"}
  ]
}
JSON
ensure_stream_include(){ :; }
regenerate >/dev/null 2>&1
! grep -q 'proxy_protocol' "$STREAM_CONF" || fail "game proxy_protocol must be off by default"
! grep -q 'proxy_protocol' "$NGINX_CONF" || fail "nginx proxy_protocol must be off by default"

cmd_game proxy-protocol on >/dev/null 2>&1
grep -q 'proxy_protocol on;' "$STREAM_CONF" || fail "STREAM_CONF missing proxy_protocol on;"
grep -qE 'listen 127\.0\.0\.1:8443 ssl http2 proxy_protocol;' "$NGINX_CONF" || fail "NGINX_CONF listener missing proxy_protocol"
grep -q 'real_ip_header proxy_protocol;' "$NGINX_CONF" || fail "NGINX_CONF missing real_ip_header proxy_protocol"

cmd_game proxy-protocol off >/dev/null 2>&1
! grep -q 'proxy_protocol' "$STREAM_CONF" || fail "STREAM_CONF still has proxy_protocol after off"
! grep -q 'real_ip_header' "$NGINX_CONF" || fail "NGINX_CONF still has real_ip_header after off"
ok "Game/SNI opt-in PROXY protocol toggle"

# 4) Doctor checks (cert expiry <14d, weak token, actionable hints)
days_left="$(rth_cert_days_left "$FAKE_FC")"
[ "$days_left" -ge 0 ] && [ "$days_left" -le 5 ] || fail "unexpected cert days_left: $days_left"
doc_out="$(cmd_doctor 2>&1 || true)"
echo "$doc_out" | grep -q 'nazdik be enghza' || fail "doctor missed cert expiry warning"
echo "$doc_out" | grep -q 'rah-e hal:' || fail "doctor missed remediation hint"
echo "$doc_out" | grep -q 'token-e node "game1" kootah ast' || fail "doctor missed short token warning"
ok "Doctor cert expiry, weak token, and remediation hints"

# 5) Panel restore --test dry-run & traversal rejection & Offsite hook argv safety
TAR_ROOT="$D/tarroot"
mkdir -p "$TAR_ROOT/etc/rathole-manager"
cp "$STATE" "$TAR_ROOT/etc/rathole-manager/state.json"
BAK_PANEL="$D/panel-bak.tar.gz"
tar -czf "$BAK_PANEL" -C "$TAR_ROOT" etc/rathole-manager/state.json
ORIG_SUM="$(sha256sum "$STATE" | cut -d' ' -f1)"
jq '.domain = "changed-in-live.example.com"' "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
LIVE_SUM="$(sha256sum "$STATE" | cut -d' ' -f1)"
dry_out="$(cmd_restore --test "$BAK_PANEL" 2>&1)"
echo "$dry_out" | grep -q 'DRY-RUN' || fail "restore --test missing DRY-RUN banner"
echo "$dry_out" | grep -q 'panel.example.com' || fail "restore --test did not preview backup domain"
AFTER_SUM="$(sha256sum "$STATE" | cut -d' ' -f1)"
[ "$LIVE_SUM" = "$AFTER_SUM" ] || fail "restore --test modified live state.json!"
[ "$ORIG_SUM" != "$AFTER_SUM" ] || fail "sanity check failed"

BAD_TAR="$D/bad-trav.tar.gz"
"$PY_BIN" - "$BAD_TAR" <<'PY'
import io, sys, tarfile
data = b"{}"
ti = tarfile.TarInfo("../sub/state.json")
ti.size = len(data)
with tarfile.open(sys.argv[1], "w:gz") as tf:
    tf.addfile(ti, io.BytesIO(data))
PY
if (cmd_restore --test "$BAD_TAR") >/dev/null 2>&1; then
  fail "restore --test accepted path traversal archive"
fi

OFFSITE_CFG="$D/offsite-backup.json"
if (cmd_backup offsite set rclone copy /tmp/nope) >/dev/null 2>&1; then
  fail "offsite set accepted command without {}"
fi
if (cmd_backup offsite set "rclone;id" {}) >/dev/null 2>&1; then
  fail "offsite set accepted shell metacharacter in binary"
fi
PWN_FILE="$D/should_not_exist"
HOOK_LOG="$D/hook_args.txt"
cat > "$D/hook.py" <<'PY'
import sys
with open(sys.argv[1], "w", encoding="utf-8") as f:
    for a in sys.argv[2:]:
        f.write(a + "\n")
PY
cmd_backup offsite set "$PY_BIN" "$D/hook.py" "$HOOK_LOG" ";touch $PWN_FILE" "{}" >/dev/null 2>&1
rth_offsite_hook_run "$OFFSITE_CFG" "$BAK_PANEL"
[ ! -e "$PWN_FILE" ] || fail "SECURITY FAIL: offsite hook executed shell metacharacters!"
grep -qx ";touch $PWN_FILE" "$HOOK_LOG" || fail "offsite hook did not pass literal arg safely"
grep -qx "$BAK_PANEL" "$HOOK_LOG" || fail "offsite hook did not substitute {} placeholder"
cmd_backup offsite off >/dev/null 2>&1
[ ! -f "$OFFSITE_CFG" ] || fail "offsite off did not remove config"
ok "Panel restore --test and shell-free argv offsite backup hook"

# 6) Node FRP proxy-protocol & restore --test
export RATHOLENODE_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholenode"
need_root(){ :; }
ENV_FILE="$D/node.env"
SVC_FILE="$D/services.conf"
BH_SVC_FILE="$D/bh-services.conf"
FRP_CLI_TOML="$D/frpc.toml"
UP_DIR="$D/upstreams"
mkdir -p "$UP_DIR"
printf 'SERVER=panel.example.com:443\nTUNNEL=frp\nFRP_REMOTE=198.51.100.10:7000\nFRP_TOKEN=tok123\nFRP_TRANSPORT=tcp\n' > "$ENV_FILE"
printf 'n1|tok123|2087|1001\n' > "$SVC_FILE"
cmd_frp proxy-protocol v2 >/dev/null 2>&1
"$PY_BIN" -c 'import sys, tomllib; d=tomllib.load(sys.stdin.buffer); assert d["proxies"][0]["transport"]["proxyProtocolVersion"] == "v2"' < "$FRP_CLI_TOML" || fail "frpc.toml proxyProtocolVersion v2 invalid"
cmd_frp proxy-protocol off >/dev/null 2>&1
! grep -q 'proxyProtocolVersion' "$FRP_CLI_TOML" || fail "frpc.toml retained proxyProtocolVersion after off"

cmd_gre_on 203.0.113.5 10.10.10.2 gre1 --key 007 --mtu 1400 >/dev/null 2>&1
load_env
[ "${GRE_FAMILY:-}" = "gre" ] && [ "${GRE_KEY:-}" = "7" ] || fail "node GRE env keys failed round-trip reload"
ok "Node GRE env keys normalized and allowed in NODE_ENV_KEYS"

NODE_TAR_ROOT="$D/nodetar"
mkdir -p "$NODE_TAR_ROOT/etc/rathole"
printf 'SERVER=bak.example.com:443\nTUNNEL=ws\n' > "$NODE_TAR_ROOT/etc/rathole/node.env"
printf 's1|tok|2088\n' > "$NODE_TAR_ROOT/etc/rathole/services.conf"
BAK_NODE="$D/node-bak.tar.gz"
tar -czf "$BAK_NODE" -C "$NODE_TAR_ROOT" etc/rathole/node.env etc/rathole/services.conf
NODE_ENV_PRE="$(sha256sum "$ENV_FILE" | cut -d' ' -f1)"
node_dry="$(cmd_restore --test "$BAK_NODE" 2>&1)"
echo "$node_dry" | grep -q 'bak.example.com:443' || fail "node restore --test did not preview node.env"
echo "$node_dry" | grep -q 'rathole=1' || fail "node restore --test did not count services"
[ "$NODE_ENV_PRE" = "$(sha256sum "$ENV_FILE" | cut -d' ' -f1)" ] || fail "node restore --test mutated node.env"
ok "Node FRP proxy-protocol TOML & node restore --test"
