#!/usr/bin/env bash
set -euo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
D="$(mktemp -d)"
PIDS=()
cleanup(){
  local pid
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" >/dev/null 2>&1 || true
  done
  rm -rf "$D"
}
trap cleanup EXIT

find_py(){
  local c
  for c in python3 python python.exe; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import ssl, socket' >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  return 1
}
PY_BIN="$(find_py)" || fail "Python 3 with ssl is required"

# Generate self-signed cert for TLS fixture
TLS_FC="$D/fc.pem"
TLS_KEY="$D/key.pem"
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$TLS_KEY" -out "$TLS_FC" -days 5 -subj "/CN=game.example.com" >/dev/null 2>&1

# Spin up mock servers: WS 101 responder, TLS direct responder, Local UP TCP backend, + unused closed port & DOWN backend port
FIX_INFO="$D/fixtures.json"
"$PY_BIN" -u - "$TLS_FC" "$TLS_KEY" "$FIX_INFO" <<'PY' &
import http.server, json, socket, ssl, sys, threading, time

cert_file, key_file, out_file = sys.argv[1:4]

class WsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(0.005)
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.end_headers()
    def log_message(self, *args):
        pass

ws_srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), WsHandler)
threading.Thread(target=ws_srv.serve_forever, daemon=True).start()

tls_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tls_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
tls_sock.bind(("127.0.0.1", 0))
tls_sock.listen(16)
tls_port = tls_sock.getsockname()[1]
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)

def tls_loop():
    while True:
        try:
            cli, _ = tls_sock.accept()
            with ctx.wrap_socket(cli, server_side=True):
                pass
        except Exception:
            break

threading.Thread(target=tls_loop, daemon=True).start()

up_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
up_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
up_sock.bind(("127.0.0.1", 0))
up_sock.listen(16)
up_port = up_sock.getsockname()[1]

def tcp_loop():
    while True:
        try:
            cli, _ = up_sock.accept()
            cli.close()
        except Exception:
            break

threading.Thread(target=tcp_loop, daemon=True).start()

def get_closed_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p

dead_port = get_closed_port()
down_port = get_closed_port()

with open(out_file, "w", encoding="utf-8") as f:
    json.dump({
        "ws_port": ws_srv.server_address[1],
        "tls_port": tls_port,
        "up_port": up_port,
        "dead_port": dead_port,
        "down_port": down_port,
    }, f)

while True:
    time.sleep(1)
PY
PIDS+=($!)

for _ in $(seq 1 40); do
  [ -s "$FIX_INFO" ] && break
  sleep 0.1
done
[ -s "$FIX_INFO" ] || fail "test fixture server failed to start"

WS_PORT="$(jq -r '.ws_port' "$FIX_INFO")"
TLS_PORT="$(jq -r '.tls_port' "$FIX_INFO")"
UP_PORT="$(jq -r '.up_port' "$FIX_INFO")"
DEAD_PORT="$(jq -r '.dead_port' "$FIX_INFO")"
DOWN_PORT="$(jq -r '.down_port' "$FIX_INFO")"

# Stub systemctl
BIN="$D/bin"
mkdir -p "$BIN"
cat > "$BIN/systemctl" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  is-active|is-enabled) exit 0 ;;
esac
exit 0
EOF
chmod +x "$BIN/systemctl"
export PATH="$BIN:$PATH"

# ---- 1) Test ratholectl test ----
export RATHOLECTL_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholectl"
STATE="$D/state.json"
cat > "$STATE" <<JSON
{
  "domain": "panel.example.com",
  "cert_fullchain": "$TLS_FC",
  "cert_key": "$TLS_KEY",
  "nginx_conf": "$D/nginx.conf",
  "control_port": 2333,
  "fake_port": 8080,
  "sub_port": 2096,
  "internal_port": 8443,
  "nodes": [
    {"name": "ws1", "port": $WS_PORT, "inbound_port": 2087, "token": "aaaaaaaaaaaaaaaaaaaaaaaa", "transport": "ws"},
    {"name": "dead1", "port": $DEAD_PORT, "inbound_port": 2088, "token": "bbbbbbbbbbbbbbbbbbbbbbbb", "transport": "ws"},
    {"name": "game1", "port": $TLS_PORT, "inbound_port": 443, "token": "cccccccccccccccccccccccc", "sni": "game.example.com"}
  ]
}
JSON

