"""Sandbox regressions: never executes real install/systemctl operations."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which('bash') if os.name != 'nt' else r'C:\Program Files\Git\bin\bash.exe'


def run_bash(source):
    return subprocess.run([BASH, '-s'], input=source, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=15)


def update_source():
    source = (ROOT / 'rathole-manager/update.sh').read_text(encoding='utf-8')
    return source.replace('[ "$(id -u)" -eq 0 ] || die', 'true || die')


class LifecycleTests(unittest.TestCase):
    def test_apply_failure_rolls_back_and_stops_remaining_mutations(self):
        source = update_source()
        split = source.index('# ==================== jarian-e asli')
        script = source[:split] + '''
detect_roles(){ PANEL=1; NODE=0; HUB=0; }
downgrade_guard(){ :; }
snapshot_now(){ echo /sandbox/snapshot; }
apply_update(){ echo APPLY; false; echo BAD_CONTINUE; }
health_check(){ return 0; }
rollback_to(){ echo ROLLED_BACK; }
''' + source[split:]
        result = run_bash(script)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ROLLED_BACK', result.stdout)
        self.assertNotIn('BAD_CONTINUE', result.stdout)

    def test_unhealthy_no_rollback_returns_failure(self):
        source = update_source()
        split = source.index('# ==================== jarian-e asli')
        script = source[:split] + '''
AUTO_ROLLBACK=0
detect_roles(){ PANEL=1; NODE=0; HUB=0; }
downgrade_guard(){ :; }
snapshot_now(){ echo /sandbox/snapshot; }
apply_update(){ :; }
health_check(){ return 1; }
''' + source[split:]
        result = run_bash(script)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('beroozresani/takmil kamel shod', result.stdout)

    def test_failed_snapshot_stops_update(self):
        source = update_source()
        split = source.index('# ==================== jarian-e asli')
        script = source[:split] + '''
detect_roles(){ PANEL=1; NODE=0; HUB=0; }
downgrade_guard(){ :; }
snapshot_now(){ return 1; }
apply_update(){ echo BAD_APPLY; }
''' + source[split:]
        result = run_bash(script)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('BAD_APPLY', result.stdout)

    def test_snapshot_tar_failure_is_not_accepted(self):
        source = update_source().split('# ==================== jarian-e asli')[0]
        script = source + '''
BACKUP_ROOT="$(mktemp -d)"
trap 'rm -rf "$BACKUP_ROOT"' EXIT
snapshot_paths(){ echo /sandbox/source; }
tar(){ return 1; }
prune_snapshots(){ echo BAD_PRUNE >&2; }
snapshot_now panel
'''
        result = run_bash(script)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('BAD_PRUNE', result.stderr)
        self.assertNotIn('snapshot gereft', result.stderr)

    def test_node_without_api_reaches_apply(self):
        source = (ROOT / 'rathole-manager/install-node.sh').read_text(encoding='utf-8')
        source = source[source.index('# ---------- nasb tazh ----------'):]
        script = '''set -euo pipefail
task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
SERVER=example.org:443 NAME=node1 TOKEN=secret INBOUND=2087
TLS_HOSTNAME= TLS_TRUSTED_ROOT= RATHOLE_VERSION=v0.5.0 API_TOKEN= API_INBOUND=
log(){ :; }
ratholenode(){ echo APPLIED; }
''' + source.replace('/etc/rathole/', '$task_dir/')
        result = run_bash(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('APPLIED', result.stdout)

    def test_node_prefers_bundled_core_without_network(self):
        source = (ROOT / 'rathole-manager/install-node.sh').read_text(encoding='utf-8')
        source = source[:source.index('mkdir -p /etc/rathole')]
        source = source.replace('[ "$(id -u)" -eq 0 ] || die', 'true || die')
        source = source.replace('SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"', 'SCRIPT_DIR="$task_dir"')
        script = '''task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
mkdir -p "$task_dir/core"
touch "$task_dir/core/SHA256SUMS"
printf 'echo BUNDLED_CORE\\n' > "$task_dir/core-install.sh"
apt-get(){ echo BAD_NETWORK; return 1; }
curl(){ echo BAD_NETWORK; return 1; }
uname(){ echo x86_64; }
set -- --server example.org:443 --name node1 --token secret --inbound-port 2087
''' + source
        result = run_bash(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('BUNDLED_CORE', result.stdout)
        self.assertNotIn('BAD_NETWORK', result.stdout)

    def test_update_refreshes_legacy_agent_executable(self):
        source = update_source()
        start = source.index('  # agent (')
        end = source.index('  # core-e backhaul', start)
        script = '''set -euo pipefail
task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
mkdir -p "$task_dir/src" "$task_dir/opt/rathole-manager"
printf new > "$task_dir/src/ratholeagent.py"
printf old > "$task_dir/opt/rathole-manager/ratholeagent.py"
SCRIPT_DIR="$task_dir/src"
''' + source[start:end].replace('/usr/local/share/rathole', '$task_dir/share').replace('/opt/rathole-manager', '$task_dir/opt/rathole-manager') + '''
cat "$task_dir/opt/rathole-manager/ratholeagent.py"
'''
        result = run_bash(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'new')

    def test_uninstall_stops_extra_transport_units(self):
        for role, units in [('panel', ['frps.service', 'rathole-kcp-server.service', 'rathole-agent.service']),
                            ('node', ['frpc.service', 'rathole-kcp-up-west.service',
                                      'rathole-client@west.service', 'rathole-watchdog.timer', 'rathole-agent.service'])]:
            with self.subTest(role=role):
                source = (ROOT / f'rathole-manager/uninstall-{role}.sh').read_text(encoding='utf-8')
                source = source[source.index('# ---------- tavaghof va hazf service'):]
                source = source[:source.index('# ----------', 10)]
                script = '''set -euo pipefail
task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
mkdir -p "$task_dir/units"
log(){ :; }
systemctl(){ echo "$*"; }
'''
                script += '\n'.join(f'touch "$task_dir/units/{unit}"' for unit in units) + '\n'
                # Only the unit teardown section is executed; binary/config rm is stubbed.
                script += 'rm(){ :; }\n' + source.replace('/etc/systemd/system', '$task_dir/units')
                result = run_bash(script)
                self.assertEqual(result.returncode, 0, result.stderr)
                for unit in units:
                    self.assertIn('disable --now '+unit, result.stdout)

    def test_frp_only_node_health_checks_frpc(self):
        source = update_source().split('# ==================== jarian-e asli')[0]
        script = '''task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
printf 'TUNNEL=frp\\n' > "$task_dir/node.env"
systemctl(){ [ "$*" = 'is-active --quiet frpc' ]; }
''' + source.replace('/etc/rathole/node.env', '$task_dir/node.env') + '\nhealth_check node\n'
        result = run_bash(script)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_core_checksum_must_cover_selected_binary(self):
        source = (ROOT / 'rathole-manager/core-install.sh').read_text(encoding='utf-8')
        script = '''task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
mkdir -p "$task_dir/x86_64-unknown-linux-gnu"
printf unchecked > "$task_dir/x86_64-unknown-linux-gnu/rathole"
printf checked > "$task_dir/other"
(cd "$task_dir" && sha256sum other > SHA256SUMS)
RATHOLE_CORE_DIR="$task_dir"
uname(){ echo x86_64; }
set -- --verify-only
''' + source
        result = run_bash(script)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('verify OK', result.stdout)

    def test_panel_nginx_failure_stops_installation(self):
        source = (ROOT / 'rathole-manager/install-panel.sh').read_text(encoding='utf-8')
        source = source[source.index('# tst va reload nhaii nginx'):source.index('# ---------- faalsazi service')]
        result = run_bash('''set -euo pipefail
log(){ :; }
err(){ echo "$*" >&2; }
die(){ err "$*"; exit 1; }
nginx(){ return 1; }
''' + source + '\necho BAD_SUCCESS\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('BAD_SUCCESS', result.stdout)

    def test_rollback_restarts_enabled_transport_units(self):
        source = update_source().split('# ==================== jarian-e asli')[0]
        script = '''task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
mkdir -p "$task_dir/units"
touch "$task_dir/units/frpc.service" "$task_dir/units/rathole-kcp-up-west.service"
systemctl(){
  case "$1" in
    is-enabled) return 0;;
    list-unit-files) return 0;;
    restart) echo "$*";;
  esac
}
''' + source.replace('/etc/systemd/system', '$task_dir/units') + '\nrestart_services node\n'
        result = run_bash(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('restart frpc.service', result.stdout)
        self.assertIn('restart rathole-kcp-up-west.service', result.stdout)

    def test_backhaul_only_node_health_checks_backhaul(self):
        source = update_source().split('# ==================== jarian-e asli')[0]
        script = '''task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
printf 'TUNNEL=websocket\\n' > "$task_dir/node.env"
printf '' > "$task_dir/services.conf"
printf 'node1|token|2087\\n' > "$task_dir/bh-services.conf"
systemctl(){ [ "$*" = 'is-active --quiet rathole-backhaul-client' ]; }
''' + source.replace('/etc/rathole/', '$task_dir/') + '\nhealth_check node\n'
        result = run_bash(script)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_agent_units_keep_token_only_in_private_file(self):
        for filename in ['install-agent.sh', 'ratholectl', 'ratholenode']:
            with self.subTest(installer=filename):
                source = (ROOT / 'rathole-manager' / filename).read_text(encoding='utf-8')
                if filename != 'install-agent.sh':
                    start = source.index('cmd_agent(){')
                    source = source[start:source.index('\n}\n', start)+3]
                    invoke = 'AGENT_SVC=rathole-agent; cmd_agent on 8089 private_token_0123456789'
                else:
                    source = source.replace('[ "${EUID:-$(id -u)}" -eq 0 ] || die', 'true || die')
                    invoke = ''
                source = source.replace('/etc/', '$task_dir/etc/').replace('/usr/local/share/', '$task_dir/share/').replace('/opt/', '$task_dir/opt/')
                script = '''set -euo pipefail
task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
mkdir -p "$task_dir/etc/systemd/system" "$task_dir/share/rathole" "$task_dir/opt/rathole-manager"
touch "$task_dir/share/rathole/ratholeagent.py" "$task_dir/opt/rathole-manager/ratholeagent.py"
systemctl(){ :; }
curl(){ echo 127.0.0.1; }
need_root(){ :; }
log(){ :; }
c_y(){ echo "$*"; }
detect_ip(){ echo 127.0.0.1; }
die(){ echo "$*" >&2; exit 1; }
set -- --token private_token_0123456789
''' + source + '\n' + invoke + '''
echo UNIT_CONTENT
cat "$task_dir/etc/systemd/system/rathole-agent.service"
echo TOKEN_MODE
stat -c %a "$task_dir/etc/rathole-agent/token"
'''
                result = run_bash(script)
                self.assertEqual(result.returncode, 0, result.stderr)
                unit = result.stdout.split('UNIT_CONTENT\n')[1].split('TOKEN_MODE\n')[0]
                self.assertNotIn('private_token_0123456789', unit)
                self.assertNotIn('RATHOLE_AGENT_TOKEN=', unit)
                if os.name != 'nt':  # Git Bash reports emulated modes on NTFS.
                    self.assertIn('TOKEN_MODE\n600', result.stdout)

    def test_update_removes_legacy_agent_unit_token(self):
        source = update_source()
        start = source.index('  if [ -f /etc/systemd/system/rathole-agent.service ]; then')
        source = source[start:source.index('  # --- samt hub ---', start)]
        script = '''set -euo pipefail
task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
mkdir -p "$task_dir/etc/systemd/system"
printf '[Service]\\nEnvironment=RATHOLE_AGENT_TOKEN=private_token_0123456789\\nExecStart=/usr/bin/python3 agent.py\\n' > "$task_dir/etc/systemd/system/rathole-agent.service"
systemctl(){ :; }
''' + source.replace('/etc/', '$task_dir/etc/') + '''
cat "$task_dir/etc/systemd/system/rathole-agent.service"
'''
        result = run_bash(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('private_token_0123456789', result.stdout)
        self.assertIn('ExecStart=', result.stdout)

    def test_cli_agent_rejects_unit_injection_before_mutating(self):
        for filename in ['ratholectl', 'ratholenode']:
            for args in ["on $'8089\\nExecStart=/bin/false' valid_token_0123456789", "on 8089 $'token\\nInjected=value'"]:
                with self.subTest(installer=filename, args=args):
                    source = (ROOT / 'rathole-manager' / filename).read_text(encoding='utf-8')
                    start = source.index('cmd_agent(){')
                    source = source[start:source.index('\n}\n', start)+3]
                    script = '''set -euo pipefail
need_root(){ :; }
die(){ echo "$*" >&2; exit 1; }
log(){ :; }
mkdir(){ echo BAD_WRITE; exit 0; }
curl(){ echo BAD_WRITE; exit 0; }
''' + source + '\ncmd_agent '+args+'\n'
                    result = run_bash(script)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('BAD_WRITE', result.stdout)

    def test_rollback_restarts_only_selected_primary_lane(self):
        for tunnel, backhaul, expected in [('frp', False, 'frpc'), ('ws', True, 'rathole-backhaul-client')]:
            with self.subTest(tunnel=tunnel, backhaul=backhaul):
                source = update_source().split('# ==================== jarian-e asli')[0]
                script = '''task_dir="$(mktemp -d)"
trap 'command rm -rf "$task_dir"' EXIT
systemctl(){
  case "$1" in
    list-unit-files) return 0;;
    restart) echo "$*";;
  esac
}
'''
                script += f'printf "TUNNEL={tunnel}\\n" > "$task_dir/node.env"\n'
                script += 'touch "$task_dir/services.conf"\n'
                if backhaul:
                    script += 'printf "node1|token|2087\\n" > "$task_dir/bh-services.conf"\n'
                script += source.replace('/etc/rathole/', '$task_dir/') + '\nrestart_services node\n'
                result = run_bash(script)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('restart '+expected, result.stdout)
                self.assertNotIn('restart rathole-client\n', result.stdout)

    def test_agent_rejects_unit_injection_before_writing(self):
        source = (ROOT / 'rathole-manager/install-agent.sh').read_text(encoding='utf-8')
        source = source[:source.index('if [ -z "$ROLE" ]; then')]
        source = source.replace('[ "${EUID:-$(id -u)}" -eq 0 ] || die', 'true || die')
        script = 'id(){ echo 0; }; EUID_TEST=0\n' + source + '\necho BAD_ACCEPTED\n'
        # Validating explicit input must precede role discovery and filesystem writes.
        result = run_bash('set -- --port '+"$'8089\\nExecStart=/bin/false'"+' --role node\n'+script)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('BAD_ACCEPTED', result.stdout)


if __name__ == '__main__':
    unittest.main()
