#!/usr/bin/env bash
set -euo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "FAIL: $*" >&2; exit 1; }

find_toml_python(){
  local candidate
  for candidate in "${TOML_PYTHON:-}" python3 python3.13 python3.12 python3.11; do
    [ -n "$candidate" ] || continue
    command -v "$candidate" >/dev/null 2>&1 || continue
    "$candidate" -c 'import tomllib' >/dev/null 2>&1 || continue
    echo "$candidate"
    return
  done
  fail 'Python 3.11+ with tomllib is required'
}
TOML_PYTHON="$(find_toml_python)"
assert_toml(){
  local file="$1"
  "$TOML_PYTHON" -c 'import sys, tomllib; tomllib.load(sys.stdin.buffer)' < "$file" || fail "invalid TOML: $file"
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

# Sandboxed bins for stubbed ss / ufw / nginx / systemctl
BIN="$D/bin"
mkdir -p "$BIN" "$D/nginx/conf.d" "$D/nginx/stream.d" "$D/cert" "$D/rathole" "$D/frp" "$D/paqet" "$D/logs"

cat > "$BIN/nginx" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat > "$BIN/systemctl" <<SH
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$D/logs/systemctl.log"
exit 0
SH
cat > "$BIN/ufw" <<SH
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$D/logs/ufw.log"
exit 0
SH
cat > "$BIN/ss" <<'SH'
#!/usr/bin/env bash
# Simulate occupied TCP listener on port 9998 if SS_BUSY_TCP=9998 is set
if [[ "$*" == *"sport = :${SS_BUSY_TCP:-99999}"* ]] && [[ "$*" == *"-ltn"* ]]; then
  echo "LISTEN 0 128 0.0.0.0:${SS_BUSY_TCP} 0.0.0.0:*"
fi
exit 0
SH
chmod +x "$BIN"/*
export PATH="$BIN:$PATH"

: > "$D/cert/fullchain.pem"
: > "$D/cert/privkey.pem"
: > "$D/logs/systemctl.log"
: > "$D/logs/ufw.log"

export RATHOLECTL_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholectl"

STATE="$D/state.json"
STATE_HIST_DIR="$D/history"
SERVER_TOML="$D/rathole/server.toml"
NOISE_TOML="$D/rathole/noise-server.toml"
BH_TOML="$D/rathole/backhaul-server.toml"
FRP_TOML="$D/frp/frps.toml"
PAQET_TOML="$D/paqet/client.yaml"
NGINX_CONF="$D/nginx/conf.d/rathole.conf"
STREAM_CONF="$D/nginx/stream.d/rathole-stream.conf"

need_root(){ :; }
ensure_stream_include(){ mkdir -p "$(dirname "$STREAM_CONF")"; }
ensure_noise_unit(){ :; }
ensure_backhaul_unit(){ :; }
gen_paqet_client_unit(){ :; }
frp_systemd_unit(){ :; }
install_frp(){ :; }
apply_reserved_ports(){ :; }
detect_ip(){ echo "5.202.4.40"; }

jq -n \
  --arg fc "$D/cert/fullchain.pem" --arg ky "$D/cert/privkey.pem" --arg nc "$NGINX_CONF" \
  '{domain:"panel.example", cert_fullchain:$fc, cert_key:$ky, nginx_conf:$nc,
    control_port:2333, fake_port:8080, sub_port:2096, internal_port:8443,
    data_port_start:1001, api_port_start:7001,
    nodes:[{name:"n1", port:1001, inbound_port:8444, token:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", transport:"ws"}]}' \
  > "$STATE"

# 1. Single TCP direct rule (no nginx stream, direct 0.0.0.0:2083 bind in server.toml)
cmd_port add 2083 443 --transport ws --node-server trk01 --note "VLESS REALITY" >/dev/null
assert_toml "$SERVER_TOML"
grep -qF 'bind_addr = "0.0.0.0:2083"' "$SERVER_TOML" || fail "direct port missing 0.0.0.0:2083 bind"
grep -qF 'type = "tcp"' "$SERVER_TOML" || fail "missing tcp type"
[ ! -f "$STREAM_CONF" ] || fail "STREAM_CONF created when no PP/SNI rules exist"
grep -qF 'listen 443 ssl http2' "$NGINX_CONF" || fail "443 HTTP listener altered by direct rule"
! grep -qF 'p2083' "$NGINX_CONF" || fail "nginx map should NOT contain port-manager rule"
grep -qx 'allow 2083/tcp' "$D/logs/ufw.log" || fail "ufw allow 2083/tcp missing"
ok "single TCP direct rule binds 0.0.0.0 without Nginx stream"

# 2. TCP + UDP coexistence on same port (different protocol) + duplicate TCP rejection
cmd_port add 2083 8448 --proto udp --transport kcp >/dev/null
assert_toml "$SERVER_TOML"
grep -qF '[server.services.p2083_udp]' "$SERVER_TOML" || fail "auto-named p2083_udp missing"
grep -qF 'type = "udp"' "$SERVER_TOML" || fail "udp type missing"
if (cmd_port add 2083 8449 --proto tcp) >/dev/null 2>&1; then
  fail "duplicate TCP on 2083 was accepted"
fi
ok "TCP+UDP coexistence on same port allowed; overlapping TCP rejected"

# 3. proto=both emits dual server services (tcp + _udp)
cmd_port add 5353 5353 --name hy2dual --proto both --transport ws >/dev/null
assert_toml "$SERVER_TOML"
grep -qF '[server.services.hy2dual]' "$SERVER_TOML" || fail "both tcp entry missing"
grep -qF '[server.services.hy2dual_udp]' "$SERVER_TOML" || fail "both udp entry missing"
ok "proto=both emits tcp and _udp service sections"

# 4. CSV list & range batch + >20 rejection + collision checks
out_batch="$(cmd_port add 2053,2082,2086 same --transport ws --json)"
printf '%s' "$out_batch" | "$TOML_PYTHON" -c 'import sys,json; d=json.load(sys.stdin); assert d["ok"] and len(d["created"])==3 and all("token" not in x for x in d["created"])' \
  || fail "CSV batch add JSON invalid or leaked token"
cmd_port add 3000-3004 443 --name rng >/dev/null
assert_toml "$SERVER_TOML"
grep -qF 'bind_addr = "0.0.0.0:3004"' "$SERVER_TOML" || fail "range port 3004 missing"
if (cmd_port add 4000-4020 443) >/dev/null 2>&1; then fail "accepted >20 port range"; fi
if (cmd_port add 22 443 --proto both) >/dev/null 2>&1; then fail "accepted port 22"; fi
if (cmd_port add 443 443 --proto tcp) >/dev/null 2>&1; then fail "accepted TCP port 443"; fi
if (cmd_port add 1001 443 --proto tcp) >/dev/null 2>&1; then fail "accepted node port collision 1001"; fi
if SS_BUSY_TCP=9998 bash -c 'RATHOLECTL_LIB_ONLY=1 source "'"$REPO_ROOT"'/rathole-manager/ratholectl"; STATE="'"$STATE"'"; PATH="'"$BIN"':$PATH"; check_public_port_free 9998 tcp' >/dev/null 2>&1; then
  fail "ss busy TCP listener 9998 was not rejected"
fi
# UDP 443 allowed when KCP is off, blocked when KCP is on 443
cmd_port add 443 8448 --name udp443 --proto udp --transport plain >/dev/null
if jq '.kcp = {enabled:true, port:443, profile:"balanced"}' "$STATE" > "$STATE.t" && mv "$STATE.t" "$STATE"; then
  if (cmd_port add 443 8449 --name udp443_b --proto udp) >/dev/null 2>&1; then
    fail "UDP 443 accepted while KCP uses UDP 443"
  fi
fi
ok "CSV/range batch, >20 guard, and collision checks work cleanly"

# 5. PROXY Protocol mode: loopback bind + independent STREAM_CONF without touching 443
cmd_port add 8444 443 --name pp8444 --proto tcp --transport ws --proxy-protocol >/dev/null
assert_toml "$SERVER_TOML"
grep -qF 'bind_addr = "127.0.0.1:21000"' "$SERVER_TOML" || fail "PP rule did not allocate 127.0.0.1:21000"
grep -qF 'listen 8444;' "$STREAM_CONF" || fail "STREAM_CONF missing listen 8444"
grep -qF 'proxy_protocol on;' "$STREAM_CONF" || fail "STREAM_CONF missing proxy_protocol on"
grep -qF 'proxy_pass 127.0.0.1:21000;' "$STREAM_CONF" || fail "STREAM_CONF missing proxy_pass"
! grep -qF 'listen 443;' "$STREAM_CONF" || fail "STREAM_CONF unexpectedly hijacked port 443 when sni_count==0"
if (cmd_port add 8445 443 --proto udp --proxy-protocol) >/dev/null 2>&1; then fail "PP accepted UDP"; fi
if (cmd_port add 8445 443 --proto both --proxy-protocol) >/dev/null 2>&1; then fail "PP accepted both"; fi
ok "PROXY Protocol emits isolated stream server block without affecting 443"

# 6. Backhaul, Noise, FRP proxyBindAddr toggle, and Paqet support
jq '.backhaul_port=3080 | .backhaul_token="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" | .backhaul_transport="wsmux" | .noise_port=2334 | .noise_privkey="PRIVKEY" | .frp_port=7000 | .frp_token="frptok1234" | .frp_transport="quic" | .paqet={remote:"198.51.100.5:9999", key:"pqkey123456", mode:"fast", block:"aes-128-gcm", conn:1, iface:"eth0", local_ip:"10.0.0.2", router_mac:"aa:bb:cc:dd:ee:ff"}' "$STATE" > "$STATE.t" && mv "$STATE.t" "$STATE"

if (cmd_port add 9001 443 --proto udp --transport backhaul) >/dev/null 2>&1; then
  fail "Backhaul accepted UDP"
fi
cmd_port add 9001 443 --name bh9001 --proto tcp --transport backhaul >/dev/null
assert_toml "$BH_TOML"
grep -qF '"0.0.0.0:9001=443"' "$BH_TOML" || fail "Backhaul TOML missing direct mapping 0.0.0.0:9001=443"

cmd_port add 9002 8448 --name nz9002 --proto udp --transport noise >/dev/null
assert_toml "$NOISE_TOML"
grep -qF '[server.services.nz9002]' "$NOISE_TOML" || fail "Noise TOML missing nz9002"
grep -qF 'bind_addr = "0.0.0.0:9002"' "$NOISE_TOML" || fail "Noise TOML missing 0.0.0.0:9002"

cmd_port add 9003 443 --name frp9003 --proto tcp --transport frp >/dev/null
assert_toml "$FRP_TOML"
grep -qx 'proxyBindAddr = "0.0.0.0"' "$FRP_TOML" || fail "FRP did not flip proxyBindAddr to 0.0.0.0"

cmd_port add 9004 9004 --name pq9004 --proto both --transport paqet >/dev/null
grep -qF 'listen: "0.0.0.0:9004"' "$PAQET_TOML" || fail "Paqet YAML missing listen 0.0.0.0:9004"
grep -qF 'protocol: "tcp"' "$PAQET_TOML" || fail "Paqet YAML missing tcp forward"
grep -qF 'protocol: "udp"' "$PAQET_TOML" || fail "Paqet YAML missing udp forward"
ok "Backhaul, Noise, FRP proxyBindAddr, and Paqet config generation passed"

# 7. edit, rm (preserving shared UFW rule), status --json token redaction, show --json, map --json
cmd_port edit pp8444 --inbound 8443 --proxy-protocol off --note "Updated direct" >/dev/null
assert_toml "$SERVER_TOML"
grep -qF 'bind_addr = "0.0.0.0:8444"' "$SERVER_TOML" || fail "edit PP off failed to bind 0.0.0.0:8444"
! grep -qF 'listen 8444;' "$STREAM_CONF" 2>/dev/null || fail "PP off left stream server 8444"

cmd_port rm frp9003 >/dev/null
grep -qx 'proxyBindAddr = "127.0.0.1"' "$FRP_TOML" || fail "removing direct FRP rule did not revert proxyBindAddr to 127.0.0.1"

: > "$D/logs/ufw.log"
cmd_port rm p2083 >/dev/null
grep -qx 'delete allow 2083/tcp' "$D/logs/ufw.log" || fail "UFW did not delete unused 2083/tcp"
! grep -qx 'delete allow 2083/udp' "$D/logs/ufw.log" || fail "UFW deleted 2083/udp still in use"

status_json="$(cmd_status --json)"
printf '%s' "$status_json" | "$TOML_PYTHON" -c '
import sys, json
d = json.load(sys.stdin)
assert "port_rules" in d and len(d["port_rules"]) > 0
assert all("token" not in r for r in d["port_rules"])
assert "port_map" in d and any(x["owner"] == "bh9001" for x in d["port_map"])
' || fail "status --json missing redacted port_rules/port_map"

show_json="$(cmd_port show bh9001 --json)"
printf '%s' "$show_json" | "$TOML_PYTHON" -c '
import sys, json
d = json.load(sys.stdin)
assert d["ok"] and d["token"] == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" and "backhaul add-svc bh9001" in d["command"]
' || fail "port show --json incorrect for backhaul"

map_json="$(cmd_port map --json)"
printf '%s' "$map_json" | "$TOML_PYTHON" -c '
import sys, json
arr = json.load(sys.stdin)
assert any(x["port"] == 22 and x["category"] == "system" for x in arr)
assert any(x["owner"] == "nz9002" for x in arr)
' || fail "port map --json missing expected entries"
ok "edit, rm, UFW safety, token redaction, show --json, and map --json passed"

# 8. ratholenode add-svc with tcp / udp / both + frpc.toml
export RATHOLENODE_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholenode"
ENV_FILE="$D/node.env"
SVC_FILE="$D/services.conf"
BH_SVC_FILE="$D/bh-services.conf"
CLIENT_TOML="$D/node-client.toml"
FRP_CLI_TOML="$D/frpc.toml"
need_root(){ :; }
check_port_conflict(){ :; }
printf 'SERVER=panel.example:443\nTUNNEL=ws\n' > "$ENV_FILE"
: > "$SVC_FILE"

main add-svc u8448 tok8448 8448 udp >/dev/null
assert_toml "$CLIENT_TOML"
grep -qF 'type = "udp"' "$CLIENT_TOML" || fail "node add-svc 4-arg udp failed"

main add-svc b5353 tok5353 5353 both >/dev/null
assert_toml "$CLIENT_TOML"
grep -qF '[client.services.b5353_udp]' "$CLIENT_TOML" || fail "node add-svc both missing _udp"

main add-svc f9003 tok9003 443 9003 both >/dev/null
assert_toml "$CLIENT_TOML"
grep -qF 'f9003|tok9003|443|9003|both' "$SVC_FILE" || fail "node add-svc 5-arg missing 5th column"

FRP_PROXY_PROTOCOL="v2"
gen_frp_client_toml "5.202.4.40" 7000 "frptok" "quic" ""
assert_toml "$FRP_CLI_TOML"
"$TOML_PYTHON" -c '
import sys, tomllib
d = tomllib.load(sys.stdin.buffer)
px = {p["name"]: p for p in d["proxies"]}
assert px["f9003"]["type"] == "tcp" and px["f9003"]["remotePort"] == 9003
assert px["f9003"]["transport"]["proxyProtocolVersion"] == "v2"
assert px["f9003_udp"]["type"] == "udp" and "transport" not in px["f9003_udp"]
assert px["u8448"]["type"] == "udp" and "transport" not in px["u8448"]
' < "$FRP_CLI_TOML" || fail "frpc.toml TCP/UDP/both proxy assertions failed"
ok "ratholenode add-svc and frpc.toml TCP/UDP/both passed"
