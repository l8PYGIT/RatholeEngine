#!/usr/bin/env bash
# test_m7_paqet_and_xray.sh — M7: paqet (Direct PCK), Managed Xray (REALITY/XHTTP), Cover Scanner & redaction
set -uo pipefail

ok(){ echo "ok - $*"; }
fail(){ echo "not ok - $*" >&2; exit 1; }

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TEST_TMP_ROOT="${TEST_TMP_ROOT:-${TMPDIR:-/tmp}}"
command -v openssl >/dev/null 2>&1 || fail "openssl lazem ast"
command -v jq >/dev/null 2>&1 || fail "jq lazem ast"

find_py(){
  local c
  for c in python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import ssl, socket, json' >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  return 1
}
PY_BIN="$(find_py)" || fail "python3 ba ssl/json lazem ast"

D="$(mktemp -d "${TEST_TMP_ROOT%/}/test-m7.XXXXXX")"
PIDS=()
cleanup(){
  local pid
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" >/dev/null 2>&1 || true
  done
  rm -rf "$D"
}
trap cleanup EXIT INT TERM

# Stub executables for sandboxed node/iran CLI testing
BIN="$D/bin"
EMPTY_BIN="$D/empty-bin"
mkdir -p "$BIN" "$EMPTY_BIN"

cat > "$BIN/systemctl" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
  is-active|is-enabled) exit 0 ;;
esac
exit 0
EOF
cat > "$BIN/iptables" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$BIN/ufw" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$BIN/paqet" <<'EOF'
#!/usr/bin/env bash
echo "paqet stub v1.0.0"
exit 0
EOF
cat > "$BIN/xray" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "run" ] && [ "${2:-}" = "-test" ]; then
  exit 0
fi
if [ "${1:-}" = "x25519" ]; then
  # Emulate Xray x25519 output disabled by default unless flag requested; keep exit 1 to test OpenSSL fallback too
  exit 1
fi
echo "Xray stub 24.12.31"
exit 0
EOF
chmod +x "$BIN/systemctl" "$BIN/iptables" "$BIN/ufw" "$BIN/paqet" "$BIN/xray"
export PATH="$BIN:$PATH"

# ---- 1: rth_xray_gen_x25519 (OpenSSL DER -> Xray base64url fallback) & rth_redact ----
(
  set -uo pipefail
  # shellcheck disable=SC1091
  source "$REPO_ROOT/rathole-manager/common.sh"
  export RATHOLE_BIN_DIR="$EMPTY_BIN"
  kp="$(rth_xray_gen_x25519)" || exit 1
  IFS='|' read -r priv pub <<<"$kp"
  echo "$priv" | grep -qE '^[A-Za-z0-9_-]{43}$' || exit 2
  echo "$pub"  | grep -qE '^[A-Za-z0-9_-]{43}$' || exit 3
  [ "$priv" != "$pub" ] || exit 4

  red_out="$(rth_redact <<'TXT'
"paqet_key": "pq_secret_123456"
PAQET_KEY=pq_secret_abcdef
"privateKey": "priv_secret_b64url_value_here"
XRAY_PRIVATE_KEY=xr_priv_env_secret
XRAY_UUID=11111111-2222-4333-8444-555555555555
    key: "yaml_secret_987654"
vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@198.51.100.5:443?type=tcp
TXT
)"
  echo "$red_out" | grep -qE 'pq_secret|priv_secret|xr_priv_env|11111111-2222|yaml_secret|aaaaaaaa-bbbb' && exit 5
  echo "$red_out" | grep -qF '***REDACTED***' || exit 6
) || fail "rth_xray_gen_x25519 or rth_redact assertion failed"
ok "rth_xray_gen_x25519 (OpenSSL fallback) + rth_redact masking for paqet & xray secrets"

