"""Opt-in generated nginx config integration; no system configuration changes."""
import glob, http.server, json, os, pathlib, re, shlex, socket, subprocess, tempfile, threading, time, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
BIN=os.environ.get('NGINX_TEST_BIN')
BACKHAUL=os.environ.get('BACKHAUL_TEST_BIN')

def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

@unittest.skipUnless(BIN, 'set NGINX_TEST_BIN')
class NginxIntegration(unittest.TestCase):
    def test_generated_ingress_routes(self):
        servers=[];process=None;carriers=[]
        def backend(text):
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200);self.end_headers();self.wfile.write(text.encode())
                def log_message(self,*args):pass
            s=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);servers.append(s)
            threading.Thread(target=s.serve_forever,daemon=True).start();return s.server_port
        try:
            fake,data,hub,sub,proxy=[backend(x) for x in ['fake','data','hub','sub','proxy']]
            direct,plain,internal,front,game=[port() for _ in range(5)]
            with tempfile.TemporaryDirectory(prefix='rathole-nginx-') as tmp:
                d=pathlib.Path(tmp);crt=d/'cert.pem';key=d/'key.pem'
                subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=lab.example','-addext','subjectAltName=DNS:lab.example,DNS:game.lab.example','-keyout',str(key),'-out',str(crt)],check=True,capture_output=True)
                state={'domain':'lab.example','cert_fullchain':str(crt),'cert_key':str(key),'control_port':fake,'control_path':'/_rh/0123456789abcdef0123456789abcdef','fake_port':fake,'sub_port':sub,'hub_port':hub,'plain_port':plain,'direct_port':direct,'direct_header':'X-Cdn-Id','internal_port':internal,'nodes':[{'name':'lab','port':data,'inbound_port':data,'token':'integration-token'}],'proxies':[{'name':'proxy','upstream':f'http://127.0.0.1:{proxy}'}]}
                if BACKHAUL:
                    bh_control,bh_public=port(),port();bh_echo=backend('backhaul-data')
                    state.update(backhaul_port=bh_control,backhaul_transport='wsmux',backhaul_exposure='nginx_tls')
                    state['nodes'].append({'name':'bh','port':bh_public,'inbound_port':bh_echo,'token':'integration-token','transport':'backhaul'})
                    mux='mux_version = 1\nmux_framesize = 32768\nmux_recievebuffer = 4194304\nmux_streambuffer = 65536\n'
                    server=f'[server]\nbind_addr = "127.0.0.1:{bh_control}"\ntransport = "wsmux"\ntoken = "integration-token"\nweb_port = 0\nheartbeat = 5\nchannel_size = 128\nmux_con = 2\n'+mux+f'ports = ["127.0.0.1:{bh_public}={bh_echo}"]\n'
                    client=f'[client]\nremote_addr = "127.0.0.1:{front}"\ntransport = "wssmux"\ntoken = "integration-token"\nweb_port = 0\nconnection_pool = 2\nretry_interval = 1\ndial_timeout = 2\n'+mux
                    for name,config in [('bh-server',server),('bh-client',client)]:
                        config_path=d/(name+'.toml');config_path.write_text(config);config_path.chmod(0o600)
                        carriers.append(subprocess.Popen([BACKHAUL,'-c',str(config_path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
                def generate(sni=False):
                    nonlocal process
                    (d/'state.json').write_text(json.dumps(state))
                    script='export RATHOLECTL_LIB_ONLY=1; source '+shlex.quote(str(ROOT/'rathole-manager/ratholectl'))+'; STATE='+shlex.quote(str(d/'state.json'))+'; NGINX_CONF='+shlex.quote(str(d/'http.conf'))+'; STREAM_CONF='+shlex.quote(str(d/'stream.conf'))+'; ensure_stream_include(){ :; }; gen_nginx_conf'
                    subprocess.run(['bash','-c',script],check=True,capture_output=True)
                    # Move only the public listener to an isolated loopback port.
                    p=d/('stream.conf' if sni else 'http.conf');text=p.read_text();text=text.replace('listen 443 ',f'listen 127.0.0.1:{front} ').replace('listen 443;',f'listen 127.0.0.1:{front};');text=re.sub(r'(?m)(^\s*listen )(\d+)([ ;])',r'\g<1>127.0.0.1:\g<2>\g<3>',text);p.write_text(text)
                    modules=glob.glob('/usr/lib/nginx/modules/ngx_stream_module.so')
                    load=f'load_module {modules[0]};' if sni and modules else ''
                    stream=f'stream {{ include {d}/stream.conf; }}' if sni else ''
                    extra=f'server {{ listen 127.0.0.1:{game} ssl; ssl_certificate {crt}; ssl_certificate_key {key}; return 200 "game"; }}' if sni else ''
                    main=f'{load} worker_processes 1; daemon off; pid {d}/nginx.pid; error_log {d}/error.log; events {{worker_connections 128;}} http {{ access_log off; map $http_upgrade $connection_upgrade {{default upgrade; \"\" close;}} include {d}/http.conf; {extra} }} {stream}'
                    (d/'nginx.conf').write_text(main)
                    check=subprocess.run([BIN,'-p',str(d)+'/', '-c',str(d/'nginx.conf'),'-t'],capture_output=True,text=True)
                    self.assertEqual(check.returncode,0,check.stderr)
                    process=subprocess.Popen([BIN,'-p',str(d)+'/', '-c',str(d/'nginx.conf')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    time.sleep(.3)
                    self.assertIsNone(process.poll(),(d/'error.log').read_text())
                def request(path='/',host='lab.example',tls=True,listen=None,headers=()):
                    selected=listen or front
                    url=f'{"https" if tls else "http"}://{host}:{selected}{path}'
                    args=['curl','-fsS','--max-time','3','--noproxy','*','--resolve',f'{host}:{selected}:127.0.0.1','--cacert',str(crt)]
                    for header in headers:args+=['-H',header]
                    return subprocess.check_output(args+[url],text=True)
                def check_backhaul():
                    if not BACKHAUL:return
                    for _ in range(20):
                        try:
                            if request('/bh')=='backhaul-data':return
                        except subprocess.CalledProcessError:pass
                        time.sleep(.2)
                    self.fail('Backhaul WSSMUX through generated nginx routing failed')
                generate()
                check_backhaul()
                for path,expected in [('/','fake'),('/lab','data'),('/proxy/','proxy'),('/hub/','hub'),('/sub/a','sub')]:self.assertEqual(request(path),expected,path)
                self.assertEqual(request(tls=False,listen=plain,path='/lab'),'data')
                self.assertEqual(request(tls=False,listen=direct,headers=['X-Cdn-Id: lab']),'data')
                self.assertEqual(request(tls=False,listen=direct),'fake')
                process.terminate();process.wait(timeout=5);process=None
                state['nodes'].append({'name':'game','port':game,'inbound_port':443,'token':'integration-token','sni':'game.lab.example'})
                generate(sni=True)
                self.assertEqual(request(host='game.lab.example'),'game')
                check_backhaul()
                self.assertEqual(request(path='/lab'),'data')
        finally:
            if process is not None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            for child in carriers:
                if child.poll() is None:child.terminate()
            for child in carriers:
                try:child.wait(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.wait()
            for s in servers:s.shutdown();s.server_close()

if __name__=='__main__':unittest.main()
