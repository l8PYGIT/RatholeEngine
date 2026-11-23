#!/usr/bin/env bash
set -uo pipefail

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

# Generate self-signed TLS cert with IP SAN 127.0.0.1 for TLS WS probe verification
TLS_FC="$D/fc.pem"
TLS_KEY="$D/key.pem"
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$TLS_KEY" -out "$TLS_FC" -days 5 \
  -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1" >/dev/null 2>&1 || \
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "$TLS_KEY" -out "$TLS_FC" -days 5 -subj "/CN=127.0.0.1" >/dev/null 2>&1

FIX_INFO="$D/fixtures.json"
"$PY_BIN" -u - "$TLS_FC" "$TLS_KEY" "$FIX_INFO" <<'PY' &
import json, socket, ssl, sys, threading, time

cert_file, key_file, out_file = sys.argv[1:4]

# 1) Plain TCP listener (for noise / frp TCP probes)
tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
tcp_sock.bind(("127.0.0.1", 0))
tcp_sock.listen(16)
tcp_port = tcp_sock.getsockname()[1]

def tcp_loop():
    while True:
        try:
            c, _ = tcp_sock.accept()
            c.close()
        except Exception:
            break

threading.Thread(target=tcp_loop, daemon=True).start()

# 2) TLS + HTTP 101 WebSocket listener (for ws primary/backup endpoint probes)
ws_tls_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ws_tls_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
ws_tls_sock.bind(("127.0.0.1", 0))
ws_tls_sock.listen(16)
ws_tls_port = ws_tls_sock.getsockname()[1]
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)

def ws_tls_client(cli):
    try:
        with ctx.wrap_socket(cli, server_side=True) as tls_c:
            tls_c.settimeout(2.0)
            tls_c.recv(2048)
            tls_c.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
            time.sleep(0.05)
            try:
                tls_c.unwrap()
            except Exception:
                pass
    except Exception:
        pass

def ws_tls_loop():
    while True:
        try:
            c, _ = ws_tls_sock.accept()
            threading.Thread(target=ws_tls_client, args=(c,), daemon=True).start()
        except Exception:
            break

threading.Thread(target=ws_tls_loop, daemon=True).start()

# 3) Closed port
s_closed = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s_closed.bind(("127.0.0.1", 0))
closed_port = s_closed.getsockname()[1]
s_closed.close()

with open(out_file, "w", encoding="utf-8") as f:
    json.dump({"tcp_port": tcp_port, "ws_tls_port": ws_tls_port, "closed_port": closed_port}, f)

while True:
    time.sleep(1)
PY
PIDS+=($!)

for _ in $(seq 1 40); do
  [ -s "$FIX_INFO" ] && break
  sleep 0.1
done
[ -s "$FIX_INFO" ] || fail "test fixture server failed to start"

OPEN_TCP="$(jq -r '.tcp_port' "$FIX_INFO")"
OPEN_WS_TLS="$(jq -r '.ws_tls_port' "$FIX_INFO")"
CLOSED_PORT="$(jq -r '.closed_port' "$FIX_INFO")"

