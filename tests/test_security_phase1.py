"""Phase 1 critical security & operational regression tests (C5-C9)."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which('bash') if os.name != 'nt' else r'C:\Program Files\Git\bin\bash.exe'


def run_bash(script):
    env = os.environ.copy()
    env['MSYS_NO_PATHCONV'] = '1'
    env['MSYS2_ARG_CONV_EXCL'] = '*'
    preamble = ''
    if os.name == 'nt':
        preamble = 'jq(){ command jq "$@" | tr -d "\\r"; }\n'
    return subprocess.run(
        [BASH, '-s'],
        input=preamble + script,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        start_new_session=(os.name != 'nt'),
        timeout=45,
    )


class Phase1BashSecurityTests(unittest.TestCase):
    def test_rth_redact_hides_noise_frp_kcp_secrets(self):
        script = '''set -uo pipefail
source rathole-manager/common.sh
rth_redact <<'EOF'
{"noise_privkey":"noise_secret_priv_123","frp_token":"frp_secret_tok_456","kcp":{"key":"kcp_json_secret_789"}}
auth.token = "frp_toml_secret_abc"
FRP_TOKEN=frp_env_secret_def
ExecStart=/usr/local/bin/kcptun-server -l :443 -t 127.0.0.1:2333 -key kcp_cli_secret_xyz -crypt aes-128
EOF
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stderr)
        for secret in [
            'noise_secret_priv_123',
            'frp_secret_tok_456',
            'kcp_json_secret_789',
            'frp_toml_secret_abc',
            'frp_env_secret_def',
            'kcp_cli_secret_xyz',
        ]:
            self.assertNotIn(secret, res.stdout)
        self.assertEqual(res.stdout.count('***REDACTED***'), 6, res.stdout)

    def test_control_path_rotate_dry_run_does_not_mutate(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLECTL_LIB_ONLY=1
source rathole-manager/ratholectl
STATE="$task_dir/state.json"
cat > "$STATE" <<'JSON'
{"domain":"x.test","cert_fullchain":"/fc","cert_key":"/k","control_port":2333,"control_path":"/_rh/00112233445566778899aabbccddeeff","fake_port":8080,"sub_port":2096,"data_port_start":1001,"api_port_start":7001,"nodes":[]}
JSON
cp "$STATE" "$task_dir/state.before"
need_root(){ :; }
rathole_supports_ws_path(){ return 0; }
main control-path rotate --dry-run
diff -u "$task_dir/state.before" "$STATE" && echo STATE_UNCHANGED
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn('[DRY-RUN]', res.stdout)
        self.assertIn('STATE_UNCHANGED', res.stdout)

    def test_plain_nginx_conf_includes_control_path(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLECTL_LIB_ONLY=1
source rathole-manager/ratholectl
STATE="$task_dir/state.json"
NGINX_CONF="$task_dir/rathole.conf"
STREAM_CONF="$task_dir/stream.conf"
: > "$task_dir/fc.pem"
: > "$task_dir/key.pem"
jq -n --arg fc "$task_dir/fc.pem" --arg k "$task_dir/key.pem" --arg nc "$NGINX_CONF" \
  '{domain:"x.test",cert_fullchain:$fc,cert_key:$k,nginx_conf:$nc,control_port:2333,control_path:"/_rh/deadbeefdeadbeef0011223344556677",fake_port:8080,sub_port:2096,plain_port:8880,data_port_start:1001,api_port_start:7001,nodes:[]}' > "$STATE"
gen_nginx_conf
cat "$NGINX_CONF"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stderr)
        # Extract the plain HTTP server block (listen 8880;)
        marker = 'listen 8880;'
        self.assertIn(marker, res.stdout)
        plain_block = res.stdout[res.stdout.index(marker):]
        plain_block = plain_block[:plain_block.index('\n}\n') + 3]
        self.assertIn('location = /_rh/deadbeefdeadbeef0011223344556677', plain_block)

    def test_cli_rejects_injection_inputs(self):
        ctl_cases = [
            'cmd_set fullchain "/etc/ssl/a; evil"',
            'cmd_set key $\'/etc/ssl/k\\nssl_protocols TLSv1;\'',
            'cmd_set nginx-conf "/etc/passwd"',
            'cmd_set nginx-conf "/etc/nginx/../shadow"',
            'cmd_fakeweb start $\'8080\\nExecStartPre=/bin/id\'',
        ]
        for call in ctl_cases:
            with self.subTest(call=call):
                script = f'''set -uo pipefail
task_dir="$(mktemp -d)"
command -v cygpath >/dev/null 2>&1 && task_dir="$(cygpath -m "$task_dir")"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLECTL_LIB_ONLY=1
source rathole-manager/ratholectl
STATE="$task_dir/state.json"
echo '{{"domain":"x.test","nodes":[]}}' > "$STATE"
need_root(){{ :; }}
regenerate(){{ echo BAD_MUTATION; }}
systemctl(){{ echo BAD_MUTATION; }}
state_set(){{ echo BAD_MUTATION; }}
{call}
'''
                res = run_bash(script)
                self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
                self.assertNotIn('BAD_MUTATION', res.stdout)

        node_cases = [
            'cmd_kcp_on "1.2.3.4:443" $\'key\\nExecStartPre=/bin/id\' balanced',
            'cmd_kcp_on $\'1.2.3.4\\nBad:443\' validkey balanced',
            'cmd_plain_on "1.2.3.4:8880;id"',
            'cmd_noise_on "1.2.3.4:2334" "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=" $\'pat\\nfoo\'',
            'cmd_fakeweb start "8081 --bad"',
        ]
        for call in node_cases:
            with self.subTest(call=call):
                script = f'''set -uo pipefail
export RATHOLENODE_LIB_ONLY=1
source rathole-manager/ratholenode
need_root(){{ :; }}
install_kcptun_client(){{ echo BAD_MUTATION; }}
systemctl(){{ echo BAD_MUTATION; }}
env_set(){{ echo BAD_MUTATION; }}
kv_set(){{ echo BAD_MUTATION; }}
gen_client(){{ echo BAD_MUTATION; }}
{call}
'''
                res = run_bash(script)
                self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)
                self.assertNotIn('BAD_MUTATION', res.stdout)

    def test_adaptive_load_env_never_executes_shell(self):
        script = '''set -uo pipefail
task_dir="$(mktemp -d)"
trap 'rm -rf "$task_dir"' EXIT
export RATHOLENODE_LIB_ONLY=1
source rathole-manager/ratholenode
ADAPTIVE_ENV="$task_dir/adaptive.env"
cat > "$ADAPTIVE_ENV" <<EOF
ADAPTIVE_ENABLED=\\$(touch "$task_dir/pwned")
ALLOW_INSECURE=1
EOF
adaptive_load_env
[ ! -e "$task_dir/pwned" ] && echo NOT_EXECUTED
echo "ENABLED=$ADAPTIVE_ENABLED ALLOW=$ALLOW_INSECURE"
'''
        res = run_bash(script)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('NOT_EXECUTED', res.stdout)
        self.assertIn('ENABLED=0 ALLOW=1', res.stdout)


if __name__ == '__main__':
    unittest.main()
