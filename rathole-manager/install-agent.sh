#!/usr/bin/env bash
# rathole-agent installer — installs the pure Python stdlib REST & Reverse WebSocket agent
# on Iran panel or Foreign node for SSH-free (and port-free in --reverse mode) RatholeHub management.
set -euo pipefail

die(){ echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }
log(){ echo -e "\033[1;32m[INFO]\033[0m $*"; }

[ "${EUID:-$(id -u)}" -eq 0 ] || die "In script bayad ba root ejra shavad (sudo)."
command -v python3 >/dev/null 2>&1 || die "python3 nasb nist (apt install -y python3)."

PORT=8089
TOKEN=""
ROLE=""
REVERSE_URL=""
NAME=""
INSECURE_SSL=0
PROXY=""

while [ $# -gt 0 ]; do
  case "$1" in
    --port) [ $# -ge 2 ] || die "--port meghdar niaz darad."; PORT="$2"; shift 2 ;;
    --token) [ $# -ge 2 ] || die "--token meghdar niaz darad."; TOKEN="$2"; shift 2 ;;
    --role) [ $# -ge 2 ] || die "--role meghdar niaz darad."; ROLE="$2"; shift 2 ;;
    --reverse) [ $# -ge 2 ] || die "--reverse meghdar niaz darad."; REVERSE_URL="$2"; shift 2 ;;
    --name) [ $# -ge 2 ] || die "--name meghdar niaz darad."; NAME="$2"; shift 2 ;;
    --insecure-ssl) INSECURE_SSL=1; shift ;;
    --proxy) [ $# -ge 2 ] || die "--proxy meghdar niaz darad."; PROXY="$2"; shift 2 ;;
    *) die "argument nashenakhte: $1" ;;
  esac
done

[[ "$PORT" =~ ^[0-9]{1,5}$ ]] && ((10#$PORT >= 1 && 10#$PORT <= 65535)) || die "port namotabar."
[[ -z "$ROLE" || "$ROLE" = iran || "$ROLE" = node ]] || die "role namotabar."
[[ -z "$TOKEN" || ( "$TOKEN" =~ ^[A-Za-z0-9._~-]+$ && ${#TOKEN} -le 256 ) ]] || die "token namotabar."
if [ -n "$REVERSE_URL" ]; then
  [[ "$REVERSE_URL" =~ ^wss?://[^[:space:]\"\'\\\$]+$ && ${#REVERSE_URL} -le 512 ]] || die "address --reverse namotabar ast (bayad ws:// ya wss:// bashad)."
  [[ -n "$NAME" && "$NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$ ]] || die "dar halat --reverse, --name motabar elzami ast."
fi
if [ -n "$PROXY" ]; then
  [[ "$PROXY" =~ ^https?://[^[:space:]\"\'\\\$]+$ && ${#PROXY} -le 512 ]] || die "address --proxy namotabar ast (bayad http:// bashad)."
fi
umask 077

if [ -z "$ROLE" ]; then
  if [ -f "/etc/rathole/server.toml" ] || [ -f "/etc/rathole-manager/state.json" ]; then
    ROLE="iran"
  else
    ROLE="node"
  fi
fi

if [ -z "$TOKEN" ]; then
  if [ -f "/etc/rathole-agent/token" ]; then
    TOKEN="$(tr -d '[:space:]' < /etc/rathole-agent/token)"
  fi
  if [ -z "$TOKEN" ]; then
    if [ -n "$REVERSE_URL" ]; then
      die "dar halat --reverse, --token (gerefte-shode az Hub) elzami ast."
    fi
    TOKEN="$(python3 -c "import secrets; print(secrets.token_hex(24))")"
  fi
fi

mkdir -p /etc/rathole-agent
echo "$TOKEN" > /etc/rathole-agent/token
chmod 600 /etc/rathole-agent/token

mkdir -p /opt/rathole-manager /usr/local/share/rathole
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

_copy_py_asset(){
  local fname="$1" mode="$2" dest="/usr/local/share/rathole/$1"
  if [ -f "$SCRIPT_DIR/$fname" ] && [ "$SCRIPT_DIR/$fname" != "$dest" ]; then
    cp -f "$SCRIPT_DIR/$fname" "$dest"
  elif [ -f "$dest" ]; then
    :
  elif [ -f "/opt/rathole-manager/$fname" ]; then
    cp -f "/opt/rathole-manager/$fname" "$dest"
  elif [ -f "/opt/ratholehub/$fname" ]; then
    cp -f "/opt/ratholehub/$fname" "$dest"
  else
    return 1
  fi
  chmod "$mode" "$dest"
  cp -f "$dest" "/opt/rathole-manager/$fname" 2>/dev/null || true
}

_copy_py_asset "wsutil.py" 644 || [ -z "$REVERSE_URL" ] || die "File wsutil.py peyda nashod."
_copy_py_asset "ratholeagent.py" 755 || die "File ratholeagent.py peyda nashod."

PY_BIN="$(command -v python3)"
EXEC_CMD="${PY_BIN} /usr/local/share/rathole/ratholeagent.py"
if [ -n "$REVERSE_URL" ]; then
  EXEC_CMD="${EXEC_CMD} --reverse ${REVERSE_URL} --name ${NAME} --role ${ROLE}"
  [ "$INSECURE_SSL" -eq 1 ] && EXEC_CMD="${EXEC_CMD} --insecure-ssl"
  [ -n "$PROXY" ] && EXEC_CMD="${EXEC_CMD} --proxy ${PROXY}"
else
  EXEC_CMD="${EXEC_CMD} --port ${PORT} --role ${ROLE}"
fi

cat > /etc/systemd/system/rathole-agent.service <<UNIT
[Unit]
Description=rathole REST & Reverse WebSocket Agent Daemon
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
KillMode=process
LimitNOFILE=65535
ExecStart=${EXEC_CMD}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
chmod 644 /etc/systemd/system/rathole-agent.service

systemctl daemon-reload
systemctl enable --now rathole-agent >/dev/null 2>&1
systemctl restart rathole-agent

IP="$(curl -fsSL --connect-timeout 3 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"

echo
echo
log "════════════════════════════════════════════════════════════════"
log "  Rathole Agent ba movafaghiat nasb va faal shod!"
log "════════════════════════════════════════════════════════════════"
echo "  Role:      $ROLE"
if [ -n "$REVERSE_URL" ]; then
  echo "  Mode:      Reverse WebSocket (outbound)"
  echo "  Server:    $NAME"
  echo "  Hub WS:    $REVERSE_URL"
  echo "  Egress IP: ${IP:-unknown}"
else
  echo "  Port:      $PORT"
  echo "  API URL:   http://${IP:-127.0.0.1}:${PORT}"
  echo "  Token:     $TOKEN"
  echo
  echo "Dar panel RatholeHub -> Add Server:"
  echo "  - Connection: Agent REST API"
  echo "  - API URL:    http://${IP:-127.0.0.1}:${PORT}"
  echo "  - Token:      $TOKEN"
fi
echo
echo "Kanal-e Telegram (etela' rasani va poshtibani):  https://t.me/l8PY4NET"
log "════════════════════════════════════════════════════════════════"
