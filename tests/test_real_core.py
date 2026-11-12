"""Opt-in integration tests: real core, loopback ports, no system config changes."""
import os, re, shutil, socket, subprocess, tempfile, threading, time, unittest
from pathlib import Path

BIN = os.environ.get('RATHOLE_TEST_BIN')

@unittest.skipUnless(BIN, 'set RATHOLE_TEST_BIN to enable real-core tests')
class RealCoreTests(unittest.TestCase):
    def test_tcp(self): self.roundtrip('tcp')
    def test_websocket(self): self.roundtrip('websocket')
    def test_noise(self): self.roundtrip('noise')

    def roundtrip(self, transport):
        def freeport():
            with socket.socket() as s:
                s.bind(('127.0.0.1', 0)); return s.getsockname()[1]
        control, public = freeport(), freeport()
        echo = socket.socket(); echo.bind(('127.0.0.1', 0)); echo.listen(); echo.settimeout(.2)
        stop = threading.Event()
        def serve():
            while not stop.is_set():
                try: conn, _ = echo.accept()
                except socket.timeout: continue
                with conn:
                    conn.settimeout(2)
                    try:
                        data=conn.recv(65536)
                        if data: conn.sendall(data)
                    except OSError: pass
        thread=threading.Thread(target=serve, daemon=True); thread.start()
        server_transport=client_transport=''
        if transport=='websocket':
            server_transport='[server.transport.websocket]\ntls = false\n'
            client_transport='[client.transport.websocket]\ntls = false\n'
        if transport=='noise':
            keys=subprocess.check_output([BIN,'--genkey'],text=True)
            private=re.search(r'Private Key:\s*(\S+)',keys).group(1)
            public_key=re.search(r'Public Key:\s*(\S+)',keys).group(1)
            server_transport=f'[server.transport.noise]\nlocal_private_key = "{private}"\n'
            client_transport=f'[client.transport.noise]\nremote_public_key = "{public_key}"\n'
        children=[]
        with tempfile.TemporaryDirectory(prefix='rathole-real-') as tmp:
            try:
                server=f'[server]\nbind_addr = "127.0.0.1:{control}"\n[server.transport]\ntype = "{transport}"\n'+server_transport+f'[server.services.test]\ntoken = "integration-token"\nbind_addr = "127.0.0.1:{public}"\n'
                client=f'[client]\nremote_addr = "127.0.0.1:{control}"\nretry_interval = 1\n[client.transport]\ntype = "{transport}"\n'+client_transport+f'[client.services.test]\ntoken = "integration-token"\nlocal_addr = "127.0.0.1:{echo.getsockname()[1]}"\n'
                for name, config in [('server',server),('client',client)]:
                    path=Path(tmp)/(name+'.toml');path.write_text(config);path.chmod(0o600)
                    log=open(Path(tmp)/(name+'.log'),'w');self.addCleanup(log.close)
                    children.append(subprocess.Popen([BIN,str(path)],stdout=log,stderr=log))
                payload=b'rathole-integration-roundtrip'
                deadline=time.monotonic()+10;last=''
                while time.monotonic()<deadline:
                    try:
                        with socket.create_connection(('127.0.0.1',public),timeout=.5) as s:
                            s.settimeout(1);s.sendall(payload);received=s.recv(4096)
                            if received==payload: return
                    except OSError as e: last=str(e)
                    if any(p.poll() is not None for p in children): break
                    time.sleep(.1)
                # Do not print configs or private Noise keys.
                self.fail(f'{transport} roundtrip failed: {last}; exits={[p.poll() for p in children]}')
            finally:
                for p in children:
                    if p.poll() is None: p.terminate()
                for p in children:
                    try: p.wait(timeout=3)
                    except subprocess.TimeoutExpired: p.kill();p.wait()
                stop.set();thread.join(timeout=3);echo.close()

if __name__=='__main__': unittest.main()
