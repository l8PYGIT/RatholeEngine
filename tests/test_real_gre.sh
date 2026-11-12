#!/usr/bin/env bash
# Opt-in kernel GRE + FRP/GRE lab. Entire topology is inside a new netns.
set -euo pipefail
if [ "${RATHOLE_REAL_GRE:-}" != 1 ]; then echo 'skip - set RATHOLE_REAL_GRE=1'; exit 0; fi
if [ "${1:-}" != --isolated ]; then
  exec unshare -n -- bash "$0" --isolated
fi
D="$(mktemp -d /tmp/rathole-gre-lab.XXXXXX)"
P1= P2= S= C= HTTP=
cleanup(){
  for pid in "$C" "$S" "$HTTP" "$P1" "$P2"; do [ -z "$pid" ] || kill "$pid" 2>/dev/null || true; done
  for pid in "$C" "$S" "$HTTP" "$P1" "$P2"; do [ -z "$pid" ] || wait "$pid" 2>/dev/null || true; done
  rm -rf "$D"
}
trap cleanup EXIT INT TERM
unshare -n -- sleep 180 & P1=$!
unshare -n -- sleep 180 & P2=$!
sleep .3
ip link add lab-a type veth peer name lab-b
ip link set lab-a netns "$P1"; ip link set lab-b netns "$P2"
N1(){ nsenter -t "$P1" -n -- "$@"; }
N2(){ nsenter -t "$P2" -n -- "$@"; }
N1 ip link set lo up; N2 ip link set lo up
N1 ip addr add 192.0.2.1/30 dev lab-a; N1 ip link set lab-a up
N2 ip addr add 192.0.2.2/30 dev lab-b; N2 ip link set lab-b up
N1 ip tunnel add gre-lab mode gre local 192.0.2.1 remote 192.0.2.2 ttl 64
N2 ip tunnel add gre-lab mode gre local 192.0.2.2 remote 192.0.2.1 ttl 64
N1 ip addr add 10.203.1.1/30 dev gre-lab; N1 ip link set gre-lab mtu 1476 up
N2 ip addr add 10.203.1.2/30 dev gre-lab; N2 ip link set gre-lab mtu 1476 up
N1 ping -c 3 -W 1 10.203.1.2 > "$D/ping.log"
N1 ping -c 1 -W 1 -M do -s 1448 10.203.1.2 >> "$D/ping.log"
echo 'ok - real GRE roundtrip and MTU 1476'
N2 ip link set lab-b down
if N1 ping -c 1 -W 1 10.203.1.2 > /dev/null 2>&1; then echo 'FAIL - GRE down did not fail'; exit 1; fi
N2 ip link set lab-b up
N1 ping -c 1 -W 2 10.203.1.2 >/dev/null
echo 'ok - real GRE link failure and recovery'
if [ -z "${FRPS_TEST_BIN:-}" ] || [ -z "${FRPC_TEST_BIN:-}" ]; then echo 'skip - FRP/GRE needs binary paths'; exit 0; fi
printf 'gre-frp-payload' > "$D/index.html"
N2 python3 -m http.server 19887 --bind 127.0.0.1 --directory "$D" >"$D/http.log" 2>&1 & HTTP=$!
cat > "$D/server.toml" <<'CONF'
bindAddr = "10.203.1.1"
bindPort = 19888
proxyBindAddr = "127.0.0.1"
auth.token = "integration-token"
CONF
cat > "$D/client.toml" <<'CONF'
serverAddr = "10.203.1.1"
serverPort = 19888
auth.token = "integration-token"
loginFailExit = false
[[proxies]]
name = "gre-test"
type = "tcp"
localIP = "127.0.0.1"
localPort = 19887
remotePort = 19889
CONF
N1 "$FRPS_TEST_BIN" -c "$D/server.toml" >"$D/frps.log" 2>&1 & S=$!
N2 "$FRPC_TEST_BIN" -c "$D/client.toml" >"$D/frpc.log" 2>&1 & C=$!
check_payload(){
  local i
  for i in $(seq 1 30); do
    if [ "$(N1 curl -fsS --max-time 1 http://127.0.0.1:19889/ 2>/dev/null)" = gre-frp-payload ]; then return 0; fi
    sleep .5
  done
  return 1
}
check_payload || { echo 'FAIL - FRP/GRE payload'; exit 1; }
echo 'ok - real FRP carried over GRE'
