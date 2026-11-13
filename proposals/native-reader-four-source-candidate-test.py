#!/usr/bin/env python3
"""Fixture takes only NONSECRET reviewed source-code bytes from stdin JSON."""
import ast,base64,copy,hashlib,importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('patcher',Path(__file__).with_name('native-reader-four-source-candidate.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SOURCES={k:base64.b64decode(v)for k,v in json.load(sys.stdin).items()}
class Candidate(unittest.TestCase):
 def test_eight_flags_and_matched_pin(self):
  r=m.prepare(SOURCES);self.assertEqual(r['proof']['data_reader_flags_removed'],8)
  self.assertEqual(r['rollback'],SOURCES)
  self.assertNotEqual(r['proof']['new_runner_sha256'],m.PIN)
  self.assertIn(r['proof']['new_runner_sha256'].encode(),r['candidates']['neo-hourly-online-run.py'])
  self.assertNotIn(m.PIN.encode(),r['candidates']['neo-hourly-online-run.py'])
 def test_changed_source_refused_before_candidate(self):
  s=dict(SOURCES);s['neo-daily-backup.sh']+=b'\n# unexpected change\n'
  with self.assertRaises(ValueError):m.prepare(s)
 def test_subset_refused(self):
  s=dict(SOURCES);s.pop('neo-hourly-online-run.py')
  with self.assertRaises(ValueError):m.prepare(s)
 def test_sources_not_mutated_and_rollback_byte_exact(self):
  before=dict(SOURCES);r=m.prepare(SOURCES);self.assertEqual(SOURCES,before)
  for n in SOURCES:self.assertEqual(m.digest(r['rollback'][n]),m.BASELINES[n][0])
 def test_new_shell_syntax_and_delegate_real_descriptor_guard(self):
  r=m.prepare(SOURCES)
  with tempfile.TemporaryDirectory(prefix='neo-source-patch-fixture-',dir='/var/tmp')as tmp:
   root=Path(tmp);root.chmod(0o700)
   for n,raw in r['candidates'].items():
    p=root/n;p.write_bytes(raw);p.chmod(0o700)
    if n.endswith('.sh'):subprocess.run(['/bin/bash','-n',str(p)],check=True,capture_output=True,timeout=5)
   path=root/'neo-hourly-online-run.py';spec=importlib.util.spec_from_file_location('newdelegate',path);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
   target=root/'neo-hourly-v3-run.py';fd=d.verified_target(target,d.EXPECTED_SHA256,(root,));os.close(fd)
   target.write_bytes(target.read_bytes()+b'\n# unexpected runtime edit\n')
   with self.assertRaises(ValueError):d.verified_target(target,d.EXPECTED_SHA256,(root,))
if __name__=='__main__':unittest.main()
