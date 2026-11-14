#!/usr/bin/env python3
"""Actual generated-engine staged tests; synthetic providers, no cloud."""
import copy,hashlib,importlib.util,json,os,subprocess,sys,tempfile,time,unittest,threading
from pathlib import Path
HERE=Path(__file__).parent;ROOT=HERE.parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
TMP=tempfile.TemporaryDirectory(prefix='neo-staged-tests-');ENGINE=load('builder',HERE/'build-staged-retention-engine.proposed.py').build(ROOT/'scripts',Path(TMP.name)/'engine');sys.path.insert(0,str(ENGINE))
from staged_derive import Budget,Journal,staged_derive
from hourly_recovery import derive
from hourly_metadata_batch import NativeHourlyMetadataBatch
enc=lambda x:json.dumps(x,sort_keys=True).encode();sha=lambda b:hashlib.sha256(b).hexdigest()
class Clock:
 def __init__(self):self.t=1000.
 def __call__(self):return self.t
class Staged(unittest.TestCase):
 def test_metadata_includes_inventory_and_total_is240(self):
  c=Clock();b=Budget(now=c);c.t+=241
  with self.assertRaises(TimeoutError):b.begin_child()
 def test_segments120_total240_global540_and_reserve90(self):
  c=Clock();b=Budget(now=c);self.assertEqual(b.begin_child(),1120);c.t=1090;self.assertEqual(b.begin_child(),1210);self.assertEqual(b.segments,2);c.t=1200
  with self.assertRaisesRegex(ValueError,'Two'):b.begin_child()
  c.t=1300;self.assertEqual(b.phase_timeout('integrity',180),150);c.t=1451
  with self.assertRaises(TimeoutError):b.phase_timeout('integrity',180)
  self.assertEqual(b.phase_timeout('component',90),89)
 def fixture_journal(self,cap=100000):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);b=Budget();b.begin_child();return Journal(Path(t.name)/'journal',{'fixed':'input'},b,max_bytes=cap)
 def test_receipt_tamper_no_reapply(self):
  j=self.fixture_journal();sid='a'*64;j.source(sid,'/f',3,lambda:b'abc');j.finish(sid,{'child_snapshot':sid});p=j.root/(sid+'.receipt');p.write_bytes(p.read_bytes()+b' ')
  with self.assertRaisesRegex(ValueError,'receipt changed'):j.start_replay([sid])
 def test_byte_tamper_even_same_size_rejected(self):
  j=self.fixture_journal();sid='a'*64;j.source(sid,'/f',3,lambda:b'abc');j.finish(sid,{});(j.root/(sha(b'abc')+'.bin')).write_bytes(b'xyz')
  with self.assertRaisesRegex(ValueError,'digest changed'):j.start_replay([sid])
 def test_partial_noadmission(self):
  j=self.fixture_journal();j.finish('a'*64,{})
  with self.assertRaisesRegex(ValueError,'Partial'):j.start_replay(['a'*64,'b'*64])
 def test_crosssnapshot_path_and_newchunk_no_replay_fetch(self):
  j=self.fixture_journal();sid='a'*64;j.source(sid,'/f',3,lambda:b'abc');j.finish(sid,{});j.start_replay([sid])
  for s,p in [('b'*64,'/f'),(sid,'/other')]:
   with self.assertRaisesRegex(ValueError,'not verified'):j.source(s,p,3,lambda:self.fail('Must not fetch'))
  with self.assertRaisesRegex(ValueError,'tree was not'):j.tree('c'*64,lambda:self.fail('Must not fetch'))
 def test_corrupt_native_tree_rejected_before_cache(self):
  j=self.fixture_journal()
  with self.assertRaisesRegex(ValueError,'native tree differs'):j.tree('a'*64,lambda:b'{}')
  self.assertEqual(j.trees,{})
 def test_symlink_body_and_entry_byte_caps(self):
  j=self.fixture_journal(3);j.source('a'*64,'/f',3,lambda:b'abc')
  with self.assertRaisesRegex(ValueError,'cap'):j.source('a'*64,'/g',3,lambda:b'xyz')
  p=j.root/(sha(b'abc')+'.bin');p.unlink();p.symlink_to('/dev/null')
  with self.assertRaisesRegex(ValueError,'Unsafe'):j._read({'bytes':3,'sha256':sha(b'abc')})
 def test_new_process_cannot_load_mac_authority(self):
  j=self.fixture_journal();j.finish('a'*64,{})
  with self.assertRaises(FileExistsError):Journal(j.root,{'fixed':'input'},j.budget)
 def test_parallel_cache_byte_reservation_race_is_bounded(self):
  j=self.fixture_journal(3);barrier=threading.Barrier(4);errors=[]
  def worker(n):
   barrier.wait()
   try:j._body(bytes([n])*3)
   except ValueError:errors.append(n)
  threads=[threading.Thread(target=worker,args=(n,))for n in range(4)]
  for t in threads:t.start()
  for t in threads:t.join()
  self.assertEqual(j.bytes,3);self.assertEqual(len(errors),3);self.assertEqual(len(list(j.root.glob('*.bin'))),1)
 def test_timeout_during_child_cannot_emit_completion_receipt(self):
  c=Clock();b=Budget(now=c);b.begin_child()
  with tempfile.TemporaryDirectory()as d:
   j=Journal(Path(d)/'j',{'scope':'fixture'},b);c.t+=121
   with self.assertRaises(TimeoutError):j.finish('a'*64,{})
   self.assertEqual(j.receipts,{})
   with self.assertRaisesRegex(ValueError,'Partial'):j.start_replay(['a'*64])
 def test_actual16_v3_plus_legacy_replay_all_edges_equal_and_shared_global_counters(self):
  f=load('actual_v3_fixture',ENGINE/'hourly_selfcontained_v3_test.py').SelfContained().fixture();inv,plans,policy,overrides,restored,blobs=f;original=next(r for r in inv if r['id']=='e'*64);allrows=[]
  for n in range(16):
   sid=sha(('point'+str(n)).encode());r=dict(original,id=sid);allrows.append(r)
   for (s,p),raw in list(blobs.items()):
    if s=='e'*64:blobs[sid,p]=raw
  inv[:]=[r for r in inv if r['id']!='e'*64]+allrows;plans[0][0]['keep']=[r for r in plans[0][0]['keep']if r['id']!='e'*64]+allrows
  seal=blobs[allrows[0]['id'],'/fixture/hourly/postgres-selfcontained/sealed-pg.json'];rows=json.loads(seal)['files'];trees={};nodes=[]
  for d in('base','wal'):
   raw=enc({'nodes':[{'name':r['path'].split('/')[1],'type':'file','size':r['bytes'],'content':[r['sha256']]}for r in rows if r['path'].startswith(d+'/')]});trees[sha(raw)]=raw;nodes.append({'name':d,'type':'dir','subtree':sha(raw)})
  nodes.append({'name':'sealed-pg.json','type':'file','size':len(seal),'content':[sha(seal)]});root=enc({'nodes':nodes});calls=[];clock=Clock();clock.t=time.monotonic()
  def restore(args,env,deadline):
   calls.append(tuple(args));clock.t+=12;i=args.index('--target');target=Path(args[i+1]);sid=args[i+2]
   for k in range(i+3,len(args),2):
    p=args[k+1]
    if(sid,p)in blobs:q=target/p.lstrip('/');q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(blobs[sid,p])
  class Reader:
   calls=0;output_bytes=0
   def read(self,args,maximum):
    self.calls+=1;raw=root if args[:2]==['cat','tree']else trees[args[2]];self.output_bytes+=len(raw);return raw
  with tempfile.TemporaryDirectory()as d:
   budget=Budget(now=clock);reader=Reader();batch=NativeHourlyMetadataBatch(Path(d)/'cache',{'RESTIC_REPOSITORY':'s3:https://fixture.invalid/restic'},inv,policy['scopes'][1],budget.metadata_end,restore,reader)
   def dump(s,p,n):
    if batch.handles(s,p):return batch.get(s,p,n)
    return blobs[s,p]
   dump.native_pg_catalog=batch.verify_catalog
   result=staged_derive(derive,inv,plans,policy,overrides,restored,dump,batch,budget,Path(d)/'journal');self.assertEqual(len(result[0]),17);self.assertEqual(len(calls),16);self.assertEqual(batch.stats['staged_completed_children'],17);self.assertEqual(batch.stats['staged_final_replay_verified'],1);self.assertLessEqual(budget.segments,2)
   self.assertEqual(reader.calls,18);self.assertEqual(budget.segments,2);self.assertGreater(clock.t-budget.start,180);self.assertLessEqual(clock.t-budget.start,240) #shared global counters; no replay I/O.
   self.assertTrue(all(e.get('postgres_named_target_restore_verified')is False for e in result[0]if e['kind']=='selfcontained-pg-named-point'))
 def test_REAL_native16_local_snapshots_shared_base_actual_engine_no_cloud(self):
  data=load('real_native_fixture',ENGINE/'hourly_selfcontained_v3_test.py').SelfContained().fixture();original=data[-1];source_sid='e'*64
  with tempfile.TemporaryDirectory(prefix='neo-staged-native16-')as d:
   p=Path(d);hourly=p/'source/hourly';pitr=p/'source/pitr';hourly.mkdir(parents=True);(pitr/'base').mkdir(parents=True)
   (pitr/'base/backup_manifest').write_bytes(original['c'*64,'/fixture/pitr/base/backup_manifest'])
   for(s,path),raw in original.items():
    if s==source_sid:q=hourly/path.removeprefix('/fixture/hourly/');q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(raw)
   env={'PATH':'/usr/bin:/bin','HOME':d,'RESTIC_PASSWORD':'isolated-native16-dummy-only','RESTIC_REPOSITORY':str(p/'repo')};native_calls=[]
   def native(args):
    native_calls.append(args[0]);r=subprocess.run(['restic',*args],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=35);self.assertLess(len(r.stdout),2*1024*1024);return r.stdout
   def backup(path):return json.loads(native(['backup','--force','--json',str(path)]).splitlines()[-1])['snapshot_id']
   native(['init']);parent=backup(pitr);rows=[]
   for n in range(16):
    cap=json.loads((hourly/'capture-result.json').read_bytes());cap['synthetic_fixture_index']=n;(hourly/'capture-result.json').write_bytes(enc(cap));sid=backup(hourly);rows.append(dict(id=sid,hostname='hourly',tags=['hourly'],paths=[str(hourly)]))
   inv=[dict(id=parent,hostname='pitr',tags=['pitr'],paths=[str(pitr)])]+rows;plans=[[dict(keep=inv,remove=[])]];policy={'scopes':[dict(kind=k,host=k,tag=k,paths=[str(p/'source'/k)])for k in('daily','hourly','pitr')]};budget=Budget()
   batch=NativeHourlyMetadataBatch(p/'cache',env,inv,policy['scopes'][1],budget.metadata_end)
   def dump(s,path,maximum):
    if batch.handles(s,path):return batch.get(s,path,maximum)
    raw=native(['dump',s,path]);self.assertLessEqual(len(raw),maximum);return raw
   dump.native_pg_catalog=batch.verify_catalog;start=time.monotonic();result=staged_derive(derive,inv,plans,policy,[],[parent],dump,batch,budget,p/'journal')
   self.assertEqual(len(result[0]),16);self.assertEqual(batch.stats['native_batches'],16);self.assertEqual(batch.stats['staged_completed_children'],16);self.assertEqual(batch.stats['staged_final_replay_verified'],1);self.assertLessEqual(batch.reader.max_live_children,4);self.assertLess(time.monotonic()-start,240)
   self.assertFalse(any(e['postgres_named_target_restore_verified']for e in result[0]));locks=native(['list','locks']).splitlines();self.assertEqual(locks,[]);repo_bytes=sum(f.stat().st_size for f in(p/'repo').rglob('*')if f.is_file());self.assertLess(repo_bytes,2*1024*1024)
   print(json.dumps({'scope':'local-native16-staged-derive-proof','snapshots':16,'actual_native_four_json_batches':batch.stats['native_batches'],'native_tree_cli_processes':batch.reader.calls,'native_tree_cache_hits':batch.catalog.stats['tree_cache_hits'],'native_subtree_reads':batch.catalog.stats['native_subtree_reads'],'native_max_live_children':batch.reader.max_live_children,'cache_bytes':batch.stats['staged_cache_bytes'],'metadata_elapsed_seconds':round(time.monotonic()-start,3),'fixture_repository_bytes':repo_bytes,'native_locks_remaining':0,'cloud_reads':0,'physical_PG_replay_claimed':False,'future_volume_performance_claimed':False}),flush=True)
 def test_builder_only_new_copy_and_unchanged_workflow_script_sources(self):
  for p in ENGINE.glob('*.py'):compile(p.read_text(),p.name,'exec')
  audit=(ENGINE/'retention-audit.py').read_text();checker=(ENGINE/'retention-readonly-check.py').read_text();self.assertIn('staged_derive(derive',audit);self.assertIn('budget.phase_timeout',checker);self.assertIn('child_subset=None',(ENGINE/'hourly_recovery.py').read_text());self.assertNotIn('staged_derive(', (ROOT/'scripts/retention-audit.py').read_text())
if __name__=='__main__':
 try:unittest.main()
 finally:TMP.cleanup()