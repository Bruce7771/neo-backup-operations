#!/usr/bin/env python3
"""Bounded controller tests with real durable files; no native/B2 calls."""
import importlib.util,pathlib,tempfile,hashlib,json,unittest
HERE=pathlib.Path(__file__).parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('coordinator',HERE/'publication-coordinator-core.proposed.py');gmod=load('gate',HERE/'durable-publication-hold.proposed.py')
class Tests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.clock=[0.];self.g=gmod.Gate(pathlib.Path(self.temp.name),now=lambda:self.clock[0]);self.rows=[{'id':'a'*64},{'id':'b'*64}];self.c={'remove_snapshot_ids':['a'*64],'protected_snapshot_ids':['b'*64],'retained_snapshot_ids':['b'*64],'inventory_stable_for_admission':True,'apply_ready':False};self.post_held=None
 def tearDown(self):self.temp.cleanup()
 def digest(self,c):return hashlib.sha256(json.dumps(c['remove_snapshot_ids']).encode()).hexdigest()
 def execute(self,fresh=None,forget=None,pre=None):
  def native(ids,timeout):self.assertLessEqual(timeout,60);self.rows=[r for r in self.rows if r['id']not in ids]
  def post(c):self.post_held=self.g.status()['held'];return {'component_restore_verified':True}
  gate=self.g
  class DirectFixtureRPC:
   def __getattr__(self,name):
    def call(*args,rpc_timeout=None,deadline=None,**kwargs):return getattr(gate,name)(*args,**kwargs)
    return call
  return m.execute(pre or self.c,self.digest(pre or self.c),self.digest,'b'*64,DirectFixtureRPC(),fresh or(lambda deadline:(self.c,list(self.rows))),forget or native,lambda timeout:list(self.rows),post,now=lambda:self.clock[0])
 def test_zero_current_candidate_does_not_take_hold_or_mutate(self):
  r=self.execute(pre=dict(self.c,remove_snapshot_ids=[]));self.assertFalse(r['hold_acquired']);self.assertEqual(len(self.rows),2)
 def test_exact_success_releases_before_component_check(self):
  r=self.execute();self.assertEqual(r['deleted_snapshots'],1);self.assertFalse(self.post_held);self.assertFalse(self.g.status()['held'])
 def test_fresh_zero_no_forced_delete(self):
  r=self.execute(fresh=lambda d:(dict(self.c,remove_snapshot_ids=[]),list(self.rows)));self.assertEqual(r['deleted_snapshots'],0);self.assertEqual(len(self.rows),2);self.assertFalse(self.g.status()['held'])
 def test_fresh_plan_changed_requires_review_and_unfences_before_native(self):
  with self.assertRaisesRegex(ValueError,'new exact review'):self.execute(fresh=lambda d:(dict(self.c,remove_snapshot_ids=['b'*64]),list(self.rows)))
  self.assertFalse(self.g.status()['held']);self.assertEqual(len(self.rows),2)
 def test_unknown_native_error_leaves_uncertain_hold(self):
  def failed(ids,t):raise RuntimeError('synthetic uncertain result')
  with self.assertRaises(RuntimeError):self.execute(forget=failed)
  self.assertTrue(self.g.status()['held']);self.assertEqual(self.g.status()['phase'],'uncertain')
 def test_extra_disappearance_leaves_hold(self):
  def extra(ids,t):self.rows=[]
  with self.assertRaisesRegex(ValueError,'unexpected'):self.execute(forget=extra)
  self.assertTrue(self.g.status()['held'])
 def test_late_fresh_tail_releases_without_native(self):
  def fresh(d):self.clock[0]=46.;return self.c,list(self.rows)
  with self.assertRaisesRegex(ValueError,'45-second'):self.execute(fresh=fresh)
  self.assertFalse(self.g.status()['held']);self.assertEqual(len(self.rows),2)
 def test_time_for_transition_is_reserved(self):
  def fresh(d):self.clock[0]=44.;return self.c,list(self.rows)
  def native(ids,t):self.assertLessEqual(t,16);self.rows=self.rows[1:];self.clock[0]+=t
  r=self.execute(fresh=fresh,forget=native);self.assertEqual(r['deleted_snapshots'],1);self.assertLess(self.clock[0],120)
 def test_protected_removal_rejected_before_native(self):
  c=dict(self.c,protected_snapshot_ids=['a'*64,'b'*64])
  with self.assertRaisesRegex(ValueError,'protection'):self.execute(fresh=lambda d:(c,list(self.rows)))
  self.assertEqual(len(self.rows),2);self.assertFalse(self.g.status()['held'])
if __name__=='__main__':unittest.main()
