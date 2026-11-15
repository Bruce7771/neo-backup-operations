#!/usr/bin/env python3
"""Actual generated planner, exact native metadata fixtures; no cloud I/O."""
import importlib.util,json,sys,tempfile,unittest,copy
from pathlib import Path
HERE=Path(__file__).parent
ROWS=json.loads(r'''[{"id":"11aed282ce0ae26c699d4b39be50c36ab5ee3bf2e583c1e9945db41190c88af9","hostname":"srv2140404-main-builder-config","tags":["neo-builder-preview-config","neo-current-source"],"paths":["/var/lib/neo-builder-preview-config/current-737-controls-1794690332127127197"],"time":"2026-11-14T21:14:20.494177824Z"},{"id":"da47e6c570052024a1f71783d8333356d56ecd8c6f640a3a31cedb4e93c9e0f0","hostname":"srv2140404-main-builder-config","tags":["neo-builder-preview-config","neo-social-final-hold"],"paths":["/etc/neo/social-restoration-hold-20261115/capture-receipt.private.json","/etc/neo/social-restoration-hold-20261115/manifest.json"],"time":"2026-11-15T01:37:21.856997201Z"}]''')
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
TEMP=tempfile.TemporaryDirectory();OUT=load('controls_builder',HERE/'build-reviewed-controls-retention-engine.proposed.py').build(HERE.parent/'scripts',Path(TEMP.name)/'engine');sys.path.insert(0,str(OUT));p=load('controls_planner',OUT/'retention-plan.py')
class Tests(unittest.TestCase):
 def setUp(self):
  self.old=dict(p.CONFIG_SCOPES);p.CONFIG_SCOPES[('srv2140404-main-builder-config','neo-builder-preview-config')]='/var/lib/neo-builder-preview-config/capture'
 def tearDown(self):p.CONFIG_SCOPES=self.old
 def fixture(self):
  inv,plans,protected,restored=p.PlannerTests().data();return inv+copy.deepcopy(ROWS),plans,protected+[r['id']for r in ROWS],restored
 def test_exact_two_accepted_without_generic_restore_or_parent(self):
  d=self.fixture();result=p.PlannerTests().invoke(*d);self.assertEqual(len(result['independent_control_artifacts_preserved']),2);self.assertEqual(result['configuration_deltas_preserved'],0);self.assertFalse(result['apply_ready']);self.assertEqual(result['remove_snapshot_ids'],[])
  for row in ROWS:self.assertNotIn(row['id'],d[3]);self.assertIn(row['id'],result['retained_snapshot_ids'])
  for e in result['independent_control_artifacts_preserved'].values():self.assertFalse(e['generic_Neo_restore_claimed']);self.assertFalse(e['external_parent_claimed'])
 def test_no_owner_hold_rejected(self):
  d=list(self.fixture());d[2]=d[2][:-1]
  with self.assertRaisesRegex(ValueError,'explicit owner protected'):p.PlannerTests().invoke(*d)
 def test_path_substitution_rejected(self):
  d=self.fixture();d[0][-1]['paths']=['/etc/neo/other-file']
  with self.assertRaisesRegex(ValueError,'projection changed'):p.PlannerTests().invoke(*d)
 def test_tags_or_time_substitution_rejected(self):
  for key,value in [('tags',['neo-builder-preview-config','extra']),('time','2026-11-15T00:00:00Z')]:
   d=self.fixture();d[0][-1][key]=value
   with self.assertRaisesRegex(ValueError,'projection changed'):p.PlannerTests().invoke(*d)
 def test_foreign_host_rejected(self):
  d=self.fixture();d[0][-1]['hostname']='foreign'
  with self.assertRaisesRegex(ValueError,'host/tag'):p.PlannerTests().invoke(*d)
 def test_unknown_third_offpath_still_fails(self):
  d=self.fixture();d[0].append(dict(ROWS[0],id='f'*64))
  with self.assertRaisesRegex(ValueError,'Unexpected configuration'):p.PlannerTests().invoke(*d)
 def test_no_blanket_two_file_exception(self):
  d=self.fixture();old=d[0][-1]['id'];d[0][-1]['id']='e'*64;d[2].remove(old);d[2].append('e'*64)
  with self.assertRaisesRegex(ValueError,'Unexpected configuration'):p.PlannerTests().invoke(*d)
 def test_original_planner_regressions(self):
  result=unittest.TestResult();unittest.defaultTestLoader.loadTestsFromTestCase(p.PlannerTests).run(result);self.assertEqual(result.testsRun,19);self.assertFalse(result.errors);self.assertFalse(result.failures)
if __name__=='__main__':
 try:unittest.main()
 finally:TEMP.cleanup()