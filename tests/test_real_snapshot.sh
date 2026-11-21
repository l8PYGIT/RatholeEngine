#!/usr/bin/env bash
# Actual tar snapshot/restore of temporary fixtures, with service control stubbed.
set -euo pipefail
if [ "${RATHOLE_REAL_SNAPSHOT:-}" != 1 ]; then echo 'skip - set RATHOLE_REAL_SNAPSHOT=1'; exit 0; fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
D="$(mktemp -d /tmp/rathole-snapshot-lab.XXXXXX)"
cleanup(){ case "$D" in /tmp/rathole-snapshot-lab.*) rm -rf -- "$D" ;; esac; }
trap cleanup EXIT INT TERM
sed '/# ==================== jarian-e asli/,$d' "$ROOT/rathole-manager/update.sh" > "$D/functions.sh"
set --
source "$D/functions.sh"
mkdir -p "$D/fixture"
printf 'original config\n' > "$D/fixture/node.env"
printf 'original unit\n' > "$D/fixture/node.service"
cp "$D/fixture/node.env" "$D/expected.env"
cp "$D/fixture/node.service" "$D/expected.service"
BACKUP_ROOT="$D/backups"; RETENTION=7
snapshot_paths(){ printf '%s\n' "$D/fixture/node.env" "$D/fixture/node.service"; }
systemctl(){ :; }
restart_services(){ :; }
CHECK_FAIL=0
health_check(){ [ "$CHECK_FAIL" = 0 ] && cmp "$D/expected.env" "$D/fixture/node.env" && cmp "$D/expected.service" "$D/fixture/node.service"; }
SNAP="$(snapshot_now node)"
# Safety: only the two fixture files may be restored under /.
while IFS= read -r member; do
 case "$member" in "${D#/}/fixture/node.env"|"${D#/}/fixture/node.service") : ;; *) echo 'FAIL - unsafe snapshot path'; exit 1 ;; esac
done < <(tar -tzf "$SNAP/backup.tar.gz")
printf 'broken config\n' > "$D/fixture/node.env"
printf 'broken unit\n' > "$D/fixture/node.service"
rollback_to "$SNAP"
health_check
echo 'ok - real snapshot restores config and unit bytes'
CHECK_FAIL=1
if rollback_to "$SNAP"; then echo 'FAIL - unhealthy rollback reported success'; exit 1; fi
echo 'ok - rollback reports health-check failure'
