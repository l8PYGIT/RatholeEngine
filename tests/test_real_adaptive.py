"""Opt-in real WSS -> KCP -> WSS recovery in a temporary loopback lab."""
import json, os, pathlib, shlex, signal, subprocess, tempfile, time, unittest
from test_real_carriers import echo_server, free_port, payload_ok
ROOT=pathlib.Path(__file__).resolve().parents[1]
CORE=os.environ.get('RATHOLE_TEST_BIN')
NGINX=os.environ.get('NGINX_TEST_BIN')
KS=os.environ.get('KCP_SERVER_TEST_BIN')
KC=os.environ.get('KCP_CLIENT_TEST_BIN')

@unittest.skipUnless(CORE and NGINX and KS and KC,'set core, nginx and kcptun binary paths')
class RealAdaptive(unittest.TestCase):
    def test_real_failover_and_recovery(self):
        children=[];logs=[]
        with tempfile.TemporaryDirectory(prefix='rathole-adaptive-') as tmp,echo_server() as echo:
            d=pathlib.Path(tmp);d.chmod(0o755);control,public,front,udp,kcp=[free_port() for _ in range(5)]
            def start(binary,config,name,nginx=False):
                path=d/(name+'.conf');path.write_text(config);path.chmod(0o600)
                log=open(d/(name+'.log'),'w');logs.append(log)
                args=[binary,'-p',str(d)+'/', '-c',str(path)] if nginx else [binary,'-c',str(path)]
                if binary==CORE:args=[binary,str(path)]
                p=subprocess.Popen(args,stdout=log,stderr=log);children.append(p);return p
            def wait_payload():
                for _ in range(60):
                    if payload_ok(public):return True
                    time.sleep(.1)
                return False
            try:
                cert,key=d/'cert.pem',d/'key.pem'
                subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=lab.example','-addext','subjectAltName=DNS:lab.example','-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
                server=f'[server]\nbind_addr = "127.0.0.1:{control}"\n[server.transport]\ntype = "websocket"\n[server.transport.websocket]\ntls = false\n[server.services.test]\ntoken = "integration-token"\nbind_addr = "127.0.0.1:{public}"\n'
                start(CORE,server,'core-server')
                temps=' '.join(f'{kind}_temp_path {d}/{kind};' for kind in ['client_body','proxy','fastcgi','uwsgi','scgi'])
                nginx=f'worker_processes 1; daemon off; pid {d}/nginx.pid; error_log {d}/error.log; events {{worker_connections 64;}} http {{{temps} access_log off; server {{listen 127.0.0.1:{front} ssl; ssl_certificate {cert}; ssl_certificate_key {key}; location / {{proxy_pass http://127.0.0.1:{control}; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; proxy_read_timeout 30s;}}}}}}'
                tls=start(NGINX,nginx,'nginx',nginx=True)
                common={'key':'integration-token','crypt':'aes','mode':'fast2','datashard':10,'parityshard':3,'quiet':True}
                ks=start(KS,json.dumps(dict(common,listen=f'127.0.0.1:{udp}',target=f'127.0.0.1:{control}')),'kcp-server')
                start(KC,json.dumps(dict(common,localaddr=f'127.0.0.1:{kcp}',remoteaddr=f'127.0.0.1:{udp}')),'kcp-client')
                (d/'node.env').write_text(f'SERVER=127.0.0.1:{front}\nTLS_HOSTNAME=lab.example\nTLS_TRUSTED_ROOT={cert}\nKCP_LOCAL=127.0.0.1:{kcp}\nTUNNEL=ws\n')
                (d/'services.conf').write_text(f'test|integration-token|{echo}\n')
                (d/'adaptive.env').write_text('ADAPTIVE_ENABLED=1\nADAPTIVE_FAILURES=1\nADAPTIVE_RECOVERIES=2\nADAPTIVE_COOLDOWN=300\n')
                prefix='export RATHOLENODE_LIB_ONLY=1; source '+shlex.quote(str(ROOT/'rathole-manager/ratholenode'))+'; '
                for key_,value in {'ENV_FILE':d/'node.env','SVC_FILE':d/'services.conf','CLIENT_TOML':d/'client.toml','ADAPTIVE_ENV':d/'adaptive.env','ADAPTIVE_STATE':d/'state.json','ADAPTIVE_LOCK':d/'adaptive.lock'}.items():prefix+=key_+'='+shlex.quote(str(value))+'; '
                pidfile=shlex.quote(str(d/'client.pid'));client=shlex.quote(str(d/'client.toml'));log=shlex.quote(str(d/'client.log'))
                prefix+='reload_svc(){ if [ -f '+pidfile+' ] && kill -0 "$(cat '+pidfile+')" 2>/dev/null; then return 0; fi; nohup '+shlex.quote(CORE)+' '+client+' >'+log+' 2>&1 < /dev/null 9>&- & echo $! > '+pidfile+'; }; '
                def shell(command):
                    result = subprocess.run(['bash','-c',prefix+command],capture_output=True,text=True,timeout=30)
                    self.assertNotIn('command not found', result.stderr)
                    return result
                def mode():
                    return next(line.split('=',1)[1] for line in (d/'node.env').read_text().splitlines() if line.startswith('TUNNEL='))
                result=shell('gen_client && reload_svc');self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue(wait_payload(),'initial WSS payload failed')
                # The same CA must not permit a different TLS hostname.
                invalid=shell('load_env; adaptive_probe_ws_tls 127.0.0.1 '+str(front)+" / '' mismatch.example "+shlex.quote(str(cert)))
                self.assertNotEqual(invalid.returncode,0);self.assertTrue(invalid.stdout.startswith('tls_failed:'))

                tls.terminate();tls.wait(timeout=5)
                result=shell('cmd_adaptive run');self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(mode(),'kcp');self.assertTrue(wait_payload(),'KCP failover payload failed')
                tls=start(NGINX,nginx,'nginx-recovered',nginx=True);time.sleep(.3)
                result=shell('cmd_adaptive run');self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(mode(),'kcp','cooldown was ignored')
                result=shell('adaptive_save_state \'{"last_switch_epoch":0}\'; cmd_adaptive run');self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(mode(),'ws',str(json.loads((d/'state.json').read_text()))+result.stdout+result.stderr);self.assertTrue(wait_payload(),'WSS recovery payload failed')
                # A listening kcptun local socket with its UDP server stopped is NOT healthy.
                ks.terminate();ks.wait(timeout=5);tls.terminate();tls.wait(timeout=5)
                result=shell('adaptive_save_state \'{"last_switch_epoch":0}\'; cmd_adaptive run')
                self.assertNotEqual(result.returncode,0,'dead KCP candidate accepted');self.assertEqual(mode(),'ws')
            finally:
                pid=d/'client.pid'
                if pid.exists():
                    try:os.kill(int(pid.read_text()),signal.SIGTERM)
                    except ProcessLookupError:pass
                for p in children:
                    if p.poll() is None:p.terminate()
                for p in children:
                    try:p.wait(timeout=3)
                    except subprocess.TimeoutExpired:p.kill();p.wait()
                for log in logs:log.close()

if __name__=='__main__':unittest.main()
