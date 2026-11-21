"""Real socket checks: a UDP or non-loopback listener is not a TCP backend."""
import os, pathlib, shlex, shutil, socket, subprocess, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASH=shutil.which('bash') if os.name!='nt' else r'C:\Program Files\Git\bin\bash.exe'

@unittest.skipUnless(BASH and os.name!='nt', 'Linux socket integration')
class BackendTests(unittest.TestCase):
    def ready(self,port):
        script='export RATHOLENODE_LIB_ONLY=1; source '+shlex.quote(str(ROOT/'rathole-manager/ratholenode'))+'; node_backend_ready '+str(port)
        return subprocess.run([BASH,'-c',script],capture_output=True,timeout=5).returncode==0
    def test_tcp_listener_accepted(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));s.listen();self.assertTrue(self.ready(s.getsockname()[1]))
    def test_udp_listener_rejected(self):
        with socket.socket(type=socket.SOCK_DGRAM) as s:
            s.bind(('127.0.0.1',0));self.assertFalse(self.ready(s.getsockname()[1]))
    def test_other_loopback_address_rejected(self):
        with socket.socket() as s:
            s.bind(('127.0.0.2',0));s.listen();self.assertFalse(self.ready(s.getsockname()[1]))
    def test_invalid_port_rejected(self):
        self.assertFalse(self.ready(65536))
