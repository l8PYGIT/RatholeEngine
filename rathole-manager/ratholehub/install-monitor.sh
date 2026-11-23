#!/usr/bin/env bash
# install-monitor.sh — nasb daemon-e mostaghel-e ratholemonitor.service va bot-e Telegram.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

c_g(){ printf '\033[1;32m%s\033[0m' "$*"; }
c_y(){ printf '\033[1;33m%s\033[0m' "$*"; }
log(){ printf '%s %s\n' "$(c_g '[+]')" "$*"; }
warn(){ printf '%s %s\n' "$(c_y '[*]')" "$*"; }
die(){ printf '[!] %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "ba root ejra kon (sudo)."
command -v python3 >/dev/null 2>&1 || die "python3 lazem ast (apt install -y python3)."

ENABLE_NOW=0
for arg in "$@"; do
  case "$arg" in
    --enable) ENABLE_NOW=1 ;;
    *) die "opt-e nashenakhte: $arg (estefade: install-monitor.sh [--enable])" ;;
  esac
done

APP_DIR=/opt/ratholehub
CONF_DIR=/etc/ratholehub
STATE_DIR=/var/lib/ratholehub

mkdir -p "$APP_DIR" "$CONF_DIR" "$STATE_DIR"
chmod 755 "$CONF_DIR" 2>/dev/null || true
chmod 700 "$STATE_DIR" 2>/dev/null || true

for f in tg_relay.py monitor.py; do
  [ -f "$SCRIPT_DIR/$f" ] || die "file peyda nashod: $SCRIPT_DIR/$f"
  sed -i 's/\r$//' "$SCRIPT_DIR/$f"
done
install -m644 "$SCRIPT_DIR/tg_relay.py" "$APP_DIR/tg_relay.py"
install -m755 "$SCRIPT_DIR/monitor.py" "$APP_DIR/monitor.py"
if [ -f "$SCRIPT_DIR/ssh_proxy.py" ]; then
  sed -i 's/\r$//' "$SCRIPT_DIR/ssh_proxy.py"
  install -m644 "$SCRIPT_DIR/ssh_proxy.py" "$APP_DIR/ssh_proxy.py"
fi

if [ ! -f "$CONF_DIR/monitor.json" ]; then
  (
    umask 077
    cat > "$CONF_DIR/monitor.json" <<'JSON'
{
  "enabled": false,
  "bot_token": "",
  "allowed_chat_ids": [],
  "hub_url": "http://127.0.0.1:8088",
  "hub_token": "",
  "relay_mode": "auto",
  "proxy": "",
  "poll_interval_sec": 60,
  "fail_threshold": 3,
  "recover_threshold": 2,
  "cooldown_sec": 300,
  "cert_warn_days": 14,
  "allow_remote_actions": true,
  "bot_enabled": true,
  "api_base": "https://api.telegram.org"
}
JSON
  )
  chmod 600 "$CONF_DIR/monitor.json"
  log "config sakhte shod: $CONF_DIR/monitor.json"
else
  chmod 600 "$CONF_DIR/monitor.json" 2>/dev/null || true
  warn "monitor.json mojood ast; dast nakhord."
fi

cat > /etc/systemd/system/ratholemonitor.service <<UNIT
[Unit]
Description=RatholeEngine Monitor & Operational Telegram Bot
After=network.target ratholehub.service
Wants=ratholehub.service

[Service]
Type=simple
Environment=RATHOLEMON_CONF=$CONF_DIR/monitor.json
Environment=RATHOLEMON_STATE=$STATE_DIR/monitor-state.json
Environment=RATHOLEHUB_CONF=$CONF_DIR/config.json
Environment=RATHOLEHUB_INV=$CONF_DIR/inventory.json
ExecStart=/usr/bin/python3 $APP_DIR/monitor.py run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
log "service sakhte shod: /etc/systemd/system/ratholemonitor.service"

CONF_ENABLED=0
if grep -qE '"enabled"[[:space:]]*:[[:space:]]*true' "$CONF_DIR/monitor.json" 2>/dev/null \
  && grep -qE '"bot_token"[[:space:]]*:[[:space:]]*"[^"]+"' "$CONF_DIR/monitor.json" 2>/dev/null; then
  CONF_ENABLED=1
fi

if [ "$ENABLE_NOW" -eq 1 ] || [ "$CONF_ENABLED" -eq 1 ]; then
  systemctl enable --now ratholemonitor
  systemctl restart ratholemonitor
  log "ratholemonitor faal va shoru shod."
else
  warn "ratholemonitor amade ast (baraye shoru: az Settings dar Hub panel ya 'systemctl enable --now ratholemonitor')."
fi
