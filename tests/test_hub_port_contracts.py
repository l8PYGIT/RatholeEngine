import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rathole-manager'/'ratholehub'))
import hubcmds
class HubPortContracts(unittest.TestCase):
    def test_control_path_can_be_synchronized_without_shell_input(self):
        self.assertEqual(hubcmds.build_node_cmd('control_path_set',{'path':'/_rh/abc123'}),['ratholenode','control-path','set','/_rh/abc123'])
        self.assertEqual(hubcmds.build_node_cmd('control_path_clear',{}),['ratholenode','control-path','clear'])
        self.assertIn('control_path_set',hubcmds.WRITE_ACTIONS)
        for value in ['/ok;whoami','x','/a\n','/'+('a'*121)]:
            self.assertIsNone(hubcmds.build_node_cmd('control_path_set',{'path':value}))
    def test_port_bounds_are_checked_before_remote_execution(self):
        for port in ('0','65536','99999','-1','1\n'):
            self.assertIsNone(hubcmds.build_iran_cmd('plain_on',{'port':port}),port)
            self.assertIsNone(hubcmds.build_node_cmd('plain_on',{'remote':'panel.example:'+port}),port)
        for port in ('1','443','65535'):
            self.assertIsNotNone(hubcmds.build_iran_cmd('plain_on',{'port':port}),port)
if __name__=='__main__':unittest.main()