# ---- 2: ratholenode paqet server & Managed Xray (REALITY + XHTTP) ----
(
  set -uo pipefail
  export RATHOLENODE_LIB_ONLY=1 RATHOLE_BIN_DIR="$BIN" RATHOLE_SKIP_XRAY_TEST=0
  # shellcheck disable=SC1091
  source "$REPO_ROOT/rathole-manager/ratholenode"
  need_root(){ :; }
  ENV_FILE="$D/node.env"
  SVC_CONF="$D/services.conf"
  PAQET_SRV_YAML="$D/paqet-server.yaml"
  PAQET_SRV_UNIT="$D/rathole-paqet-server.service"
  XRAY_CONF="$D/xray-config.json"
  XRAY_ENV="$D/xray.env"
  XRAY_UNIT="$D/rathole-xray.service"
  : > "$ENV_FILE"
  : > "$SVC_CONF"

  PQ_KEY="abcdef0123456789abcdef0123456789"
  show_out="$(cmd_paqet on 9999 "$PQ_KEY" --mode fast2 --block aes-128-gcm --conn 2 \
    --iface eth0 --local-ip 198.51.100.2 --router-mac aa:bb:cc:dd:ee:ff --skip-iptables)" || exit 1
  echo "$show_out" | grep -qF "ratholectl paqet on 198.51.100.2:9999 $PQ_KEY fast2 --block aes-128-gcm" || exit 2
  grep -qF 'role: "server"' "$PAQET_SRV_YAML" || exit 3
  grep -qF 'addr: ":9999"' "$PAQET_SRV_YAML" || exit 4
  grep -qF 'mode: "fast2"' "$PAQET_SRV_YAML" || exit 5
  grep -qF 'CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN' "$PAQET_SRV_UNIT" || exit 6
  cmd_paqet status | grep -qF 'listen=:9999' || exit 7
  cmd_paqet off >/dev/null || exit 8
  [ ! -e "$PAQET_SRV_YAML" ] && [ ! -e "$PAQET_SRV_UNIT" ] || exit 9

  cmd_xray setup reality --port 8443 --uuid 22222222-3333-4444-8555-666666666666 \
    --dest www.microsoft.com:443 --sni www.microsoft.com --short-id a1b2c3d4 \
    --proxy-protocol >/dev/null || exit 10
  "$PY_BIN" - "$XRAY_CONF" <<'PY' || exit 11
import json, sys
cfg = json.load(open(sys.argv[1]))
inb = cfg["inbounds"][0]
assert inb["port"] == 8443
assert inb["settings"]["clients"][0]["flow"] == "xtls-rprx-vision"
st = inb["streamSettings"]
assert st["security"] == "reality"
assert st["realitySettings"]["dest"] == "www.microsoft.com:443"
assert st["realitySettings"]["privateKey"]
assert st["sockopt"]["acceptProxyProtocol"] is True
PY
  st_json="$(cmd_xray status --json)"
  "$PY_BIN" - "$st_json" <<'PY' || exit 12
import json, sys
raw = sys.argv[1]
assert "privateKey" not in raw and "private_key" not in raw
d = json.loads(raw)
assert d["configured"] is True and d["active"] is True
assert d["mode"] == "reality" and d["port"] == 8443
assert d["proxy_protocol"] is True
assert len(d["public_key"]) >= 40
PY
  uri_r="$(cmd_xray uri 203.0.113.5 443)"
  echo "$uri_r" | grep -qE '^vless://22222222-3333-4444-8555-666666666666@203\.0\.113\.5:443\?' || exit 13
  echo "$uri_r" | grep -qF 'security=reality' || exit 14
  echo "$uri_r" | grep -qF 'flow=xtls-rprx-vision' || exit 15

  cmd_xray setup xhttp --port 2087 --path /xhttp --mode stream-up >/dev/null || exit 16
  uri_x="$(cmd_xray uri 203.0.113.5 443)"
  echo "$uri_x" | grep -qF 'type=xhttp' || exit 17
  echo "$uri_x" | grep -qF 'mode=stream-up' || exit 18
  cmd_xray off >/dev/null || exit 19
  [ ! -e "$XRAY_CONF" ] && [ ! -e "$XRAY_ENV" ] || exit 20
) || fail "ratholenode paqet & Managed Xray lifecycle failed ($?)"
ok "ratholenode paqet server YAML/unit + Managed Xray REALITY/XHTTP setup/status/uri/off"

