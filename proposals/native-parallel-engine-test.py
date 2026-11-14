#!/usr/bin/env python3
"""Inactive parallel engine tests: no cloud, key or deployed-code changes."""
import hashlib,importlib.util,json,os,subprocess,sys,tempfile,threading,time,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE=Path(__file__).parent;ROOT=HERE.parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
TEMP=tempfile.TemporaryDirectory(prefix='neo-parallel-tests-');ENGINE=load('builder',HERE/'build-native-parallel-engine.proposed.py').build(ROOT/'scripts',Path(TEMP.name)/'engine');sys.path.insert(0,str(ENGINE))
from native_parallel_catalog import ParallelPGCatalog
from native_parallel_transport import ParallelNativeCLI
enc=lambda x:json.dumps(x,sort_keys=True).encode();sha=lambda x:hashlib.sha256(x).hexdigest()
class Catalog(unittest.TestCase):
 def fixture(self,dirs=10,duplicate=False,reverse=False):
  self.calls=[];self.event=threading.Event();self.active=0;self.peak=0;self.guard=threading.Lock();files=[];trees={};nodes=[]
  for i in range(dirs):
   payload=b'same'if duplicate else('file'+str(i)).encode();row={'path':'d'+str(i).zfill(2)+'/payload','bytes':len(payload),'sha256':sha(payload)};files.append(row)
   raw=enc({'nodes':[{'name':'payload','type':'file','size':len(payload),'content':[sha(payload)]}]});trees[sha(raw)]=raw;nodes.append({'name':row['path'].split('/')[0],'type':'dir','subtree':sha(raw)})
  seal=enc({'schema':3,'files':files});nodes.append({'name':'sealed-pg.json','type':'file','size':len(seal),'content':[sha(seal)]});root=enc({'nodes':nodes});ordered=list(trees)
  def blob(i):
   with self.guard:self.calls.append(i);self.active+=1;self.peak=max(self.peak,self.active)
   try:
    index=ordered.index(i);delay=.005*(len(ordered)-index if reverse else index+1);end=time.monotonic()+delay
    while time.monotonic()<end:
     if self.event.wait(.001):raise RuntimeError('Synthetic cancelled')
    return trees[i]
   finally:
    with self.guard:self.active-=1
  scope={'host':'fixture','tag':'hourly','paths':['/fixture']};inventory=[dict(id='a'*64,hostname='fixture',tags=['hourly'],paths=['/fixture'])]
  c=ParallelPGCatalog('synthetic',scope,inventory,lambda *a:root,blob,time.monotonic()+5,authenticated_file_origin=lambda *a:True,cancel_callback=self.event.set)
  return c,files,seal,trees
 def test_out_of_order_deterministic_proof_main_thread_auth_max4(self):
  c,f,s,_=self.fixture(reverse=True);main=threading.get_ident();seen=[];parse=c.tree
  def check(*a,**k):seen.append(threading.get_ident());return parse(*a,**k)
  c.tree=check;p=c.verify('a'*64,f,s);self.assertTrue(all(i==main for i in seen));self.assertLessEqual(self.peak,4);self.assertGreater(self.peak,1)
  q,g,t,_=self.fixture(reverse=False);self.assertEqual(p['catalog_proof_sha256'],q.verify('a'*64,g,t)['catalog_proof_sha256'])
 def test_duplicate_tree_ids_join_one_worker(self):
  c,f,s,_=self.fixture(8,True);c.verify('a'*64,f,s);self.assertEqual(len(self.calls),1)
 def test_corrupt_early_result_cancels_other_workers(self):
  c,f,s,trees=self.fixture(4);original=c.read_blob_tree;first=next(iter(trees))
  def raw(i):
   if i==first:return b'{"nodes":[]}'
   end=time.monotonic()+.5
   while time.monotonic()<end:
    if self.event.wait(.002):raise RuntimeError('Synthetic cancelled')
   return original(i)
  c.read_blob_tree=raw;start=time.monotonic()
  with self.assertRaisesRegex(ValueError,'subtree hash'):c.verify('a'*64,f,s)
  self.assertTrue(self.event.is_set());self.assertLess(time.monotonic()-start,.3)
 def test_LRU_evicts_across_points_preserves_hash_authority(self):
  c,_,_,_=self.fixture(1);c.max_trees=2;roots={};raws={}
  for i in range(5):
   raw=enc({'nodes':[{'name':'payload','type':'file','size':1,'content':[sha(bytes([i]))]}]});raws[sha(raw)]=raw;roots[str(i)*64]=enc({'nodes':[{'name':'base','type':'dir','subtree':sha(raw)}]})
  c.allowed=set(roots);c.read_tree=lambda sid,p:roots[sid];c.read_blob_tree=lambda i:raws[i];c.proven_hashes[(9,('f'*64,))]='e'*64
  for sid in roots:c.nodes(sid)
  self.assertLessEqual(len(c.tree_cache),2);self.assertGreaterEqual(c.stats['tree_cache_evictions'],3);self.assertEqual(c.proven_hashes[(9,('f'*64,))],'e'*64)
 def test_deadline_cancels_raw_workers(self):
  c,f,s,_=self.fixture(4);c.deadline=time.monotonic()+.01
  def slow(i):
   while not self.event.wait(.001):pass
   raise RuntimeError('Synthetic cancelled')
  c.read_blob_tree=slow
  with self.assertRaises(TimeoutError):c.verify('a'*64,f,s)
  self.assertTrue(self.event.is_set())

