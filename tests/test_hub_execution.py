import unittest, sys, pathlib, shlex
from unittest.mock import patch, Mock
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'rathole-manager/ratholehub'))
import hub

class ExecutionTests(unittest.TestCase):
    def test_agent_http_error_closes_response_on_valid_and_invalid_json(self):
        import io, urllib.error
        for payload in [b'{"error":"denied"}', b'not-json']:
            with self.subTest(payload=payload):
                body = io.BytesIO(payload)
                error = urllib.error.HTTPError('http://test', 403, 'denied', {}, body)
                opener = Mock()
                opener.open.side_effect = error
                server = {'api_url': 'http://test', 'api_token': 'test'}
                with patch.object(hub, 'get_proxy', return_value=''), patch.object(hub.urllib.request, 'build_opener', return_value=opener):
                    self.assertEqual(hub.run_on_agent(server, ['ratholectl', 'ls'])['rc'], 403)
                self.assertTrue(body.closed)

    def test_remote_execution_concurrency_is_bounded(self):
        import concurrent.futures, threading, time
        lock = threading.Lock()
        counts = {'active': 0, 'peak': 0}
        def execute(*args, **kwargs):
            with lock:
                counts['active'] += 1
                counts['peak'] = max(counts['peak'], counts['active'])
            time.sleep(.03)
            with lock:
                counts['active'] -= 1
            return {'rc': 0}
        with patch.object(hub, '_run_on_server', side_effect=execute):
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(lambda _: hub.run_on_server({'host': 'test'}, ['true']), range(12)))
        self.assertLessEqual(counts['peak'], 4)
        self.assertTrue(all(r['rc'] == 0 for r in results))

    def test_execution_slot_released_after_failure(self):
        slots = Mock()
        slots.acquire.return_value = True
        with patch.object(hub, '_execution_slots', slots), patch.object(hub, '_run_on_server', side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):
                hub.run_on_server({'host': 'test'}, ['true'])
        slots.release.assert_called_once()

    def test_busy_hub_does_not_spawn_another_command(self):
        slots = Mock()
        slots.acquire.return_value = False
        with patch.object(hub, '_execution_slots', slots), patch.object(hub, '_run_on_server') as execute:
            self.assertEqual(hub.run_on_server({'host': 'test'}, ['true'])['rc'], 75)
        execute.assert_not_called()
        slots.release.assert_not_called()

    def test_api_server_url_can_be_corrected_without_rotating_token(self):
        handler = object.__new__(hub.Handler)
        handler._send = lambda code, body: (code, body)
        handler._user = lambda: 'test'
        inventory = [{'name': 'hub', 'role': 'iran', 'transport': 'api',
                      'api_url': 'http://127.0.0.1:8089', 'api_token': 'existing'}]
        with patch.object(hub, 'get_inventory', return_value=inventory), \
             patch.object(hub, 'set_inventory') as save, \
             patch.object(hub, 'audit_log'):
            code, body = handler._edit_server('hub', {'api_url': 'http://192.0.2.5:8089'})
            self.assertEqual(code, 200)
            self.assertEqual(body['server']['api_token'], 'existing')
            self.assertEqual(save.call_args.args[0][0]['api_url'], 'http://192.0.2.5:8089')

    def test_public_ip_override_is_saved_separately_from_ssh_host(self):
        handler = object.__new__(hub.Handler)
        handler._send = lambda code, body: (code, body)
        handler._user = lambda: 'test'
        inventory = [{'name': 'iran', 'role': 'iran', 'transport': 'ssh', 'host': '10.1.2.3'}]
        with patch.object(hub, 'get_inventory', return_value=inventory), \
             patch.object(hub, 'set_inventory') as save, \
             patch.object(hub, 'audit_log'):
            code, _ = handler._edit_server('iran', {'public_ip': '45.234.54.9'})
            self.assertEqual(code, 200)
            self.assertEqual(save.call_args.args[0][0]['host'], '10.1.2.3')
            self.assertEqual(save.call_args.args[0][0]['public_ip'], '45.234.54.9')

    def test_ssh_preserves_remote_argv(self):
        args = ['bash', '-c', 'printf "%s" "a b"; exit 7']
        with patch.object(hub, 'MOCK', False), patch.object(hub, 'get_config', return_value={}), patch.object(hub.subprocess, 'run', return_value=Mock(returncode=7, stdout='', stderr='')) as run:
            self.assertEqual(hub.run_on_server({'host':'example.test'}, args)['rc'], 7)
            self.assertEqual(shlex.split(run.call_args.args[0][-1]), args)

    def test_api_only_deploy_does_not_require_host(self):
        server = {'name':'node', 'transport':'api', 'api_url':'http://example.test', 'api_token':'test'}
        with patch.object(hub, 'MOCK', False), patch.object(hub, 'get_config', return_value={}), patch.object(hub, 'run_on_server', return_value={'rc':0}) as run:
            self.assertEqual(hub.deploy_to_server(server)['rc'], 0)
            self.assertEqual(run.call_args.args[0], server)
            self.assertEqual(run.call_args.args[1][:2], ['bash', '-c'])
            self.assertEqual(run.call_args.kwargs['timeout'], 600)

    def test_connection_metadata(self):
        handler = object.__new__(hub.Handler)
        handler._find = lambda name: {'name': name, 'role': 'iran', 'host':'192.0.2.1'}
        handler._send = lambda code, body: body
        def execute(server, argv):
            if argv == ['ratholectl', 'frp', 'show']:
                return {'rc':0, 'out':'ratholenode frp on 192.0.2.1:7000 secret123 tcp'}
            if argv == ['ratholectl', 'show', 'n1']:
                return {'rc':0, 'out':'--name n1 --token secret123 --inbound-port 443'}
            return {'rc':0, 'out':'{"nodes":[{"name":"n1","port":10005}]}'}
        with patch.object(hub, 'run_on_server', side_effect=execute):
            self.assertEqual(handler._frpconnect('iran'), {'ok':True, 'host':'192.0.2.1', 'remote':'192.0.2.1:7000', 'port':'7000', 'token':'secret123', 'transport':'tcp'})
            self.assertEqual(handler._nodeconnect('iran','n1')['remote_port'], '10005')

    def test_api_connection_hosts_and_control_path(self):
        handler = object.__new__(hub.Handler)
        handler._find = lambda name: {'name':name, 'role':'iran', 'transport':'api'}
        handler._send = lambda code, body: body
        def execute(server, argv):
            outputs = {
                ('status','--json'): '{"domain":"example.test","public_ip":"192.0.2.5"}',
                ('control-path','show'): 'control_path=/_rh/secret',
                ('kcp','show'): 'ratholenode kcp on 192.0.2.9:29900 abcdef123456 balanced',
                ('kcp','status'): '',
                ('noise','show'): 'ratholenode noise on 192.0.2.9:2334 ' + 'a'*44,
            }
            return {'rc':0, 'out':outputs.get(tuple(argv[1:]), '')}
        with patch.object(hub, 'run_on_server', side_effect=execute):
            main = handler._mainconnect('iran')
            self.assertEqual(main['control_path'], '/_rh/secret')
            self.assertEqual(main['host'], '192.0.2.5')
            self.assertEqual(handler._kcpconnect('iran')['remote'], '192.0.2.5:29900')
            self.assertEqual(handler._noiseconnect('iran')['remote'], '192.0.2.5:2334')

    def test_node_port_missing_fails_clearly(self):
        handler = object.__new__(hub.Handler)
        handler._find = lambda name: {'role':'iran'}
        handler._send = lambda code, body: body
        with patch.object(hub, 'run_on_server', side_effect=[
            {'rc':0,'out':'--name n1 --token secret123 --inbound-port 443'},
            {'rc':1,'out':'not-json'}]):
            self.assertFalse(handler._nodeconnect('iran','n1')['ok'])