# ---- 3: ratholectl paqet client YAML, server.toml exclusion & status --json ----
(
  set -uo pipefail
  export RATHOLECTL_LIB_ONLY=1 RATHOLE_BIN_DIR="$BIN"
  # shellcheck disable=SC1091
  source "$REPO_ROOT/rathole-manager/ratholectl"
  need_root(){ :; }
  nginx(){ :; }
  STATE="$D/state.json"
  SERVER_TOML="$D/server.toml"
  NGINX_CONF="$D/nginx.conf"
  PAQET_TOML="$D/paqet-client.yaml"
  PAQET_UNIT="$D/rathole-paqet-client.service"
  BH_TOML="$D/bh-server.toml"
  NOISE_TOML="$D/noise-server.toml"

  cat > "$STATE" <<JSON
{
  "domain": "panel.example.com",
  "cert_fullchain": "$D/fake.pem",
  "cert_key": "$D/fake.key",
  "nginx_conf": "$NGINX_CONF",
  "control_port": 2333,
  "fake_port": 8080,
  "sub_port": 2096,
  "internal_port": 8443,
  "nodes": [
    {"name": "ws1", "port": 1005, "inbound_port": 8444, "token": "aaaaaaaaaaaaaaaaaaaaaaaa", "transport": "ws"},
    {"name": "pq1", "port": 1006, "inbound_port": 8445, "api_local_port": 9001, "api_token": "cccccccccccccccccccccccc", "token": "bbbbbbbbbbbbbbbbbbbbbbbb", "transport": "ws"}
  ]
}
JSON

  PQ_KEY="abcdef0123456789abcdef0123456789"
  cmd_paqet on 198.51.100.2:9999 "$PQ_KEY" --mode fast3 --block salsa20 --conn 2 \
    --iface eth0 --local-ip 203.0.113.2 --router-mac 11:22:33:44:55:66 --skip-iptables >/dev/null || exit 1
  cmd_paqet node pq1 on >/dev/null || exit 2

  grep -qF '[server.services.ws1]' "$SERVER_TOML" || exit 3
  grep -qF '[server.services.pq1]' "$SERVER_TOML" && exit 4
  grep -qF 'role: "client"' "$PAQET_TOML" || exit 5
  grep -qF 'listen: "127.0.0.1:1006"' "$PAQET_TOML" || exit 6
  grep -qF 'target: "127.0.0.1:8445"' "$PAQET_TOML" || exit 7
  grep -qF '127.0.0.1:9001' "$PAQET_TOML" && exit 8
  grep -qF 'mode: "fast3"' "$PAQET_TOML" || exit 9
  grep -qF 'block: "salsa20"' "$PAQET_TOML" || exit 10

  st_json="$(cmd_status --json)"
  "$PY_BIN" - "$st_json" <<'PY' || exit 11
import json, sys
d = json.loads(sys.argv[1])
assert d["services"]["paqet"] == "yes"
fp = d["features"]["paqet"]
assert fp["configured"] is True and fp["active"] is True
assert fp["mode"] == "fast3" and fp["block"] == "salsa20"
assert fp["nodes"] == ["pq1"]
PY

  cmd_paqet off >/dev/null || exit 12
  [ ! -e "$PAQET_TOML" ] || exit 13
  grep -qF '[server.services.pq1]' "$SERVER_TOML" || exit 14
) || fail "ratholectl paqet client lifecycle failed ($?)"
ok "ratholectl paqet client YAML, server.toml exclusion, status --json & cleanup"

# ---- 4: rth_xray_scan_cover against live local TLS 1.3 + ALPN h2 server ----
SCAN_CERT="$D/scan-cert.pem"
SCAN_KEY="$D/scan-key.pem"
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$SCAN_KEY" -out "$SCAN_CERT" \
  -days 2 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1 \
  || fail "openssl req baraye scan server shekast khord"

SCAN_PORT_FILE="$D/scan.port"
"$PY_BIN" -u - "$SCAN_CERT" "$SCAN_KEY" "$SCAN_PORT_FILE" <<'PY' &
import socket, ssl, sys
cert_f, key_f, out_f = sys.argv[1:4]
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 0))
srv.listen(16)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(certfile=cert_f, keyfile=key_f)
try:
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
except Exception:
    pass
try:
    ctx.set_alpn_protocols(["h2", "http/1.1"])
except Exception:
    pass
with open(out_f, "w") as f:
    f.write(str(srv.getsockname()[1]))
while True:
    try:
        c, _ = srv.accept()
        try:
            with ctx.wrap_socket(c, server_side=True) as ss:
                pass
        except Exception:
            try:
                c.close()
            except OSError:
                pass
    except Exception:
        break
PY
PIDS+=($!)

SCAN_PORT=""
for _ in $(seq 1 30); do
  if [ -s "$SCAN_PORT_FILE" ]; then
    SCAN_PORT="$(cat "$SCAN_PORT_FILE")"
    break
  fi
  sleep 0.1
done
[ -n "$SCAN_PORT" ] || fail "local TLS scan fixture failed to start"

