#!/usr/bin/env python3
"""Actual derive/planner fresh-tail tests, synthetic bytes and same process."""
import copy,hashlib,importlib.util,json,pathlib,pickle,sys,tempfile,time,unittest
HERE=pathlib.Path(__file__).parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
TEMP=tempfile.TemporaryDirectory();OUT=load('tailbuilder',HERE/'build-same-job-tail-retention-engine.proposed.py').build(HERE.parent/'scripts',pathlib.Path(TEMP.name)/'engine');sys.path[:0]=[str(OUT),str(HERE.parent/'scripts')]
import hourly_selfcontained_v3_test as fixture
from hourly_recovery import derive
from same_job_fresh_tail import SameJobEvidence,fresh_replan
planner=load('tailplanner',OUT/'retention-plan.py')
class Tests(unittest.TestCase):
 def setup_data(self):
  d=list(fixture.SelfContained().fixture());tags={'daily':'neo-daily','hourly':'neo-hourly-files','pitr':'neo-main-pitr'}
  for r in d[0]:r['tags']=[tags[r['hostname']]]
  for s in d[2]['scopes']:s['tag']=tags[s['kind']]
  static={'protected':['a'*64],'restored':['a'*64,'b'*64,'c'*64],'dependencies':[],'hourly_overrides':d[3]};all_edges={};bases=set();reads=[]
  def dump(sid,path,maximum):reads.append((sid,path));raw=d[-1][sid,path];self.assertLessEqual(len(raw),maximum);return raw
  dump.classified_edges_observer=lambda edges:all_edges.update({e['child_snapshot']:e for e in edges});dump.accepted_base_observer=lambda x:bases.update(x)
  edges,parents,plans=derive(d[0],d[1],d[2],static['hourly_overrides'],static['restored'],dump)
  planner.SCOPES={s['host']:(s['tag'],frozenset(s['paths']))for s in d[2]['scopes']};planner.FULL_MAIN_HOST='daily';planner.CONFIG_SCOPES={};protected=sorted(set(static['protected'])|parents);candidate=planner.build(d[0],plans,protected,static['restored'],[],edges);candidate['hourly_metadata_read']={'staged_final_replay_verified':1,'catalog_cli_processes':10,'catalog_cli_selected_bytes':1000}
  bundle={'schema':1,'inventory':copy.deepcopy(d[0]),'plans':plans,'policy':d[2],'protected':protected,'restored':static['restored'],'dependencies':[],'hourly_recovery':edges,'candidate':candidate,'all_classified_hourly_recovery':list(all_edges.values()),'accepted_restore_base_sha256':sorted(bases)}
  def validate(b,p,s):
   self.assertEqual(p,b['policy']);v=planner.build(b['inventory'],b['plans'],b['protected'],b['restored'],b['dependencies'],b['hourly_recovery']);want=dict(b['candidate']);want.pop('hourly_metadata_read');self.assertEqual(v,want)
  cache=SameJobEvidence(bundle,d[2],static,validate);reads.clear();dump.publication_tail_limits=cache.transport_limits();dump.publication_selected_json_usage=lambda:cache.used_json+sum(len(d[-1][key])for key in reads);return d,static,cache,dump,reads
 def runfresh(self,x,inventory=None,plans=None,confirm=None):
  d,s,c,dump,reads=x;inv=inventory or d[0];return fresh_replan(c,inv,plans or d[1],d[2],s,derive,planner,dump,confirm or(lambda:copy.deepcopy(inv)),deadline=time.monotonic()+40)
 def test_unchanged_prefix_reuses_exact_evidence_zero_old_native_reads(self):
  x=self.setup_data();r=self.runfresh(x);self.assertEqual(x[-1],[]);self.assertEqual(r['remove_snapshot_ids'],['d'*64]);self.assertTrue(r['inventory_stable_for_admission'])
 def test_new_tail_only_authenticates_new_child_and_its_parent_refs(self):
  x=self.setup_data();d,static,cache,dump,reads=x;f=dict(d[0][-1],id='f'*64);d[0]=d[0]+[f];d[1][0][0]['keep'].append(f)
  marker={'restore_point':'neo_hourly_1234567890_abcdef01','wal_segment':'A'*24};delivery={'archive_delivery_verified':True,'wal_snapshot':'d'*64,'wal_segment':'A'*24,'wal_sha256':hashlib.sha256(d[-1]['d'*64,'/fixture/pitr/wal/'+'A'*24+'.gz']).hexdigest(),'marker_restore_point':marker['restore_point']}
  for path,obj in [('capture-result.json',{'scope':'neo-hourly-write-fenced-capture','sqlite_verified':6,'postgres_marker_recorded':True}),('postgres-point.private.json',marker),('postgres-archive-delivery.json',delivery)]:d[-1]['f'*64,'/fixture/hourly/'+path]=json.dumps(obj,sort_keys=True).encode()
  r=self.runfresh(x);self.assertEqual(r['remove_snapshot_ids'],[]);self.assertTrue({'f'*64,'d'*64}>={sid for sid,path in reads});self.assertNotIn('e'*64,{sid for sid,path in reads});self.assertIn('d'*64,r['protected_snapshot_ids'])
 def test_old_immutable_metadata_substitution_refused(self):
  x=self.setup_data();x[0][0][0]['paths']=['/changed']
  with self.assertRaisesRegex(ValueError,'Immutable old'):self.runfresh(x)
 def test_policy_change_refused(self):
  x=self.setup_data();x[0][2]['schema']=999
  with self.assertRaisesRegex(ValueError,'policy/evidence'):self.runfresh(x)
 def test_incomplete_initial_all_hourly_proof_refused(self):
  x=self.setup_data();cache=x[2];cache.edges.pop('e'*64)
  with self.assertRaisesRegex(ValueError,'Private preplan'):self.runfresh(x)
 def test_append_during_hold_final_confirmation_refused(self):
  x=self.setup_data()
  with self.assertRaisesRegex(ValueError,'Publication changed'):self.runfresh(x,confirm=lambda:x[0][0]+[dict(x[0][0][0],id='f'*64)])
 def test_no_cross_run_serialization_or_second_admission(self):
  x=self.setup_data()
  with self.assertRaises(TypeError):pickle.dumps(x[2])
  self.runfresh(x)
  with self.assertRaisesRegex(ValueError,'no replay'):self.runfresh(x)
 def test_no_native_process_budget_reset(self):
  x=self.setup_data();self.assertEqual(x[2].transport_limits()['max_live'],4);x[2].used_calls=4096
  with self.assertRaisesRegex(ValueError,'cap exhausted'):x[2].transport_limits()
if __name__=='__main__':
 try:unittest.main()
 finally:TEMP.cleanup()
