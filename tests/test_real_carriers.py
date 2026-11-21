"""Opt-in real FRP/Backhaul payload, bad-auth and reconnect checks.

All listeners are loopback-only; no package, firewall or systemd changes.
"""
import contextlib, json, os, socket, subprocess, tempfile, threading, time, unittest
from pathlib import Path

FRPS=os.environ.get('FRPS_TEST_BIN')
FRPC=os.environ.get('FRPC_TEST_BIN')
BACKHAUL=os.environ.get('BACKHAUL_TEST_BIN')
KCP_SERVER=os.environ.get('KCP_SERVER_TEST_BIN')
KCP_CLIENT=os.environ.get('KCP_CLIENT_TEST_BIN')


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]


@contextlib.contextmanager
def echo_server():
    s=socket.socket();s.bind(('127.0.0.1',0));s.listen();s.settimeout(.2)
    stop=threading.Event()
    def run():
        while not stop.is_set():
            try:c,_=s.accept()
            except socket.timeout:continue
            with c:
                c.settimeout(.5)
                try:
                    data=c.recv(65536)
                    if data:c.sendall(data)
                except OSError:pass
    worker=threading.Thread(target=run,daemon=True);worker.start()
    try:yield s.getsockname()[1]
    finally:stop.set();worker.join(timeout=2);s.close()


def payload_ok(port,timeout=1):
    payload=b'rathole-carrier-integration-payload'
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=timeout) as s:
            s.settimeout(timeout);s.sendall(payload);return s.recv(4096)==payload
    except OSError:return False


class CarrierLab:
    def __init__(self,folder):self.folder=Path(folder);self.processes=[];self.logs=[]
    def start(self,binary,config,name):
        path=self.folder/(name+'.toml');path.write_text(config);path.chmod(0o600)
        log=open(self.folder/(name+'.log'),'w');self.logs.append(log)
        # FRP and Backhaul both accept -c <config>.
        p=subprocess.Popen([binary,'-c',str(path)],stdout=log,stderr=log)
        self.processes.append(p);return p
    def stop(self,p):
        if p.poll() is None:p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait()
    def close(self):
        for p in self.processes:self.stop(p)
        for log in self.logs:log.close()
    def wait_data(self,port,seconds=15):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            if payload_ok(port):return True
            time.sleep(.15)
        return False
    def failures(self):
        # Reports only exit status, not configs or credentials.
        return [p.poll() for p in self.processes]


class RealCarrierTests(unittest.TestCase):
    def exercise(self,make_configs,server_bin,client_bin):
        with tempfile.TemporaryDirectory(prefix='rathole-carrier-') as folder,echo_server() as echo:
            lab=CarrierLab(folder)
            try:
                control,public=free_port(),free_port()
                server,client,bad=make_configs(control,public,echo)
                lab.start(server_bin,server,'server')
                wrong=lab.start(client_bin,bad,'bad-client')
                time.sleep(1)
                self.assertFalse(payload_ok(public),'wrong token delivered a payload')
                lab.stop(wrong)
                good=lab.start(client_bin,client,'client')
                self.assertTrue(lab.wait_data(public),f'roundtrip failed; exits={lab.failures()}')
                lab.stop(good)
                time.sleep(.3)
                self.assertFalse(payload_ok(public),'payload delivered with client stopped')
                lab.start(client_bin,client,'reconnected-client')
                self.assertTrue(lab.wait_data(public),f'reconnect failed; exits={lab.failures()}')
            finally:lab.close()

    def frp(self,protocol):
        if not(FRPS and FRPC):self.skipTest('set FRPS_TEST_BIN and FRPC_TEST_BIN')
        def configs(control,public,echo):
            extra=f'kcpBindPort = {control}\n' if protocol=='kcp' else f'quicBindPort = {control}\n' if protocol=='quic' else ''
            server=f'bindAddr = "127.0.0.1"\nbindPort = {control}\nproxyBindAddr = "127.0.0.1"\n'+extra+'auth.method = "token"\nauth.token = "integration-token"\n'
            client=f'serverAddr = "127.0.0.1"\nserverPort = {control}\nauth.method = "token"\nauth.token = "integration-token"\ntransport.protocol = "{protocol}"\nloginFailExit = false\n[[proxies]]\nname = "integration"\ntype = "tcp"\nlocalIP = "127.0.0.1"\nlocalPort = {echo}\nremotePort = {public}\n'
            return server,client,client.replace('integration-token','wrong-token')
        self.exercise(configs,FRPS,FRPC)

    def backhaul(self,protocol):
        if not BACKHAUL:self.skipTest('set BACKHAUL_TEST_BIN')
        with tempfile.TemporaryDirectory(prefix='rathole-backhaul-tls-') as folder:
            tls=''
            if protocol in ('wss','wssmux'):
                cert,key=Path(folder)/'cert.pem',Path(folder)/'key.pem'
                subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
                tls=f'tls_cert = "{cert}"\ntls_key = "{key}"\n'
            def configs(control,public,echo):
                common=f'transport = "{protocol}"\ntoken = "integration-token"\nlog_level = "error"\nweb_port = 0\n'
                mux='mux_version = 1\nmux_framesize = 32768\nmux_recievebuffer = 4194304\nmux_streambuffer = 65536\n'
                server=f'[server]\nbind_addr = "127.0.0.1:{control}"\n'+common+mux+tls+f'heartbeat = 5\nchannel_size = 128\nmux_con = 2\nports = ["127.0.0.1:{public}={echo}"]\n'
                client=f'[client]\nremote_addr = "127.0.0.1:{control}"\n'+common+mux+'connection_pool = 2\nretry_interval = 1\ndial_timeout = 2\n'
                return server,client,client.replace('integration-token','wrong-token')
            self.exercise(configs,BACKHAUL,BACKHAUL)

    def kcp(self,profile):
        if not(KCP_SERVER and KCP_CLIENT):self.skipTest('set KCP_SERVER_TEST_BIN and KCP_CLIENT_TEST_BIN')
        def configs(control,public,echo):
            parity,mode={'balanced':(3,'fast2'),'lossy':(5,'fast2'),'aggressive':(4,'fast3')}[profile]
            common={'key':'integration-token','crypt':'aes','mode':mode,'datashard':10,'parityshard':parity,'quiet':True}
            server=json.dumps(dict(common,listen=f'127.0.0.1:{control}',target=f'127.0.0.1:{echo}'))
            client=json.dumps(dict(common,localaddr=f'127.0.0.1:{public}',remoteaddr=f'127.0.0.1:{control}'))
            return server,client,client.replace('integration-token','wrong-token')
        self.exercise(configs,KCP_SERVER,KCP_CLIENT)

    def test_kcp_balanced(self):self.kcp('balanced')
    def test_kcp_lossy(self):self.kcp('lossy')
    def test_kcp_aggressive(self):self.kcp('aggressive')

    def test_frp_tcp(self):self.frp('tcp')
    def test_frp_kcp(self):self.frp('kcp')
    def test_frp_quic(self):self.frp('quic')
    def test_frp_websocket(self):self.frp('websocket')
    def test_backhaul_ws(self):self.backhaul('ws')
    def test_backhaul_wsmux(self):self.backhaul('wsmux')
    def test_backhaul_wss(self):self.backhaul('wss')
    def test_backhaul_wssmux(self):self.backhaul('wssmux')

if __name__=='__main__':unittest.main()