(
  set -uo pipefail
  # shellcheck disable=SC1091
  source "$REPO_ROOT/rathole-manager/common.sh"
  export RATHOLE_SCAN_TARGET_HOST=127.0.0.1 RATHOLE_SCAN_CAFILE="$SCAN_CERT"
  out="$(rth_xray_scan_cover --domains localhost,other.local --port "$SCAN_PORT" --timeout 2 --top 2 --json)"
  "$PY_BIN" - "$out" <<'PY' || exit 1
import json, sys
d = json.loads(sys.argv[1])
assert d["ok"] is True
assert d["recommended"] == "localhost"
res = {r["domain"]: r for r in d["results"]}
assert res["localhost"]["ok"] is True
assert res["localhost"]["tls_version"] == "TLSv1.3"
assert res["localhost"]["alpn"] == "h2"
assert res["other.local"]["ok"] is False
PY
) || fail "rth_xray_scan_cover live TLS 1.3 probe failed"
ok "rth_xray_scan_cover probes TLSv1.3 + ALPN h2 + ranks passing cover sites"

# ---- 5: install_paqet release URL keeps 'v' prefix and extracts binary cleanly (not paqet.tgz) ----
(
  set -uo pipefail
  PQ_FIX="$D/paqet-dl"
  PQ_CURL_BIN="$PQ_FIX/bin"
  PQ_PAYLOAD="$PQ_FIX/payload"
  PQ_BIN1="$PQ_FIX/out1"
  PQ_BIN2="$PQ_FIX/out2"
  PQ_URLS="$PQ_FIX/urls.log"
  case "$(uname -m)" in
    x86_64)  PQ_ARCH="amd64" ;;
    aarch64) PQ_ARCH="arm64" ;;
    *) echo "unsupported arch for install_paqet test" >&2; exit 0 ;;
  esac
  mkdir -p "$PQ_CURL_BIN" "$PQ_PAYLOAD/example" "$PQ_BIN1" "$PQ_BIN2"
  cat > "$PQ_PAYLOAD/paqet_linux_${PQ_ARCH}" <<'SH'
#!/usr/bin/env bash
echo "PAQET_EXTRACTED_OK"
SH
  chmod +x "$PQ_PAYLOAD/paqet_linux_${PQ_ARCH}"
  echo "# README" > "$PQ_PAYLOAD/README.md"
  echo "role: client" > "$PQ_PAYLOAD/example/client.yaml.example"
  tar -czf "$PQ_FIX/paqet.tar.gz" -C "$PQ_PAYLOAD" "paqet_linux_${PQ_ARCH}" "README.md" "example/client.yaml.example"

  cat > "$PQ_CURL_BIN/curl" <<SH
#!/usr/bin/env bash
set -euo pipefail
out=""
url=""
for a in "\$@"; do :; done
while [ \$# -gt 0 ]; do
  case "\$1" in
    -o) out="\${2:-}"; shift 2 ;;
    -*) case "\$1" in --config|--connect-timeout|--speed-limit|--speed-time|--retry) shift 2 ;; *) shift ;; esac ;;
    *) url="\$1"; shift ;;
  esac
done
printf '%s\n' "\$url" >> "$PQ_URLS"
cp "$PQ_FIX/paqet.tar.gz" "\$out"
SH
  chmod +x "$PQ_CURL_BIN/curl"
  export PATH="$PQ_CURL_BIN:$PATH"
  # shellcheck disable=SC1091
  source "$REPO_ROOT/rathole-manager/common.sh"

  # 1) Default version keeps leading 'v' in both tag and asset filename, and does not install .tgz
  (
    export RATHOLE_BIN_DIR="$PQ_BIN1"
    unset PAQET_VER || true
    install_paqet >/dev/null
  ) || exit 1
  grep -qE "/releases/download/v1\.0\.0-alpha\.14/paqet-linux-${PQ_ARCH}-v1\.0\.0-alpha\.14\.tar\.gz\$" "$PQ_URLS" || exit 2
  [ "$( "$PQ_BIN1/paqet" 2>/dev/null || true )" = "PAQET_EXTRACTED_OK" ] || exit 3

  # 2) PAQET_VER without leading 'v' normalizes to 'v<ver>' in tag & asset filename
  : > "$PQ_URLS"
  (
    export RATHOLE_BIN_DIR="$PQ_BIN2"
    export PAQET_VER="1.0.0-alpha.21"
    install_paqet >/dev/null
  ) || exit 4
  grep -qE "/releases/download/v1\.0\.0-alpha\.21/paqet-linux-${PQ_ARCH}-v1\.0\.0-alpha\.21\.tar\.gz\$" "$PQ_URLS" || exit 5
  [ "$( "$PQ_BIN2/paqet" 2>/dev/null || true )" = "PAQET_EXTRACTED_OK" ] || exit 6
) || fail "install_paqet release URL / extraction regression test failed"
ok "install_paqet keeps v-prefix in asset filename and installs extracted binary cleanly"
