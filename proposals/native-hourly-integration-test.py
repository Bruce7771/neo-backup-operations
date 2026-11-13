#!/usr/bin/env python3
"""Generated ACTUAL engine copy; synthetic native IO; no cloud/credentials."""
import hashlib,importlib.util,json,os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
build=load('builder',Path(__file__).with_name('build-native-engine.proposed.py')).build
TEST=tempfile.TemporaryDirectory(prefix='neo-native-engine-synthetic-');ENGINE=build(ROOT/'scripts',Path(TEST.name)/'engine');sys.path.insert(0,str(ENGINE))
from hourly_metadata_batch import NativeHourlyMetadataBatch,BoundedNativeCLI
from native_pg_catalog_v2 import NativePGCatalog
enc=lambda x:json.dumps(x,sort_keys=True).encode();sha=lambda x:hashlib.sha256(x).hexdigest()
class Integration(unittest.TestCase):
 def fixture(self,v3=True,multi_seal=False):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.scope={'kind':'hourly','host':'fixture','tag':'hourly','paths':['/fixture']};self.sid='a'*64;self.inv=[dict(id=self.sid,hostname='fixture',tags=['hourly'],paths=['/fixture'])];self.calls=[];self.reads=[]
  files=[dict(path='base/data',bytes=3,sha256=sha(b'abc'))];self.seal=enc({'schema':3,'files':files});self.files=files
  payload={'capture-result.json':enc({'scope':'fixture'}),'postgres-point.private.json':enc({'marker':'fixture'}),'postgres-archive-delivery.json':enc({'schema':3 if v3 else 2,'sealed_pg_sha256':sha(self.seal)})}
  if v3:payload['postgres-selfcontained/sealed-pg.json']=self.seal
  outer=enc([dict(path=p,bytes=len(raw),sha256=sha(raw))for p,raw in payload.items()]);self.payload=dict(payload,**{'manifest.json':outer})
  base=enc({'nodes':[{'name':'data','type':'file','size':3,'content':[sha(b'abc')]}]});self.treebytes={sha(base):base}
  self.pgroot=enc({'nodes':[{'name':'base','type':'dir','subtree':sha(base)},{'name':'sealed-pg.json','type':'file','size':len(self.seal),'content':[sha(b'chunk1'),sha(b'chunk2')]if multi_seal else[sha(self.seal)]}]})
  def restore(args,env,deadline):
   self.calls.append(args);self.assertEqual(args[:3],['restic','restore','--verify']);self.assertNotIn('--no-lock',args)
   i=args.index('--target');target=Path(args[i+1]);sid=args[i+2];self.assertEqual(sid,self.sid)
   for k in range(i+3,len(args),2):
    self.assertEqual(args[k],'--include');p=args[k+1];name=p.removeprefix('/fixture/')
    if name in self.payload:
     f=target/p.lstrip('/');f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(self.payload[name])
  class Reader:
   calls=0;output_bytes=0
   def read(inner,args,maximum):
    self.reads.append(args);inner.calls+=1
    if args[:2]==['cat','tree']:self.assertEqual(args[2],self.sid+':/fixture/postgres-selfcontained');raw=self.pgroot
    elif args[:2]==['cat','blob']:raw=self.treebytes[args[2]]
    elif args[0]=='dump':self.assertEqual(args[1],self.sid);raw=self.payload[args[2].removeprefix('/fixture/')]
    else:raise AssertionError(args)
    self.assertLessEqual(len(raw),maximum);inner.output_bytes+=len(raw);return raw
  b=NativeHourlyMetadataBatch(Path(self.temp.name)/'cache',{'RESTIC_REPOSITORY':'s3:https://fixture.invalid/restic'},self.inv,self.scope,time.monotonic()+180,restore,Reader());return b
 def test_v3_four_JSON_no_outer_default_locked_exact_api(self):
  b=self.fixture()
  for name in set(self.payload)-{'manifest.json'}:b.get(self.sid,'/fixture/'+name,8*1024*1024)
  self.assertEqual(len(self.calls),1);self.assertEqual(len(self.calls[0][self.calls[0].index('--include'):]),8);self.assertNotIn('/fixture/manifest.json',self.calls[0]);self.assertEqual(b.stats['native_v3_four_json_points'],1)
  p=b.verify_catalog(self.sid,'/fixture',self.files,self.seal);self.assertFalse(p['physical_restore_claimed']);self.assertFalse(any(a[0]=='dump'for a in self.reads))
 def test_multiblob_seal_without_origin_refused_even_correct_length(self):
  b=self.fixture(multi_seal=True)
  with self.assertRaisesRegex(ValueError,'provenance'):b.verify_catalog(self.sid,'/fixture',self.files,self.seal)
 def test_multiblob_seal_exact_native_restore_provenance_passes(self):
  b=self.fixture(multi_seal=True);b.get(self.sid,'/fixture/postgres-selfcontained/sealed-pg.json',8*1024*1024);self.assertEqual(b.verify_catalog(self.sid,'/fixture',self.files,self.seal)['file_rows'],1)
  with self.assertRaisesRegex(ValueError,'provenance'):b.verify_catalog(self.sid,'/fixture',self.files,b'X'*len(self.seal))
 def test_cross_snapshot_provenance_refused(self):
  b=self.fixture();b.get(self.sid,'/fixture/postgres-selfcontained/sealed-pg.json',8*1024*1024)
  with self.assertRaises(ValueError):b.assert_native_origin('b'*64,'/fixture/postgres-selfcontained/sealed-pg.json',self.seal)
 def test_legacy_fallback_still_uses_original_manifest_validator(self):
  b=self.fixture(False);b.get(self.sid,'/fixture/capture-result.json',8*1024*1024);self.assertEqual(len(self.calls),2);self.assertIn('/fixture/manifest.json',self.calls[1]);self.assertEqual(b.stats['legacy_full_manifest_points'],1)
 def test_unknown_manifest_returns_actual_native_bytes(self):
  b=self.fixture();raw=b.get(self.sid,'/fixture/manifest.json',8*1024*1024);self.assertEqual(raw,self.payload['manifest.json']);self.assertEqual(self.calls,[]);self.assertEqual(self.reads,[['dump',self.sid,'/fixture/manifest.json']])
 def test_bad_native_v3_delivery_seal_binding_rejected(self):
  b=self.fixture();self.payload['postgres-selfcontained/sealed-pg.json']=b'{}'
  with self.assertRaisesRegex(ValueError,'fingerprint'):b.get(self.sid,'/fixture/capture-result.json',8*1024*1024)
 def test_cli_only_bounded_default_locked_calls(self):
  seen=[]
  def execute(args,**kw):seen.append(args);kw['stdout'].write(b'{}');self.assertTrue(kw['check']);self.assertLessEqual(kw['timeout'],35)
  with tempfile.TemporaryDirectory()as d:
   c=BoundedNativeCLI({},time.monotonic()+180,d,execute);self.assertEqual(c.read(['cat','tree','a'*64+':/fixture/postgres-selfcontained'],1024),b'{}');self.assertEqual(seen[0][0:3],['restic','cat','tree']);self.assertNotIn('--no-lock',seen[0])
   with self.assertRaises(ValueError):c.read(['forget','a'*64],1024)
   c.deadline=time.monotonic()-1
   with self.assertRaises(TimeoutError):c.read(['cat','blob','b'*64],1024)
 def test_ACTUAL_derive_through_native_batch_catalog_and_actual_planner(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  fixture=load('integrated_v3_fixture',ENGINE/'hourly_selfcontained_v3_test.py').SelfContained();data=fixture.fixture();inventory,plans,policy,external,restored,blobs=data;sid='e'*64;root='/fixture/hourly';scope=policy['scopes'][1];seal=blobs[sid,root+'/postgres-selfcontained/sealed-pg.json'];rows=json.loads(seal)['files'];trees={};nodes=[];calls=[];reads=[]
  for directory in ('base','wal'):
   children=[{'name':r['path'].split('/')[1],'type':'file','size':r['bytes'],'content':[r['sha256']]}for r in rows if r['path'].startswith(directory+'/')];raw=enc({'nodes':children});trees[sha(raw)]=raw;nodes.append({'name':directory,'type':'dir','subtree':sha(raw)})
  nodes.append({'name':'sealed-pg.json','type':'file','size':len(seal),'content':[sha(seal)]});pgroot=enc({'nodes':nodes})
  def restore(args,env,deadline):
   calls.append(args);self.assertNotIn('--no-lock',args);i=args.index('--target');target=Path(args[i+1]);snapshot=args[i+2]
   for k in range(i+3,len(args),2):
    path=args[k+1]
    if (snapshot,path)in blobs:
     p=target/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blobs[snapshot,path])
  class Reader:
   calls=0;output_bytes=0
   def read(obj,args,maximum):
    reads.append(args);obj.calls+=1
    if args[:2]==['cat','tree']:self.assertEqual(args[2],sid+':'+root+'/postgres-selfcontained');raw=pgroot
    elif args[:2]==['cat','blob']:raw=trees[args[2]]
    else:raise AssertionError('No full outer fetch needed in direct-file fixture')
    obj.output_bytes+=len(raw);return raw
  b=NativeHourlyMetadataBatch(Path(self.temp.name)/'cache',{'RESTIC_REPOSITORY':'s3:https://fixture.invalid/restic'},inventory,scope,time.monotonic()+180,restore,Reader())
  def dump(s,p,n):
   if b.handles(s,p):return b.get(s,p,n)
   raw=blobs[s,p];self.assertLessEqual(len(raw),n);return raw
  dump.native_pg_catalog=b.verify_catalog
  from hourly_recovery import derive
  edges,parents,updated=derive(inventory,plans,policy,external,restored,dump);edge=next(e for e in edges if e['child_snapshot']==sid)
  self.assertEqual(edge['metadata_validation'],'native-PG-catalog-content-identity-v1');self.assertFalse(edge['postgres_named_target_restore_verified']);self.assertEqual(len(calls),1);self.assertEqual(parents,set())
  tags={'daily':'neo-daily','hourly':'neo-hourly-files','pitr':'neo-main-pitr'}
  for s in policy['scopes']:s['tag']=tags[s['kind']]
  for r in inventory:r['tags']=[tags[r['hostname']]]
  planner=load('native_integrated_planner',ENGINE/'retention-plan.py');planner.SCOPES={s['host']:(s['tag'],frozenset(s['paths']))for s in policy['scopes']};planner.FULL_MAIN_HOST='daily';planner.CONFIG_SCOPES={}
  result=planner.build(inventory,updated,['a'*64],['a'*64,'b'*64,'c'*64],[],edges);self.assertFalse(result['apply_ready']);self.assertEqual(result['remove_snapshot_ids'],['d'*64])
 def test_timeout_signals_own_child_and_reaps_without_unlock(self):
  from hourly_metadata_batch import graceful_native_run
  class Child:
   def __init__(obj):obj.events=[];obj.n=0
   def wait(obj,timeout):
    obj.events.append(('wait',timeout));obj.n+=1
    if obj.n==1:raise subprocess.TimeoutExpired('synthetic-native',timeout)
    return -signal.SIGINT
   def poll(obj):return None
   def send_signal(obj,s):obj.events.append(('signal',s))
   def kill(obj):obj.events.append(('kill',))
  child=Child()
  with patch('hourly_metadata_batch.subprocess.Popen',return_value=child):
   with self.assertRaises(subprocess.TimeoutExpired):graceful_native_run(['restic','cat','tree','synthetic'],{},None,None,True,1,None)
  self.assertEqual(child.events,[('wait',1),('signal',signal.SIGINT),('wait',8)])
 def test_generated_actual_audit_wiring_and_compile(self):
  source=(ENGINE/'retention-audit.py').read_text();compile(source,'actual-native-candidate','exec');self.assertIn('dump.native_pg_catalog=metadata_batch.verify_catalog',source);self.assertIn('NativeHourlyMetadataBatch as HourlyMetadataBatch',source);self.assertNotIn("['restic','--no-lock','dump'",source)
 def test_actual_v3_source_legacy_path_retained_and_separate_proof_scheme(self):
  source=(ENGINE/'hourly_selfcontained_v3.py').read_text();self.assertIn("outer_raw=dump(sid,root+'/manifest.json'",source);self.assertIn("metadata_validation='native-PG-catalog-content-identity-v1'",source);compile(source,'actual-v3-candidate','exec')
if __name__=='__main__':
 try:unittest.main()
 finally:TEST.cleanup()