class EngineAPI(unittest.TestCase):
 def test_actual_batch_constructor_compile_and_existing12_API_regressions(self):
  # Import the NEW generated batch before loading unchanged API regression cases.
  import hourly_metadata_batch as batch
  with tempfile.TemporaryDirectory()as d:
   obj=batch.NativeHourlyMetadataBatch(Path(d)/'cache',{'RESTIC_REPOSITORY':'s3:https://fixture.invalid/restic'},[dict(id='a'*64,hostname='fixture',tags=['hourly'],paths=['/fixture'])],{'host':'fixture','tag':'hourly','paths':['/fixture']},time.monotonic()+5)
   self.assertIsInstance(obj.reader,ParallelNativeCLI);self.assertIsInstance(obj.catalog,ParallelPGCatalog);self.assertEqual(obj.reader.calls,0)
  for p in ENGINE.glob('*.py'):compile(p.read_text(),p.name,'exec')
  cases=load('unchanged_native_api_regressions',HERE/'native-hourly-integration-test.py')
  try:
   result=unittest.TestResult();unittest.defaultTestLoader.loadTestsFromTestCase(cases.Integration).run(result)
   self.assertEqual(result.testsRun,12);self.assertEqual(result.failures,[]);self.assertEqual(result.errors,[])
  finally:cases.TEST.cleanup()
class Child:
 next_pid=98000000
 def __init__(self,stdout,duration=.08,payload=b'{}',ignore_signal=False):
  type(self).next_pid+=1;self.pid=type(self).next_pid;self.stdout=stdout;self.end=time.monotonic()+duration;self.payload=payload;self.returncode=None;self.reaped=False;self.signals=[];self.ignore=ignore_signal;self.written=False
 def poll(self):return self.returncode
 def wait(self,timeout):
  if self.returncode is None and time.monotonic()<self.end:
   time.sleep(min(timeout,.003))
   if self.returncode is None and time.monotonic()<self.end:raise subprocess.TimeoutExpired('synthetic',timeout)
  if self.returncode is None:self.returncode=0
  if self.returncode==0 and not self.written:self.stdout.write(self.payload);self.written=True
  self.reaped=True;return self.returncode
 def send_signal(self,s):
  self.signals.append(s)
  if not self.ignore:self.returncode=-s
 def kill(self):self.returncode=-9
class Transport(unittest.TestCase):
 def fixture(self,duration=.08,byte_limit=4096,process_limit=4096,deadline=5,ignore_signal=False):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.children=[];self.commands=[]
  def popen(cmd,**kw):self.commands.append(cmd);p=Child(kw['stdout'],duration,ignore_signal=ignore_signal);self.children.append(p);return p
  return ParallelNativeCLI({},time.monotonic()+deadline,self.tmp.name,popen=popen,byte_limit=byte_limit,process_limit=process_limit)
 def invoke(self,t,n=8):
  results=[]
  with ThreadPoolExecutor(max_workers=8)as p:
   for f in [p.submit(t.read,['cat','blob','f'*64],64)for _ in range(n)]:
    try:results.append(f.result())
    except (ValueError,TimeoutError,subprocess.TimeoutExpired):results.append(None)
  return results
 def test_global4_children_defaultSH_and_reaped(self):
  t=self.fixture();self.assertEqual(self.invoke(t),[b'{}']*8);self.assertEqual(t.calls,8);self.assertLessEqual(t.max_live_children,4);self.assertEqual(t.output_bytes,16);self.assertEqual(t._reserved,0);self.assertFalse(t._children);self.assertTrue(all(c.reaped for c in self.children));self.assertTrue(all('--no-lock'not in a for a in self.commands));self.assertTrue(all(a[0]=='/usr/bin/prlimit'for a in self.commands))
 def test_byte_reservation_race_fails_closed_cancels_and_reaps(self):
  t=self.fixture(byte_limit=128);self.invoke(t,4);self.assertLessEqual(t.calls,2);self.assertLessEqual(t.output_bytes,128);self.assertEqual(t._reserved,0);self.assertFalse(t._children);self.assertTrue(all(c.reaped for c in self.children))
 def test_process_budget_race(self):
  t=self.fixture(process_limit=2);self.invoke(t,4);self.assertEqual(t.calls,2);self.assertTrue(t._cancelled.is_set());self.assertTrue(all(c.reaped for c in self.children))
 def test_deadline_signals_and_reaps_all_own_children(self):
  t=self.fixture(duration=10,deadline=.05);start=time.monotonic();self.invoke(t,4);self.assertLess(time.monotonic()-start,1);self.assertTrue(all(c.signals and c.reaped for c in self.children));self.assertFalse(t._children)
 def test_REAL_owned_child_cancellation_reaps_ALL_without_cloud(self):
  with tempfile.TemporaryDirectory()as d:
   children=[]
   def popen(command,**kw):
    # Actual owned OS children, synthetic sleep only; no provider/native repo.
    p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(5)'],**kw);children.append(p);return p
   t=ParallelNativeCLI({},time.monotonic()+.2,d,popen=popen);start=time.monotonic();self.invoke(t,4)
   self.assertEqual(len(children),4);self.assertLessEqual(time.monotonic()-start,2);self.assertTrue(all(p.poll()is not None for p in children));self.assertFalse(t._children);self.assertEqual(t._reserved,0)
 def test_kill_fallback_reaps_signal_ignoring_own_child(self):
  t=self.fixture(duration=10,deadline=.02,ignore_signal=True);self.invoke(t,1);self.assertTrue(all(c.returncode==-9 and c.reaped for c in self.children));self.assertFalse(t._children)

if __name__=='__main__':
 try:unittest.main()
 finally:TEMP.cleanup()
