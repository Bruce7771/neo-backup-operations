"""SOURCE-ONLY preplan reservation/readonly tests; no credentials or cloud."""
import importlib.util,pathlib,subprocess,sys,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
H=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('per_io_launcher',H/'run-publication-retention.candidate.py');launcher=importlib.util.module_from_spec(s);s.loader.exec_module(launcher)

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class Tests(unittest.TestCase):
 def setup_engine(self):
  td=tempfile.TemporaryDirectory();self.addCleanup(td.cleanup);engine=launcher.build_engine(H,pathlib.Path(td.name)/'engine');sys.path.insert(0,str(engine));self.addCleanup(lambda:sys.path.remove(str(engine)))
  return engine,load('per_io_budget',engine/'staged_derive.py'),load('per_io_transport',engine/'native_parallel_transport.py')
 def test_concurrent_reservations_global_and_segment_limits(self):
  _,m,_=self.setup_engine();clock=[0];b=m.Budget(start=0,now=lambda:clock[0]);self.assertEqual(b.begin_child(),300);clock[0]=211
  with ThreadPoolExecutor(max_workers=4)as pool:self.assertEqual(list(pool.map(lambda _:b.reserve_native_read(),range(4))),[511]*4)
  self.assertEqual(b.segments,2);self.assertEqual(b.metadata_end,3600);self.assertEqual(b.job_end,4500)
  clock[0]=3511
  with self.assertRaises(TimeoutError):b.reserve_native_read()
  clock[0]=1000;b.segments=30;b.segment_end=1001
  with self.assertRaises(ValueError):b.reserve_native_read()
 def test_slot_wait_reserves_again_after_acquire(self):
  engine,m,n=self.setup_engine();clock=[0];b=m.Budget(start=0,now=lambda:clock[0]);b.begin_child();clock[0]=200;calls=[]
  class Slot:
   def acquire(self,timeout):clock[0]=250;return True
   def release(self):pass
  class Child:
   pid=99999999
   def poll(self):return 0
   def wait(self,timeout):return 0
  def reserve():calls.append(clock[0]);return b.reserve_native_read()
  with patch.object(n.time,'monotonic',side_effect=lambda:clock[0]),patch.object(n,'external_command',side_effect=lambda a,e:a):
   r=n.ParallelNativeCLI({},3600,engine,deadline_reserver=reserve,preplan_read_only_nolock=True,popen=lambda*a,**k:Child());r._slots=Slot();r.read(['cat','blob','a'*64],1024)
  self.assertEqual(calls,[200,250]);self.assertEqual(b.segment_end,550);self.assertEqual(b.segments,2)
 def test_renewing_another_worker_cannot_extend_inflight(self):
  engine,m,n=self.setup_engine();clock=[0];b=m.Budget(start=0,now=lambda:clock[0]);b.begin_child();clock[0]=200
  class Child:
   pid=99999999;code=None;renewed=False
   def poll(self):return self.code
   def wait(self,timeout):
    if self.code is not None:return self.code
    if not self.renewed:clock[0]=211;b.reserve_native_read();self.renewed=True
    else:clock[0]+=timeout
    raise subprocess.TimeoutExpired('SYNTHETIC',timeout)
   def send_signal(self,s):self.code=-2
   def kill(self):self.code=-9
  with patch.object(n.time,'monotonic',side_effect=lambda:clock[0]),patch.object(n,'external_command',side_effect=lambda a,e:a):
   r=n.ParallelNativeCLI({},3600,engine,deadline_reserver=b.reserve_native_read,preplan_read_only_nolock=True,popen=lambda*a,**k:Child())
   with self.assertRaises(subprocess.TimeoutExpired):r.read(['cat','blob','a'*64],1024)
  self.assertEqual(b.segment_end,511);self.assertEqual(r.timeout_diagnostic['native_timeout_deadline_kind'],1);self.assertTrue(89900<=r.timeout_diagnostic['native_timeout_childwait_ms']<=90100)
 def test_four_workers_bounded_and_cancelled_reader_cannot_reserve(self):
  engine,m,n=self.setup_engine();b=m.Budget();barrier=threading.Barrier(4);commands=[]
  class Child:
   def __init__(self,pid):self.pid=pid
   def poll(self):return 0
   def wait(self,timeout):barrier.wait(timeout=3);return 0
  def spawn(args,**kwargs):commands.append(args);return Child(99999000+len(commands))
  r=n.ParallelNativeCLI({},b.metadata_end,engine,deadline_reserver=b.reserve_native_read,preplan_read_only_nolock=True,popen=spawn)
  with patch.object(n,'external_command',side_effect=lambda a,e:a),ThreadPoolExecutor(max_workers=4)as pool:list(pool.map(lambda _:r.read(['cat','blob','a'*64],1024),range(4)))
  self.assertEqual(r.max_live_children,4);self.assertEqual(len(commands),4);self.assertTrue(all(a[-5:]==['restic','--no-lock','cat','blob','a'*64]for a in commands));self.assertEqual(b.segments,1)
  r.cancel_all();before=b.segments
  with self.assertRaises(ValueError):r.read(['cat','blob','a'*64],1024)
  self.assertEqual(b.segments,before)
 def test_readonly_argv_is_exact_and_default_fresh_reader_has_no_options(self):
  engine,_,n=self.setup_engine();sid='a'*64
  for args in [['cat','blob',sid],['cat','tree',sid+':/fixture/postgres-selfcontained'],['dump',sid,'/fixture/sealed-pg.json']]:self.assertEqual(n.readonly_metadata_command(args),['restic','--no-lock']+args)
  for args in [['forget',sid,'--json'],['check','',''],['cat','blob','--option'],['cat','tree',sid+':/a/../b'],['dump',sid,'--option'],['dump',sid,'/x','--target'],['cat','blob',sid+'\n']]:
   with self.assertRaises(ValueError):n.readonly_metadata_command(args)
  r=n.ParallelNativeCLI({},45,engine);self.assertIsNone(r.deadline_reserver);self.assertIs(r.preplan_read_only_nolock,False)
  with self.assertRaises(ValueError):n.ParallelNativeCLI({},45,engine,preplan_read_only_nolock='true')
 def test_callback_cannot_extend_configured_ceiling(self):
  engine,_,n=self.setup_engine();spawned=[]
  r=n.ParallelNativeCLI({},45,engine,deadline_reserver=lambda:46,popen=lambda*a,**k:spawned.append(True))
  with self.assertRaisesRegex(ValueError,'exceeds configured absolute deadline'):r.read(['cat','blob','a'*64],1024)
  self.assertEqual(spawned,[])
 def test_maintenance_scope_wiring_and_base_unchanged(self):
  engine,_,_=self.setup_engine();staged=(engine/'staged_derive.py').read_text();audit=(engine/'retention-audit.py').read_text();base=(H/'staged-derive.proposed.py').read_text()
  self.assertIn('batch.reader.deadline_reserver=budget.reserve_native_read',staged);self.assertIn('catalog.deadline=budget.metadata_end',staged);self.assertIn('batch.reader.deadline_reserver=old_reserver',staged);self.assertIn('batch.restore=old_restore',staged)
  self.assertNotIn('reserve_native_read',base);self.assertIn('BUDGET.reserve_native_read()',audit);self.assertIn("readonly_metadata_command(['dump',snapshot,path])",audit)
  fresh=(H/'publication-existing-coordinator.proposed.py').read_text();self.assertNotIn('deadline_reserver=',fresh);self.assertNotIn('preplan_read_only_nolock=',fresh);self.assertIn('fresh_candidate(start+45)',(H/'publication-coordinator-core.proposed.py').read_text())

if __name__=='__main__':unittest.main()