res_ws="$(cmd_test ws1 --count 3 --json)"
"$PY_BIN" - "$res_ws" <<'PY' || fail "ratholectl test ws1 assertion failed: $res_ws"
import json, sys
d = json.loads(sys.argv[1])
assert d["role"] == "panel"
assert d["node"] == "ws1"
assert d["ok"] is True
assert d["ok_count"] == 3
assert d["loss_pct"] == 0.0
assert d["listener_up"] is True
assert d["http_status"] == 101
assert d["rtt_ms"]["avg"] > 0
assert d["service"]["active"] is True
PY
ok "ratholectl test healthy http_ws node returns 101, 0% loss, RTT stats"

res_dead="$(cmd_test dead1 --count 2 --json)"
"$PY_BIN" - "$res_dead" <<'PY' || fail "ratholectl test dead1 assertion failed: $res_dead"
import json, sys
d = json.loads(sys.argv[1])
assert d["ok"] is False
assert d["verdict"] == "failed"
assert d["listener_up"] is False
assert d["loss_pct"] == 100.0
PY
ok "ratholectl test dead node reports listener_up=false and 100% loss"

res_game="$(cmd_test game1 --count 2 --json)"
"$PY_BIN" - "$res_game" <<'PY' || fail "ratholectl test game1 assertion failed: $res_game"
import json, sys
d = json.loads(sys.argv[1])
assert d["ok"] is True
assert d["probe_mode"] == "tls_direct"
assert d["ok_count"] == 2
assert d["sni"] == "game.example.com"
assert d["tls_version"]
PY
ok "ratholectl test game/SNI node probes tls_direct"

if (cmd_test ws1 --count 50) >/dev/null 2>&1; then
  fail "ratholectl test accepted invalid --count 50"
fi
if (cmd_test unknown_node --count 2) >/dev/null 2>&1; then
  fail "ratholectl test accepted unknown node"
fi
cmd_test ws1 --count 1 | grep -q 'verdict' || fail "ratholectl test human output missing verdict"
ok "ratholectl test validation and human output"

# ---- 2) Test ratholenode test ----
export RATHOLENODE_LIB_ONLY=1
source "$REPO_ROOT/rathole-manager/ratholenode"
ENV_FILE="$D/node.env"
SVC_FILE="$D/services.conf"
BH_SVC_FILE="$D/bh-services.conf"
UP_DIR="$D/upstreams"
mkdir -p "$UP_DIR"

printf 'SERVER=127.0.0.1:%s\nTUNNEL=plain\nPLAIN_REMOTE=127.0.0.1:%s\n' "$WS_PORT" "$WS_PORT" > "$ENV_FILE"
printf 'svc_up|tok1|%s\nsvc_down|tok2|%s\n' "$UP_PORT" "$DOWN_PORT" > "$SVC_FILE"
: > "$BH_SVC_FILE"

nres_plain="$(cmd_test --count 3 --json)"
"$PY_BIN" - "$nres_plain" <<'PY' || fail "ratholenode test plain assertion failed: $nres_plain"
import json, sys
d = json.loads(sys.argv[1])
assert d["role"] == "node"
assert d["transport"] == "plain"
assert d["probe_mode"] == "ws_plain"
assert d["ok"] is True
assert d["ok_count"] == 3
bmap = {b["name"]: b for b in d["backends"]}
assert bmap["svc_up"]["up"] is True
assert bmap["svc_down"]["up"] is False
PY
ok "ratholenode test TUNNEL=plain + mixed UP/DOWN local backends"

printf 'SERVER=127.0.0.1:%s\nTUNNEL=noise\nNOISE_REMOTE=127.0.0.1:%s\nNOISE_PUBKEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n' "$UP_PORT" "$UP_PORT" > "$ENV_FILE"
nres_noise="$(cmd_test --count 2 --json)"
"$PY_BIN" - "$nres_noise" <<'PY' || fail "ratholenode test noise assertion failed: $nres_noise"
import json, sys
d = json.loads(sys.argv[1])
assert d["ok"] is True
assert d["probe_mode"] == "tcp"
assert d["ok_count"] == 2
PY
ok "ratholenode test TUNNEL=noise probes TCP cleanly"

# Test rth_gre_peer_ip helper directly
[ "$(rth_gre_peer_ip "10.10.10.1")" = "10.10.10.2" ] || fail "rth_gre_peer_ip v4 failed"
[ "$(rth_gre_peer_ip "fd00::1/126")" = "fd00::2" ] || fail "rth_gre_peer_ip v6 failed"
ok "rth_gre_peer_ip computes IPv4/IPv6 point-to-point peers"