# ---- Subtest 1 & 2: noise and frp probes ----
(
  export RATHOLENODE_LIB_ONLY=1
  source "$REPO_ROOT/rathole-manager/ratholenode"
  ENV_FILE="$D/node1.env"
  SVC_FILE="$D/svc1.conf"
  ADAPTIVE_STATE="$D/st1.json"
  : > "$SVC_FILE"

  # Unconfigured noise without pubkey
  NOISE_REMOTE="127.0.0.1:$OPEN_TCP"; NOISE_PUBKEY=""
  res_u="$(adaptive_probe_noise || true)"
  grep -Fq "unconfigured" <<<"$res_u" || fail "expected unconfigured noise without pubkey, got: $res_u"

  NOISE_PUBKEY="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
  res_ok="$(adaptive_probe_noise "127.0.0.1:$OPEN_TCP")" || fail "adaptive_probe_noise open failed: $res_ok"
  grep -Fq "healthy:" <<<"$res_ok" || fail "adaptive_probe_noise open unexpected: $res_ok"

  res_bad="$(adaptive_probe_noise "127.0.0.1:$CLOSED_PORT" || true)"
  [[ "$res_bad" =~ tcp_refused|tcp_timeout ]] || fail "adaptive_probe_noise closed unexpected: $res_bad"
  ok "adaptive_probe_noise distinguishes unconfigured, open TCP, and closed TCP"

  FRP_TOKEN="abcdef1234567890"
  FRP_REMOTE="127.0.0.1:$OPEN_TCP"
  FRP_TRANSPORT="tcp"
  frp_ok="$(adaptive_probe_frp)" || fail "adaptive_probe_frp open TCP failed: $frp_ok"
  grep -Fq "healthy:" <<<"$frp_ok" || fail "adaptive_probe_frp open unexpected: $frp_ok"

  frp_bad="$(adaptive_probe_frp "127.0.0.1:$CLOSED_PORT" tcp || true)"
  [[ "$frp_bad" =~ tcp_refused|tcp_timeout ]] || fail "adaptive_probe_frp closed unexpected: $frp_bad"

  printf 'SERVER=127.0.0.1:%s\nTUNNEL=frp\nFRP_REMOTE=127.0.0.1:%s\nFRP_TOKEN=%s\nFRP_TRANSPORT=tcp\n' \
    "$CLOSED_PORT" "$OPEN_TCP" "$FRP_TOKEN" > "$ENV_FILE"
  systemctl(){ return 1; }
  cls_dead="$(ADAPTIVE_WRITE_STATE=0 adaptive_run_probe || true)"
  [ "$cls_dead" = "dead" ] || fail "expected dead when frpc inactive, got: $cls_dead"

  systemctl(){ return 0; }
  cls_up="$(ADAPTIVE_WRITE_STATE=0 adaptive_run_probe)" || fail "frp active run_probe failed"
  [ "$cls_up" = "healthy" ] || fail "expected healthy when frpc active + reachable, got: $cls_up"
  ok "adaptive_probe_frp checks daemon activity + TCP reachability"
)

# ---- Subtest 3 & 4: multi-carrier chain with candidate pre-probing & plain gate ----
(
  export RATHOLENODE_LIB_ONLY=1
  source "$REPO_ROOT/rathole-manager/ratholenode"
  ENV_FILE="$D/node2.env"
  SVC_FILE="$D/svc2.conf"
  CLIENT_TOML="$D/client2.toml"
  FRP_CLI_TOML="$D/frpc2.toml"
  ADAPTIVE_ENV="$D/adaptive2.env"
  ADAPTIVE_STATE="$D/adaptive2.json"
  ADAPTIVE_LOCK="$D/adaptive2.lock"
  SVC_LOG="$D/svc2.log"
  : > "$SVC_LOG"

  cat > "$ENV_FILE" <<EOF
SERVER=127.0.0.1:${CLOSED_PORT}
TUNNEL=ws
NOISE_REMOTE=127.0.0.1:${CLOSED_PORT}
NOISE_PUBKEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
FRP_REMOTE=127.0.0.1:${OPEN_TCP}
FRP_TOKEN=abcdef1234567890
FRP_TRANSPORT=tcp
PLAIN_REMOTE=127.0.0.1:${OPEN_TCP}
EOF
  printf 'svc1|tok1|8444\n' > "$SVC_FILE"

  # plain must be gated when ALLOW_INSECURE=0, permitted when ALLOW_INSECURE=1
  load_env
  ALLOW_INSECURE=0
  p_gated="$(adaptive_pick_next_carrier ws "ws,plain" 0 2>/dev/null || true)"
  [ -z "$p_gated" ] || fail "plain should not be picked when ALLOW_INSECURE=0 (got: $p_gated)"
  ALLOW_INSECURE=1
  p_allow="$(adaptive_pick_next_carrier ws "ws,plain" 0)"
  [ "$p_allow" = "plain" ] || fail "plain should be picked when ALLOW_INSECURE=1 (got: $p_allow)"
  ok "plain carrier in chain enforces ALLOW_INSECURE gate"

  need_root(){ return 0; }
  flock(){ return 0; }
  systemctl(){ echo "$*" >> "$SVC_LOG"; return 0; }
  mkdir -p "$D/bin"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$D/bin/frpc"
  chmod +x "$D/bin/frpc"
  export PATH="$D/bin:$PATH"

  cmd_adaptive on --interval 30 --failures 3 --recoveries 2 --chain ws,noise,frp --probe-candidates
  echo '{"consecutive_failures":2}' > "$ADAPTIVE_STATE"
  main adaptive run
  load_env
  [ "${TUNNEL:-}" = "frp" ] || fail "expected chain to skip dead noise and switch directly to frp, got: ${TUNNEL:-}"
  [ -s "$FRP_CLI_TOML" ] || fail "frpc.toml was not generated during switch to frp"
  grep -Fq "disable --now rathole-client" "$SVC_LOG" || fail "rathole-client was not stopped on frp switch"
  grep -Fq "restart frpc" "$SVC_LOG" || fail "frpc was not restarted on frp switch"
  [ "$(jq -r '.last_reason' "$ADAPTIVE_STATE")" = "carrier_failover" ] || fail "missing carrier_failover reason"
  ok "multi-carrier chain with pre-probing skips dead noise and switches to healthy frp"
)

