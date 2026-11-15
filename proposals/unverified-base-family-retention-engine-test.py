#!/usr/bin/env python3
"""Metadata-only new-base quarantine fixtures; no PostgreSQL replay or cloud."""
import copy,hashlib,importlib.util,json,pathlib,sys,tempfile,unittest
HERE=pathlib.Path(__file__).parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
TEMP=tempfile.TemporaryDirectory();OUT=load('familybuilder',HERE/'build-unverified-base-family-retention-engine.proposed.py').build(HERE.parent/'scripts',pathlib.Path(TEMP.name)/'engine');sys.path[:0]=[str(OUT),str(HERE.parent/'scripts')]
from hourly_selfcontained_v3_test import SelfContained
from hourly_recovery import derive
planner=load('familyplanner',OUT/'retention-plan.py')
class Tests(unittest.TestCase):
 def data(self,untested=True,expired=False):
  d=SelfContained().fixture()
  if untested:d[-1]['c'*64,'/fixture/pitr/base/backup_manifest']=b'{"old_compatible_base":true}'
  if expired:
   g=d[1][0][0];row=next(r for r in g['keep']if r['id']=='e'*64);g['keep']=[r for r in g['keep']if r['id']!='e'*64];g['remove'].append(row)
  return d
 def invoke(self,d,subset=None):
  *args,blobs=d
  def dump(sid,path,maximum):raw=blobs[sid,path];self.assertLessEqual(len(raw),maximum);return raw
  return derive(*args,dump,child_subset=subset)
 def prepare_planner(self,d,plans):
  tags={'daily':'neo-daily','hourly':'neo-hourly-files','pitr':'neo-main-pitr'}
  for r in d[0]+[r for plan in plans for group in plan for k in('keep','remove')for r in group.get(k,[])]:r['tags']=[tags[r['hostname']]]
  for scope in d[2]['scopes']:scope['tag']=tags[scope['kind']]
  planner.SCOPES={s['host']:(s['tag'],frozenset(s['paths']))for s in d[2]['scopes']};planner.FULL_MAIN_HOST='daily';planner.CONFIG_SCOPES={}
 def test_unverified_base_all_structure_checked_but_not_restored(self):
  edges,parents,plans=self.invoke(self.data());edge=next(e for e in edges if e['child_snapshot']=='e'*64)
  self.assertEqual(edge['kind'],'protected-unverified-base-family');self.assertFalse(edge['verified']);self.assertTrue(edge['metadata_verified']);self.assertEqual(edge['base_restore_coverage'],'unverified');self.assertFalse(edge['postgres_named_target_restore_verified']);self.assertEqual(parents,{'c'*64,'d'*64,'e'*64})
 def test_expired_unverified_point_quarantined_before_removal(self):
  edges,parents,plans=self.invoke(self.data(expired=True));self.assertFalse(plans[0][0]['remove']);self.assertIn('e'*64,parents);self.assertEqual(len(edges),2)
 def test_whole_same_base_family_including_expired_sibling_held(self):
  d=self.data();f=dict(next(r for r in d[0]if r['id']=='e'*64),id='f'*64);d[0].append(f);d[1][0][0]['remove'].append(f)
  for(k,path),raw in list(d[-1].items()):
   if k=='e'*64:d[-1]['f'*64,path]=raw
  edges,parents,plans=self.invoke(d);self.assertTrue({'c'*64,'d'*64,'e'*64,'f'*64}<=parents);self.assertFalse(plans[0][0]['remove']);self.assertEqual(sum(e['kind']=='protected-unverified-base-family'for e in edges),2)
 def test_staged_partial_expired_child_still_one_receipt(self):
  edges,_,_=self.invoke(self.data(expired=True),['e'*64]);self.assertEqual(len(edges),1)
 def test_structural_corruption_not_hidden_by_quarantine(self):
  d=self.data();d[-1]['e'*64,'/fixture/hourly/postgres-selfcontained/sealed-pg.json']=b'{}'
  with self.assertRaisesRegex(ValueError,'seal fingerprint'):self.invoke(d)
 def test_periodic_actual_base_witness_changes_eligibility_without_hourly_restore(self):
  d=self.data();d[4].append('d'*64);edges,_,_=self.invoke(d);edge=next(e for e in edges if e['child_snapshot']=='e'*64);self.assertEqual(edge['kind'],'selfcontained-pg-named-point');self.assertTrue(edge['verified']);self.assertFalse(edge['postgres_named_target_restore_verified'])
 def test_final_actual_planner_accepts_protected_family_no_false_unknown13(self):
  d=self.data(expired=True);edges,parents,plans=self.invoke(d);self.prepare_planner(d,plans);r=planner.build(d[0],plans,['a'*64]+list(parents),['a'*64,'b'*64,'c'*64],[],edges);self.assertEqual(r['remove_snapshot_ids'],[]);self.assertEqual(r['protected_unverified_base_family_count'],1);self.assertEqual(r['protected_unverified_base_hourly_points'],1);self.assertEqual(r['protected_unknown_hourly_points'],0);self.assertFalse(r['apply_ready'])
 def test_expired_verified_point_not_falsely_kept_as_hourly_evidence(self):
  d=self.data(untested=False,expired=True);edges,parents,plans=self.invoke(d);self.assertNotIn('e'*64,{e['child_snapshot']for e in edges});self.assertIn('e'*64,{r['id']for r in plans[0][0]['remove']})
 def test_partial_verified_expired_child_still_has_one_staged_receipt(self):
  edges,_,_=self.invoke(self.data(untested=False,expired=True),['e'*64]);self.assertEqual(len(edges),1)
 def test_missing_PITR_family_protection_refused(self):
  d=self.data();edges,parents,plans=self.invoke(d);self.prepare_planner(d,plans)
  with self.assertRaisesRegex(ValueError,'every possible authorized PITR'):planner.build(d[0],plans,['a'*64,'e'*64,'c'*64],['a'*64,'b'*64,'c'*64],[],edges)
 def test_faked_verified_claim_rejected(self):
  d=self.data();edges,parents,plans=self.invoke(d);next(e for e in edges if e['child_snapshot']=='e'*64)['verified']=True;self.prepare_planner(d,plans)
  with self.assertRaisesRegex(ValueError,'not restored claim'):planner.build(d[0],plans,['a'*64]+list(parents),['a'*64,'b'*64,'c'*64],[],edges)
if __name__=='__main__':
 try:unittest.main()
 finally:TEMP.cleanup()
