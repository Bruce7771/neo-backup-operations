#!/usr/bin/env python3
"""Portable regression with a NEW tiny real local restic fixture, no Neo/cloud."""
import hashlib,importlib.util,json,os,subprocess,tempfile,time,unittest
from pathlib import Path
HERE=Path(__file__).parent;ROOT=HERE.parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class Fix(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='neo-empty-node-fix-');cls.out=load('fix_builder',HERE/'build-native-empty-file-fix.proposed.py').build(ROOT/'scripts',Path(cls.tmp.name)/'engine')
  cls.fixed=load('fixed_catalog',cls.out/'native_pg_catalog_v2.py');cls.original=load('old_catalog',HERE/'native-pg-catalog-authentication.proposed.py')
  r=Path(cls.tmp.name)/'fresh-local-native-fixture';r.mkdir(mode=0o700)
  pg=r/'fixture/exact/pg/path';(pg/'base').mkdir(parents=True);(pg/'wal').mkdir()
  for name in('synthetic-empty-one','synthetic-empty-two'):(pg/'base'/name).touch()
  password=r/'password';password.write_text('synthetic-empty-format-test-only');password.chmod(0o600)
  # Deliberately no inherited AWS/RESTIC/NEO variables: cannot access B2.
  env={'PATH':os.environ['PATH'],'HOME':str(r),'XDG_CACHE_HOME':str(r/'cache'),'RESTIC_REPOSITORY':str(r/'repo'),'RESTIC_PASSWORD_FILE':str(password),'LANG':'C.UTF-8'}
  def native(args):
   result=subprocess.run(['restic']+args,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=15)
   assert len(result.stdout)<=2*1024*1024
   assert sum(p.stat().st_size for p in r.rglob('*')if p.is_file())<=2*1024*1024
   return result.stdout
  assert native(['version']).decode().startswith('restic 0.16.4 ')
  native(['init']);summary=native(['backup','--json',str(r/'fixture')]);sid=[json.loads(x)['snapshot_id']for x in summary.splitlines()if json.loads(x).get('message_type')=='summary'][0]
  cls.rawroot=native(['cat','tree',sid+':'+str(pg)])
  cls.id=next(n['subtree']for n in json.loads(cls.rawroot)['nodes']if n['name']=='base');cls.raw=native(['cat','blob',cls.id]);assert hashlib.sha256(cls.raw).hexdigest()==cls.id
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def catalog(self,fixed=True):
  m=self.fixed if fixed else self.original;kw={'authenticated_file_origin':lambda *a:True}if fixed else{}
  return m.NativePGCatalog('synthetic',{'host':'fixture','tag':'hourly','paths':['/fixture']},[{'id':'a'*64,'hostname':'fixture','tags':['hourly'],'paths':['/fixture']}],None,None,time.monotonic()+180,**kw)
 def test_REAL_native_empty_nodes_old_bug_reproduced_new_fixed(self):
  with self.assertRaisesRegex(ValueError,'file size'):self.catalog(False).tree(self.raw,self.id)
  rows=self.catalog().tree(self.raw,self.id);self.assertEqual(len(rows),2);self.assertTrue(all('size'not in n and n.get('content')==[]for n in rows))
 def test_explicit_zero_remains_supported(self):
  raw=json.dumps({'nodes':[{'name':'zero','type':'file','size':0,'content':[]}]}).encode();self.assertEqual(self.catalog().tree(raw)[0]['size'],0)
 def test_missing_size_with_content_is_NOT_silently_empty(self):
  raw=json.dumps({'nodes':[{'name':'nonempty','type':'file','content':['f'*64]}]}).encode()
  with self.assertRaises(ValueError):self.catalog().tree(raw)
 def test_invalid_sizes_still_refused(self):
  for v in (-1,None,False,'0'):
   raw=json.dumps({'nodes':[{'name':'bad','type':'file','size':v,'content':[]}]}).encode()
   with self.assertRaises(ValueError):self.catalog().tree(raw)
 def test_new_copy_source_and_diagnostics_only(self):
  audit=(self.out/'retention-audit.py').read_text();self.assertIn("'native_pg_catalog_v2.py'",audit);self.assertIn("frame.name not in('require','need')",audit)
  batch=(self.out/'hourly_metadata_batch.py').read_text();self.assertIn('  finally:\n   self.stats.update',batch)
  for p in self.out.glob('*.py'):compile(p.read_text(),p.name,'exec')
if __name__=='__main__':unittest.main()
