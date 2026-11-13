#!/usr/bin/env python3
import base64,importlib.util,json,subprocess,sys,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('combined',Path(__file__).with_name('native-reader-eight-source-candidate.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SOURCES={k:base64.b64decode(v)for k,v in json.load(sys.stdin).items()}
class Combined(unittest.TestCase):
 def test_all_eight_originals_exact_and_mirrors(self):
  r=m.prepare(SOURCES);self.assertEqual(r['rollback'],SOURCES);self.assertEqual(len(r['candidates']),8)
  self.assertEqual(r['candidates']['neo-hourly-v3-config-collect.py'],r['candidates']['neo-builder-preview-config-collect.py'])
 def test_coverage_all8sources_8rollback_and_receipt(self):
  r=m.prepare(SOURCES);ns={'__name__':'coverage_fixture'};exec(compile(r['candidates']['neo-hourly-v3-config-coverage.py'],'<coverage>','exec'),ns)
  self.assertEqual(len(ns['REQUIRED']),34)
  for n,h in m.BEFORE.items():
   self.assertIn('/usr/local/libexec/'+n,ns['REQUIRED'])
   self.assertIn('/etc/neo/backup/rollback/native-reader-before-'+n+'.'+h+'.txt',ns['REQUIRED'])
  self.assertIn('/etc/neo/backup/native-reader-enrollment.json',ns['REQUIRED'])
 def test_missing_enrollment_rejected(self):
  r=m.prepare(SOURCES);ns={'__name__':'coverage_fixture'};exec(compile(r['candidates']['neo-hourly-v3-config-coverage.py'],'<coverage>','exec'),ns)
  rows=[{'source':p,'uid':0,'sha256':'a'*64,'bytes':1}for p in ns['REQUIRED']]
  self.assertTrue(ns['verify']({'source_file_metadata':rows})['all_manifested'])
  rows=[x for x in rows if not x['source'].endswith('native-reader-enrollment.json')]
  with self.assertRaises(ValueError):ns['verify']({'source_file_metadata':rows})
 def test_changed_collector_refused(self):
  v=dict(SOURCES);v['neo-builder-preview-config-collect.py']+=b'\n'
  with self.assertRaises(ValueError):m.prepare(v)
 def test_expected_bound_and_shell_syntax(self):
  r=m.prepare(SOURCES);self.assertLess(r['proof']['source_code_bytes']+r['proof']['additional_rollback_bytes'],300000)
  with tempfile.TemporaryDirectory(prefix='neo-eight-source-fixture-',dir='/var/tmp')as tmp:
   for n,raw in r['candidates'].items():
    if n.endswith('.sh'):
     p=Path(tmp)/n;p.write_bytes(raw);subprocess.run(['/bin/bash','-n',str(p)],check=True,capture_output=True,timeout=5)
if __name__=='__main__':unittest.main()
