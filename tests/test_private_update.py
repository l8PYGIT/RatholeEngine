import json, os, pathlib, shutil, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
@unittest.skipIf(os.name=='nt','Linux updater sandbox; run under WSL')
class PrivateUpdateTests(unittest.TestCase):
    def run_update(self, assets, failed_id=''):
        with tempfile.TemporaryDirectory() as directory:
            d=pathlib.Path(directory); (d/'bin').mkdir()
            programs={
                'id':'#!/bin/sh\necho 0\n',
                'bash':'#!/bin/sh\nprintf "%s\\n" "$@" > "$TASK_TEST_DIR/invocation"\n',
                'curl':'''#!/usr/bin/env python3
import json,os,sys,pathlib
args=sys.argv[1:];cfg=sys.stdin.read();d=pathlib.Path(os.environ['TASK_TEST_DIR'])
with (d/'requests').open('a') as f:f.write(json.dumps({'args':args,'auth': 'test_token' in cfg})+'\\n')
url=next(a for a in args if a.startswith('https://'));out=pathlib.Path(args[args.index('-o')+1])
if url.endswith('/releases/latest') or '/releases/tags/' in url:out.write_text(os.environ['TASK_ASSETS'])
elif url.endswith('/'+os.environ.get('TASK_FAIL_ID','NEVER')):sys.exit(22)
else:out.write_text('#!/bin/bash\\nexit 0\\n')
'''}
            for name,body in programs.items():
                p=d/'bin'/name;p.write_text(body);p.chmod(0o755)
            env=dict(os.environ,PATH=str(d/'bin')+':'+os.environ['PATH'],TASK_TEST_DIR=str(d),TASK_ASSETS=json.dumps({'assets':assets}),TASK_FAIL_ID=failed_id,RATHOLE_GH_TOKEN='test_token',RATHOLE_RELEASE='latest')
            r=subprocess.run(['/bin/bash',str(ROOT/'tools/update-private.sh')],env=env,capture_output=True,text=True,timeout=10)
            calls=[json.loads(line) for line in (d/'requests').read_text().splitlines()] if (d/'requests').exists() else []
            invocation=(d/'invocation').read_text() if (d/'invocation').exists() else ''
            return r,calls,invocation
    def test_private_release_assets_are_authenticated_and_update_is_local(self):
        r,calls,invocation=self.run_update([{'name':'bootstrap.sh','id':11},{'name':'rathole-manager.zip','id':12}])
        self.assertEqual(r.returncode,0,r.stderr)
        urls=[next(a for a in c['args'] if a.startswith('https://')) for c in calls]
        self.assertEqual(urls,['https://api.github.com/repos/loopy-iri/tunnelplus/releases/latest','https://api.github.com/repos/loopy-iri/tunnelplus/releases/assets/11','https://api.github.com/repos/loopy-iri/tunnelplus/releases/assets/12'])
        self.assertTrue(all(c['auth'] for c in calls))
        self.assertTrue(all('test_token' not in str(c['args']) for c in calls))
        self.assertIn('--local\n',invocation);self.assertIn('--update\n',invocation)
        self.assertNotIn('test_token',r.stdout+r.stderr)
    def test_missing_bundle_never_falls_back_to_unreleased_source(self):
        r,calls,invocation=self.run_update([{'name':'bootstrap.sh','id':11}])
        self.assertNotEqual(r.returncode,0);self.assertEqual(invocation,'')
    def test_failed_download_never_starts_update(self):
        r,calls,invocation=self.run_update([{'name':'bootstrap.sh','id':11},{'name':'rathole-manager.zip','id':12}],'12')
        self.assertNotEqual(r.returncode,0);self.assertEqual(invocation,'')
if __name__=='__main__':unittest.main()
