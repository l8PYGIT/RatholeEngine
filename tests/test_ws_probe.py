"""Real sockets verify bounded RFC 6455 health probing."""
import os, pathlib, shlex, shutil, socket, subprocess, threading, time, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASH=shutil.which('bash')
BASE=b'Upgrade: websocket\r\nConnection: Upgrade\r\n'
ACCEPT=b'Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n'

@unittest.skipUnless(BASH and os.name!='nt','Linux socket integration')
class WebSocketProbeTests(unittest.TestCase):
    def probe(self,response,hold=False):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(3)
        port=listener.getsockname()[1];stop=threading.Event()
        def serve():
            try:
                connection,_=listener.accept()
                with connection:
                    connection.settimeout(2);data=b''
                    while b'\r\n\r\n' not in data:
                        part=connection.recv(4096)
                        if not part:return
                        data+=part
                    connection.sendall(response)
                    if hold:stop.wait(5)
            except OSError:pass
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        script='export RATHOLENODE_LIB_ONLY=1; source '+shlex.quote(str(ROOT/'rathole-manager/ratholenode'))+'; adaptive_probe_ws_plain 127.0.0.1 '+str(port)
        try:
            start=time.monotonic();result=subprocess.run([BASH,'-c',script],capture_output=True,text=True,timeout=7)
            return result,time.monotonic()-start
        finally:stop.set();thread.join(timeout=3);listener.close()
    def test_valid_upgrade_returns_without_waiting_for_eof(self):
        result,elapsed=self.probe(b'HTTP/1.1 101 Switching Protocols\r\n'+BASE+ACCEPT+b'\r\n',hold=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(result.stdout.startswith('healthy:'));self.assertLess(elapsed,4)
    def test_wrong_accept_rejected(self):
        result,_=self.probe(b'HTTP/1.1 101 Switching Protocols\r\n'+BASE+b'Sec-WebSocket-Accept: wrong\r\n\r\n')
        self.assertNotEqual(result.returncode,0)
    def test_http_200_is_not_websocket(self):
        result,_=self.probe(b'HTTP/1.1 200 OK\r\n'+BASE+ACCEPT+b'\r\n')
        self.assertNotEqual(result.returncode,0)
    def test_body_cannot_forge_missing_accept_header(self):
        result,_=self.probe(b'HTTP/1.1 101 Switching Protocols\r\n'+BASE+b'\r\n'+ACCEPT)
        self.assertNotEqual(result.returncode,0)
    def test_incomplete_headers_rejected(self):
        result,_=self.probe(b'HTTP/1.1 101 Switching Protocols\r\n'+BASE+ACCEPT)
        self.assertNotEqual(result.returncode,0)