# ---- Subtest 5: primary carrier auto-recovery ----
(
  export RATHOLENODE_LIB_ONLY=1
  source "$REPO_ROOT/rathole-manager/ratholenode"
  ENV_FILE="$D/node3.env"
  SVC_FILE="$D/svc3.conf"
  CLIENT_TOML="$D/client3.toml"
  ADAPTIVE_ENV="$D/adaptive3.env"
  ADAPTIVE_STATE="$D/adaptive3.json"
  ADAPTIVE_LOCK="$D/adaptive3.lock"
  printf 'svc1|tok1|8444\n' > "$SVC_FILE"
  cat > "$ENV_FILE" <<EOF
SERVER=127.0.0.1:${OPEN_WS_TLS}
TLS_TRUSTED_ROOT=${TLS_FC}
TUNNEL=noise
NOISE_REMOTE=127.0.0.1:${OPEN_TCP}
NOISE_PUBKEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
EOF
  cat > "$ADAPTIVE_ENV" <<'EOF'
ADAPTIVE_ENABLED=1
ADAPTIVE_INTERVAL=30
ADAPTIVE_FAILURES=3
ADAPTIVE_RECOVERIES=2
ADAPTIVE_COOLDOWN=0
ADAPTIVE_CHAIN=ws,noise
ADAPTIVE_PROBE_CANDIDATES=0
ADAPTIVE_AUTO_RECOVER=1
EOF
  echo '{"consecutive_failures":0,"primary_recoveries":0,"last_switch_ts":0}' > "$ADAPTIVE_STATE"

  need_root(){ return 0; }
  flock(){ return 0; }
  systemctl(){ return 0; }

  # 1st healthy run: increments primary_recoveries=1, stays on noise
  main adaptive run
  load_env
  [ "$TUNNEL" = "noise" ] || fail "should stay on noise after 1st primary recovery probe (got: $TUNNEL)"
  [ "$(jq -r '.primary_recoveries' "$ADAPTIVE_STATE")" = "1" ] || fail "primary_recoveries did not increment to 1"

  # 2nd healthy run: reaches ADAPTIVE_RECOVERIES=2 -> switches back to primary ws
  main adaptive run
  load_env
  [ "$TUNNEL" = "ws" ] || fail "should auto-recover to ws after 2 healthy probes (got: $TUNNEL)"
  [ "$(jq -r '.last_reason' "$ADAPTIVE_STATE")" = "primary_carrier_recovered" ] || fail "missing primary_carrier_recovered reason"
  ok "adaptive auto-recover restores primary ws carrier after consecutive healthy probes"
)

