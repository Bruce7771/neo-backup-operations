#!/usr/bin/env python3
"""Synthetic tests against actual current engine, no subprocess/cloud/credentials."""
import copy,importlib.util,json,os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('candidate',Path(__file__).with_name('retention-safety-candidate.py'))
actual=load('fixture',ROOT/'scripts/hourly_recovery_test.py')
class Safety(unittest.TestCase):
 def test_protected_old_hourly_passes_REAL_derive_and_planner(self):
  fixture=actual.DeriveTests();data=fixture.fixture();inventory,plans,policy,external,restored,blobs=data
  hourly=next(r for r in plans[0][0]['keep']if r['id']=='b'*64);plans[0][0]['keep'].remove(hourly);plans[0][0]['remove'].append(hourly)
  from hourly_recovery import derive
  unheld=derive(*data[:-1],lambda sid,p,n:blobs[sid,p]);self.assertNotIn('b'*64,{r['child_snapshot']for r in unheld[0]})
  held=m.move_explicit_holds_before_derive(plans,['b'*64]);data=(inventory,held,policy,external,restored,blobs)
  edges,parents,updated=fixture.invoke(data)
  self.assertIn('b'*64,{r['child_snapshot']for r in edges});self.assertNotIn('b'*64,{r['id']for p in updated for g in p for r in g['remove']})
  tags={'daily':'neo-daily','hourly':'neo-hourly-files','pitr':'neo-main-pitr'}
  for s in policy['scopes']:s['tag']=tags[s['kind']]
  for r in inventory:r['tags']=[tags[r['hostname']]]
  planner=load('planner',ROOT/'scripts/retention-plan.py');planner.SCOPES={s['host']:(s['tag'],frozenset(s['paths']))for s in policy['scopes']};planner.FULL_MAIN_HOST='daily';planner.CONFIG_SCOPES={}
  result=planner.build(inventory,updated,['a'*64,'b'*64]+sorted(parents),['a'*64,'b'*64,'c'*64],[],edges)
  self.assertFalse(result['apply_ready']);self.assertEqual(result['remove_snapshot_ids'],[])
 def test_rules_no_invented48hour_horizon(self):
  self.assertEqual(m.scoped_rule_suffix({'kind':'daily'}),['--keep-daily','30','--keep-monthly','3'])
  for kind in ('hourly','pitr'):
   self.assertEqual(m.scoped_rule_suffix({'kind':kind}),['--keep-within','30d','--keep-daily','30','--keep-monthly','3'])
 def test_missing_protected_id_not_fabricated(self):self.assertEqual(m.move_explicit_holds_before_derive([],['a'*64]),[])
 def test_duplicate_plan_fails_closed(self):
  with self.assertRaises(ValueError):m.move_explicit_holds_before_derive([[{'keep':[{'id':'a'*64}],'remove':[{'id':'a'*64}]}]],[])
 def test_input_unchanged(self):
  p=[[{'remove':[{'id':'a'*64}],'keep':[]}]];q=copy.deepcopy(p);m.move_explicit_holds_before_derive(p,['a'*64]);self.assertEqual(p,q)
 def test_audit_patch_exact_and_protected_before_derive(self):
  s=m.audit_candidate((ROOT/'scripts/retention-audit.py').read_text());compile(s,'candidate','exec');self.assertLess(s.index('held_plans='),s.index('edge_inventory,parents,updated=derive'))
  with self.assertRaises(ValueError):m.audit_candidate(s)
 def test_ACTUAL_audit_main_applies_hold_before_REAL_derive(self):
  fixture=actual.DeriveTests();inventory,plans,policy,external,restored,blobs=fixture.fixture();policy['schema']=1
  row=next(r for r in plans[0][0]['keep']if r['id']=='b'*64);plans[0][0]['keep'].remove(row);plans[0][0]['remove'].append(row)
  class Done(Exception):pass
  class Batch:
   def __init__(self,*a):self.stats={}
   def handles(self,*a):return True
   def get(self,s,p,n):return blobs[s,p]
  import types
  module=types.ModuleType('candidate_audit');module.__file__=str(ROOT/'scripts/retention-audit.py')
  with patch.dict(sys.modules,{'retention_safety_candidate':m}):exec(compile(m.audit_candidate((ROOT/'scripts/retention-audit.py').read_text()),module.__file__,'exec'),module.__dict__)
  module.HourlyMetadataBatch=Batch;commands=[]
  def fake_run(args,env,*a,**k):
   if args==['restic','version']:return 'restic 0.16.4 synthetic'
   if args[-2:]==['snapshots','--json']:return json.dumps(inventory)
   if '--dry-run'in args:
    commands.append(args)
    # Test one synthetic native plan per authorized scope; no duplicates.
    host=args[args.index('--host')+1]
    return json.dumps([{'keep':[r for r in plans[0][0]['keep']if r['hostname']==host],'remove':[r for r in plans[0][0]['remove']if r['hostname']==host]}])
   if len(args)>1 and Path(args[1]).name=='retention-plan.py':
    w=Path(args[args.index('--protected')+1]).parent
    edges=json.loads((w/'hourly-recovery.json').read_text());self.assertIn('b'*64,{e['child_snapshot']for e in edges})
    selected=[]
    for i,x in enumerate(args):
     if x=='--plan':selected.extend(json.loads(Path(args[i+1]).read_text()))
    self.assertNotIn('b'*64,{r['id']for g in selected for r in g['remove']});raise Done()
   raise AssertionError('Unexpected IO')
  module.run=fake_run
  with tempfile.TemporaryDirectory()as d:
   env={'PATH':'/usr/bin:/bin','RUNNER_TEMP':d,'RESTIC_REPOSITORY':'s3:https://fixture.invalid/restic','AWS_ACCESS_KEY_ID':'synthetic','AWS_SECRET_ACCESS_KEY':'synthetic','NEO_RESTIC_PASSWORD':'synthetic','NEO_POLICY_JSON':json.dumps(policy),'NEO_PROTECTED_JSON':json.dumps(['b'*64]),'NEO_RESTORED_JSON':json.dumps(restored),'NEO_DEPENDENCIES_JSON':'[]','NEO_HOURLY_RECOVERY_JSON':json.dumps(external)}
   with patch.dict(os.environ,env,clear=True):
    with self.assertRaises(Done):module.main()
  self.assertEqual(len(commands),3);self.assertNotIn('--keep-within',commands[0]);self.assertEqual(commands[1][-6:],['--keep-within','30d','--keep-daily','30','--keep-monthly','3'])
 def test_batch_same_point_immutable_once_and_bounded_eviction(self):
  base=load('batch_fixture',ROOT/'scripts/hourly_metadata_batch_test.py');f=base.Batch();f.setUp();self.addCleanup(f.doCleanups)
  import hourly_metadata_batch
  scope={};exec(compile(m.batch_candidate((ROOT/'scripts/hourly_metadata_batch.py').read_text()),'candidate','exec'),scope)
  b=scope['HourlyMetadataBatch'](f.cache,f.env,f.inventory,f.scope,time.monotonic()+180,f.restore)
  reads=[];original=b._read
  def tracked(*a):reads.append(a);return original(*a)
  b._read=tracked
  for name in f.payloads['b'*64]:b.get('b'*64,'/fixture/hourly/'+name,8*1024*1024)
  self.assertEqual(len(f.calls),1);self.assertEqual(len(reads),1);self.assertEqual(b.stats['memory_payload_hits'],4)
  with self.assertRaises(TypeError):b._memo_payload['manifest.json']=b'changed'
  b.get('a'*64,'/fixture/hourly/manifest.json',8*1024*1024);self.assertEqual(len(f.calls),2)
  b.get('b'*64,'/fixture/hourly/manifest.json',8*1024*1024);self.assertEqual(len(f.calls),2);self.assertEqual(len(reads),3)
  b.deadline=time.monotonic()-1
  with self.assertRaises(TimeoutError):b.get('b'*64,'/fixture/hourly/manifest.json',8*1024*1024)
if __name__=='__main__':unittest.main()
