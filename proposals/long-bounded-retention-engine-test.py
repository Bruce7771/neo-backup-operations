#!/usr/bin/env python3
"""Pure generated-source and clock tests: no native or network calls."""
import importlib.util,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).parent

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.out=load('long_builder',HERE/'build-long-bounded-retention-engine.proposed.py').build(HERE.parent/'scripts',Path(cls.temp.name)/'engine')
  cls.module=load('long_budget',cls.out/'staged_derive.py')
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def budget(self):
  clock=[0.];b=self.module.Budget(now=lambda:clock[0]);return clock,b
 def test_boundaries(self):
  _,b=self.budget();self.assertEqual((b.metadata_end,b.finalize_end,b.job_end),(3600,3630,4500))
 def test_metadata_still_hard(self):
  c,b=self.budget();c[0]=3600
  with self.assertRaises(TimeoutError):b.metadata()
 def test_rollover_remains_120_and_bounded(self):
  c,b=self.budget()
  for i in range(42):self.assertEqual(b.begin_child(),min(c[0]+120,3600));c[0]+=85.01
  self.assertLess(c[0],3600);self.assertEqual(b.begin_child(),3600);self.assertEqual(b.segments,43)
 def test_integrity_and_restore_reserve(self):
  c,b=self.budget();c[0]=3630
  self.assertEqual(b.phase_timeout('integrity',180),180);self.assertEqual(b.phase_timeout('component',90),90)
 def test_whole_job_deadline(self):
  c,b=self.budget();c[0]=4500
  with self.assertRaises(TimeoutError):b.phase_timeout('component',90)
 def test_generated_checker_timeout(self):
  s=(self.out/'retention-readonly-check.py').read_text();self.assertIn("budget.phase_timeout('finalize',3630)",s);self.assertIn("'component',180 if",s)
 def test_cold_and_warm_call_limits_unchanged(self):
  s=(self.out/'retention-audit.py').read_text();self.assertIn('maximum_seconds=25',s);self.assertIn('maximum_seconds=90',s);self.assertIn('BUDGET.job_end',s)
 def test_transport_and_journal_caps_unchanged(self):
  s=(self.out/'native_parallel_transport.py').read_text();self.assertIn('max_live=4,process_limit=4096,byte_limit=512*1024*1024',s)
  s=(self.out/'staged_derive.py').read_text();self.assertIn('max_bytes=512*1024*1024,max_entries=4096',s);self.assertIn('Partial metadata cannot be admitted',s)
if __name__=='__main__':unittest.main()
