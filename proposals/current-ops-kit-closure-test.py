#!/usr/bin/env python3
"""Actual planner compatibility/negative tests, synthetic backup IDs only."""
import copy,hashlib,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).parent;ROOT=HERE.parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
TEMP=tempfile.TemporaryDirectory(prefix='neo-new-ops-closure-test-');OUT=load('builder',HERE/'build-current-ops-retention-engine.proposed.py').build(ROOT/'scripts',Path(TEMP.name)/'engine');sys.path.insert(0,str(OUT));p=load('actual_kit_planner',OUT/'retention-plan.py');kit=load('kit',OUT/'current_ops_kit_closure.py')
class Closure(unittest.TestCase):
 def fixture(self):
  inv,plans,protected,restored=p.PlannerTests().data();hourly=next(r for r in inv if 'neo-hourly-files'in r['tags']);full=inv[0]
  row=dict(id='a'*64,hostname='fixture-ops',tags=['neo-ops-config','new-reviewed-kit'],paths=['/fixture/new-sidecar/capture'],time='2026-11-14T12:00:00Z');inv=inv+[row]
  digest=hashlib.sha256(kit.canonical(kit.projection(row))).hexdigest();deps=[dict(child_snapshot=row['id'],parent_snapshot=parent['id'],kind='reviewed-configuration-kit-v1',child_inventory_sha256=digest,parent_role=role)for parent,role in((full,'full'),(hourly,'hourly'))]
  edge=dict(child_snapshot=hourly['id'],kind='selfcontained-pg-named-point',source='postgres-archive-delivery.json',verified=True,evidence_sha256='e'*64,external_parent_dependency=None,postgres_recovery_included=True,metadata_verified=True,restore_point='neo_hourly_1234567890_abcdef01',wal_segment='A'*24,base_manifest_sha256='d'*64)
  return inv,plans,protected+[hourly['id'],row['id']],restored+[row['id']],deps,[edge]
 def test_exact_offpath_kit_with_full_and_restored_v3_parent_accepted_no_apply(self):
  result=p.build(*self.fixture());self.assertEqual(result['configuration_deltas_preserved'],1);self.assertFalse(result['apply_ready']);self.assertEqual(result['remove_snapshot_ids'],[])
 def test_missing_exact_descriptor_not_path_wildcard(self):
  d=list(self.fixture());d[4]=[{k:e[k]for k in('child_snapshot','parent_snapshot')}for e in d[4]]
  with self.assertRaisesRegex(ValueError,'Unexpected configuration'):p.build(*d)
 def test_projection_tamper_refused(self):
  d=self.fixture();d[0][-1]['paths']=['/fixture/tampered/capture']
  with self.assertRaisesRegex(ValueError,'projection differs'):p.build(*d)
 def test_unknown_host_cannot_gain_access(self):
  d=self.fixture();d[0][-1]['hostname']='unapproved-host'
  with self.assertRaisesRegex(ValueError,'outside existing'):p.build(*d)
 def test_unprotected_parent_refused(self):
  d=list(self.fixture());d[2]=[x for x in d[2]if x!='3'*64]
  with self.assertRaisesRegex(ValueError,'unprotected'):p.build(*d)
 def test_hourly_parent_needs_actual_restore_authority(self):
  d=list(self.fixture());d[3]=[x for x in d[3]if x!='3'*64]
  with self.assertRaisesRegex(ValueError,'actual restore'):p.build(*d)
 def test_SQLite_only_or_unknown_cannot_be_claimed_v3_parent(self):
  d=self.fixture();d[-1][0].update(kind='sqlite-files-only',postgres_recovery_included=False);d[-1][0].pop('restore_point');d[-1][0].pop('wal_segment')
  with self.assertRaisesRegex(ValueError,'self-contained PostgreSQL'):p.build(*d)
 def test_parent_role_mismatch(self):
  d=self.fixture();d[4][0]['parent_role']='config'
  with self.assertRaisesRegex(ValueError,'role mismatch'):p.build(*d)
 def chain(self):
  d=list(self.fixture());a=d[0][-1];b=dict(a,id='b'*64,paths=['/fixture/second-sidecar/capture']);d[0]=d[0]+[b];d[2]=d[2]+[b['id']];d[3]=d[3]+[b['id']]
  digest=hashlib.sha256(kit.canonical(kit.projection(b))).hexdigest();d[4]=d[4]+[dict(child_snapshot=a['id'],parent_snapshot=b['id'],kind='reviewed-configuration-kit-v1',child_inventory_sha256=d[4][0]['child_inventory_sha256'],parent_role='config'),dict(child_snapshot=b['id'],parent_snapshot='1'*64,kind='reviewed-configuration-kit-v1',child_inventory_sha256=digest,parent_role='full')];return d
 def test_transitive_exact_ops_chain(self):self.assertEqual(p.build(*self.chain())['configuration_deltas_preserved'],2)
 def test_transitive_cycle_refused(self):
  d=self.chain();d[4].append(dict(d[4][-1],parent_snapshot='a'*64,parent_role='config'))
  with self.assertRaisesRegex(ValueError,'cycle'):p.build(*d)
 def test_actual_existing_planner_regressions(self):
  r=unittest.TestResult();unittest.defaultTestLoader.loadTestsFromTestCase(p.PlannerTests).run(r);self.assertFalse(r.failures);self.assertFalse(r.errors);self.assertEqual(r.testsRun,19)
if __name__=='__main__':
 try:unittest.main()
 finally:TEMP.cleanup()
