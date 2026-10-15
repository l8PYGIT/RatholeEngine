#!/usr/bin/env bash
# rathole-agent installer — installs the pure Python stdlib REST API agent
# on Iran panel or Foreign node for SSH-free RatholeHub management.
set -euo pipefail

die(){ echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }
log(){ echo -e "\033[1;32m[INFO]\033[0m $*"; }

[ "${EUID:-$(id -u)}" -eq 0 ] || die "In script bayad ba root ejra shavad (sudo)."
command -v python3 >/dev/null 2>&1 || die "python3 nasb nist (apt install -y python3)."

PORT=8089
TOKEN=""
ROLE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --port) [ $# -ge 2 ] || die "--port meghdar niaz darad."; PORT="$2"; shift 2 ;;
    --token) [ $# -ge 2 ] || die "--token meghdar niaz darad."; TOKEN="$2"; shift 2 ;;
    --role) [ $# -ge 2 ] || die "--role meghdar niaz darad."; ROLE="$2"; shift 2 ;;
    *) die "argument nashenakhte: $1" ;;
  esac
done

[[ "$PORT" =~ ^[0-9]{1,5}$ ]] && ((10#$PORT >= 1 && 10#$PORT <= 65535)) || die "port namotabar."
[[ -z "$ROLE" || "$ROLE" = iran || "$ROLE" = node ]] || die "role namotabar."
[[ -z "$TOKEN" || "$TOKEN" =~ ^[A-Za-z0-9._~-]+$ && ${#TOKEN} -le 256 ]] || die "token namotabar."
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
    TOKEN="$(cat /etc/rathole-agent/token | tr -d '[:space:]')"
  fi
  if [ -z "$TOKEN" ]; then
    TOKEN="$(python3 -c "import secrets; print(secrets.token_hex(24))")"
  fi
fi

mkdir -p /etc/rathole-agent
echo "$TOKEN" > /etc/rathole-agent/token
chmod 600 /etc/rathole-agent/token

mkdir -p /opt/rathole-manager
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/ratholeagent.py" ]; then
  cp "$SCRIPT_DIR/ratholeagent.py" /opt/rathole-manager/ratholeagent.py
elif [ -f "/opt/rathole-manager/ratholeagent.py" ]; then
  : # already present
else
  die "File ratholeagent.py dar $SCRIPT_DIR peyda nashod."
fi
chmod 755 /opt/rathole-manager/ratholeagent.py

cat > /etc/systemd/system/rathole-agent.service <<UNIT
[Unit]
Description=rathole REST Agent Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/rathole-manager/ratholeagent.py --port ${PORT} --role ${ROLE}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now rathole-agent >/dev/null 2>&1
systemctl restart rathole-agent

IP="$(curl -fsSL --connect-timeout 3 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"

echo
log "════════════════════════════════════════════════════════════════"
log "  Rathole Agent ba movafaghiat nasb va faal shod!"
log "════════════════════════════════════════════════════════════════"
echo "  Role:      $ROLE"
echo "  Port:      $PORT"
echo "  API URL:   http://${IP:-127.0.0.1}:${PORT}"
echo "  Token:     $TOKEN"
echo
echo "Dar panel RatholeHub -> Add Server:"
echo "  - Connection: Agent REST API"
echo "  - API URL:    http://${IP:-127.0.0.1}:${PORT}"
echo "  - Token:      $TOKEN"
log "════════════════════════════════════════════════════════════════"
