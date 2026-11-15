"""Existing generated engine wiring tests; synthetic metadata, no network."""
import copy,importlib.util,json,pathlib,tempfile,time,unittest
HERE=pathlib.Path(__file__).parent
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
f=load('same_job_fixture_only',HERE/'same-job-fresh-tail-test.py')
m=load('existing_coordinator_wiring',HERE/'publication-existing-coordinator.proposed.py')
class Tests(unittest.TestCase):
 def fixture(self):return f.Tests().setup_data()
 def test_actual_generated_warm_tail_uses_no_old_payload_native_reads(self):
  d,static,cache,dump,reads=self.fixture();calls=[]
  def native(args,timeout):
   self.assertGreater(timeout,0);self.assertLessEqual(timeout,10);calls.append(args)
   if args==['snapshots','--json']:return json.dumps(d[0]).encode()
   self.assertEqual(args[:3],['forget','--dry-run','--json']);host=args[args.index('--host')+1]
   original=d[1][0][0];group={k:[r for r in original[k]if r['hostname']==host]for k in('keep','remove')}
   return json.dumps([group]).encode()
  with tempfile.TemporaryDirectory()as work:
   candidate,inventory=m.fresh_native(cache,f.OUT,{'PATH':'/usr/bin:/bin','RESTIC_REPOSITORY':'LOCAL-UNUSED-NO-NETWORK'},pathlib.Path(work),native,d[2],static,time.monotonic()+40)
  self.assertEqual(candidate['remove_snapshot_ids'],['d'*64]);self.assertEqual(reads,[]);self.assertEqual(len(calls),5);self.assertEqual(inventory,d[0])
 def zero_bundle(self):
  d,static,cache,dump,reads=self.fixture();static['protected'].append('d'*64)
  from retention_safety_candidate import move_explicit_holds_before_derive
  plans=move_explicit_holds_before_derive(d[1],static['protected'])
  edges,parents,plans=f.derive(d[0],plans,d[2],static['hourly_overrides'],static['restored'],dump)
  protected=sorted(set(static['protected'])|parents);candidate=f.planner.build(d[0],plans,protected,static['restored'],[],edges)
  bundle={'schema':1,'policy':d[2],'inventory':d[0],'plans':plans,'protected':protected,'restored':static['restored'],'dependencies':[],'hourly_recovery':edges,'candidate':candidate}
  self.assertEqual(candidate['remove_snapshot_ids'],[]);return bundle,d[2],static
 def test_zero_actual_planner_branch_never_uses_ssh_or_hold(self):
  bundle,policy,static=self.zero_bundle();used=[]
  def forbidden(*a,**k):raise AssertionError('Zero candidate must not invoke transport')
  result=m.coordinate(bundle,f.OUT,{},None,forbidden,policy,static,None,'b'*64,'review',forbidden,forbidden,lambda c:used.append(c)or{'component_restore_verified':True})
  self.assertEqual(len(used),1);self.assertFalse(result['hold_acquired']);self.assertTrue(result['component_restore_verified'])
 def test_zero_branch_still_rejects_changed_owner_evidence(self):
  bundle,policy,static=self.zero_bundle();bundle['dependencies']=[{'changed':True}]
  with self.assertRaisesRegex(ValueError,'metadata differs'):m.coordinate(bundle,f.OUT,{},None,None,policy,static,None,'b'*64,'review',None,None,None)
 def test_existing_ssh_nonce_is_stdin_not_argv(self):
  calls=[]
  def bounded(argv,env,timeout,input):calls.append((argv,env,timeout,json.loads(input)));return b'{"acquired":true}'
  rpc=m.ExistingSSH(['ssh','-T','fixed-target'],{'PATH':'/usr/bin:/bin'},bounded);rpc.acquire('a'*64,'b'*64,120)
  argv,env,timeout,body=calls[0];self.assertEqual(argv[-1],'publication-acquire');self.assertNotIn('a'*64,argv);self.assertEqual(body['owner_nonce'],'a'*64);self.assertEqual(timeout,15)
 def test_ssh_cannot_inherit_provider_credentials(self):
  for key in('AWS_SECRET_ACCESS_KEY','NEO_PROVIDER_KEY','RESTIC_PASSWORD'):
   with self.assertRaises(ValueError):m.ExistingSSH(['ssh','fixed-target'],{key:'SYNTHETIC'},None)

if __name__=='__main__':
 try:unittest.main()
 finally:f.TEMP.cleanup()