# ---- Subtest 6, 7 & 8: backup endpoints EWMA scoring, failover, and security rejection ----
(
  export RATHOLENODE_LIB_ONLY=1
  source "$REPO_ROOT/rathole-manager/ratholenode"
  ENV_FILE="$D/node4.env"
  SVC_FILE="$D/svc4.conf"
  CLIENT_TOML="$D/client4.toml"
  ADAPTIVE_ENV="$D/adaptive4.env"
  ADAPTIVE_STATE="$D/adaptive4.json"
  ADAPTIVE_LOCK="$D/adaptive4.lock"
  ENDPOINT_SCORES_FILE="$D/ep_scores4.json"
  SVC_LOG="$D/svc4.log"
  : > "$SVC_LOG"

  cat > "$ENV_FILE" <<EOF
SERVER=127.0.0.1:${CLOSED_PORT}
TLS_TRUSTED_ROOT=${TLS_FC}
TUNNEL=ws
EOF
  printf 'svc1|tok1|8444\n' > "$SVC_FILE"

  need_root(){ return 0; }
  flock(){ return 0; }
  systemctl(){ echo "$*" >> "$SVC_LOG"; return 0; }
  mkdir -p "$D/bin"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$D/bin/frpc"
  chmod +x "$D/bin/frpc"
  export PATH="$D/bin:$PATH"

  # Validation rejects invalid / injected endpoint addresses
  if (main endpoints add "127.0.0.1;id") >/dev/null 2>&1; then
    fail "endpoints add accepted shell injection"
  fi
  if (main endpoints add "127.0.0.1:99999") >/dev/null 2>&1; then
    fail "endpoints add accepted out-of-range port"
  fi

  main endpoints add "127.0.0.1:$OPEN_WS_TLS" >/dev/null || fail "endpoints add failed"
  ep_test_json="$(main endpoints test --json)" || fail "endpoints test --json failed"
  "$PY_BIN" - "$ep_test_json" "$OPEN_WS_TLS" "$CLOSED_PORT" <<'PY' || fail "endpoint EWMA scores assertion failed: $ep_test_json"
import json, sys
d = json.loads(sys.argv[1])
open_addr = "127.0.0.1:" + sys.argv[2]
closed_addr = "127.0.0.1:" + sys.argv[3]
by_addr = {r["addr"]: r for r in d["results"]}
assert by_addr[open_addr]["last_ok"] is True
assert by_addr[open_addr]["score"] >= 90.0
assert by_addr[closed_addr]["last_ok"] is False
assert by_addr[closed_addr]["score"] == 0.0
PY
  ok "endpoints add/test/EWMA scoring ranks healthy TLS WS endpoint above closed primary"

  # Single-carrier chain ws -> no other carrier -> failover must move SERVER to healthy backup
  cat > "$ADAPTIVE_ENV" <<'EOF'
ADAPTIVE_ENABLED=1
ADAPTIVE_INTERVAL=30
ADAPTIVE_FAILURES=3
ADAPTIVE_RECOVERIES=2
ADAPTIVE_COOLDOWN=300
ADAPTIVE_CHAIN=ws
ADAPTIVE_PROBE_CANDIDATES=0
ADAPTIVE_AUTO_RECOVER=1
EOF
  echo '{"consecutive_failures":2}' > "$ADAPTIVE_STATE"
  main adaptive run
  load_env
  [ "$SERVER" = "127.0.0.1:$OPEN_WS_TLS" ] || fail "adaptive run did not fail over to healthy backup endpoint (SERVER=$SERVER)"
  [ "$PRIMARY_SERVER" = "127.0.0.1:$CLOSED_PORT" ] || fail "PRIMARY_SERVER was not preserved (got: $PRIMARY_SERVER)"
  [ "$(jq -r '.last_reason' "$ADAPTIVE_STATE")" = "endpoint_failover" ] || fail "missing endpoint_failover reason"
  ok "cmd_adaptive run fails over to highest-scored backup endpoint when no carrier switch exists"

  # adaptive_load_env rejects injection in ADAPTIVE_CHAIN
  ADAPTIVE_CHAIN=""
  printf 'ADAPTIVE_CHAIN=$(touch %s/pwned)\n' "$D" > "$ADAPTIVE_ENV"
  adaptive_load_env 2>/dev/null || true
  [ ! -e "$D/pwned" ] || fail "shell injection executed in adaptive_load_env"
  [ "$ADAPTIVE_CHAIN" = "ws,kcp" ] || fail "invalid ADAPTIVE_CHAIN did not fall back to ws,kcp (got: $ADAPTIVE_CHAIN)"
  ok "adaptive_load_env rejects shell metacharacters in ADAPTIVE_CHAIN safely"
)
