#!/usr/bin/env bash
# Reproduce/fix the actual lock failure using dedicated transient units.
set -euo pipefail
if [ "${RATHOLE_REAL_SYSTEMD:-}" != 1 ]; then echo 'skip - set RATHOLE_REAL_SYSTEMD=1'; exit 0; fi
BIN="${RATHOLE_TEST_BIN:?set RATHOLE_TEST_BIN}"
D="$(mktemp -d /etc/rathole/rathole-lab.XXXXXX)"
UNIT="rathole-lab-$(basename "$D" | tr . -)"
cleanup(){
 systemctl stop "$UNIT-bad.service" "$UNIT-good.service" >/dev/null 2>&1 || true
 systemctl reset-failed "$UNIT-bad.service" "$UNIT-good.service" >/dev/null 2>&1 || true
 case "$D" in /etc/rathole/rathole-lab.*) rm -rf -- "$D" ;; esac
}
trap cleanup EXIT INT TERM
cat > "$D/server.toml" <<'CONF'
[server]
bind_addr = "127.0.0.1:0"
[server.transport]
type = "tcp"
[server.services.test]
token = "integration-token"
bind_addr = "127.0.0.1:0"
CONF
systemd-run --quiet --unit="$UNIT-bad" --property=ProtectSystem=full --property=RuntimeMaxSec=10 "$BIN" "$D/server.toml"
sleep 1
if systemctl is-active --quiet "$UNIT-bad"; then echo 'FAIL - lock unexpectedly writable'; exit 1; fi
journalctl -u "$UNIT-bad" --no-pager | grep -q 'Read-only file system'
echo 'ok - reproduced configuration lock error under ProtectSystem=full'
systemd-run --quiet --unit="$UNIT-good" --property=ProtectSystem=full --property=ReadWritePaths=/etc/rathole --property=RuntimeMaxSec=10 "$BIN" "$D/server.toml"
sleep 1
systemctl is-active --quiet "$UNIT-good"
echo 'ok - scoped ReadWritePaths fixes the actual systemd lock failure'
