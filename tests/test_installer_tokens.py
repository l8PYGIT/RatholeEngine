import os, pathlib, shutil, subprocess, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
BASH = shutil.which("bash") if os.name != "nt" else "C:/Program Files/Git/bin/bash.exe"
class InstallerTokenTests(unittest.TestCase):
    def test_node_separator_preserves_tunnel_token(self):
        source = (ROOT / "install.sh").read_text(encoding="utf-8")
        parser = source[source.index("RAW_ARGC=$#"):source.index("# zir-e `curl | sudo bash`")]
        script = 'GH_TOKEN=github-secret; REL=latest; die(){ exit 1; };\n' + parser + '\nprintf "%s\\n" "$GH_TOKEN" "$@"\n'
        run = subprocess.run([BASH, "-c", script, "test", "--node", "--", "--server", "panel:443", "--token", "tunnel-secret", "--inbound-port", "82"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.splitlines(), ["github-secret", "--node", "--", "--server", "panel:443", "--token", "tunnel-secret", "--inbound-port", "82"])
if __name__ == "__main__": unittest.main()
