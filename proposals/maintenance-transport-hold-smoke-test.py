"""Fake SSH boundary only; test actual inline controller/finally, no network."""
import copy,json,os,pathlib,re,subprocess,sys,tempfile,textwrap,unittest
import yaml
HERE=pathlib.Path(__file__).parent
FILE=HERE/'maintenance-transport-hold-smoke.publication.yml'
DOC=yaml.safe_load(FILE.read_text());STEP=DOC['jobs']['transport']['steps'][-1]
CODE=textwrap.dedent(re.search(r"<<'PY'\n(.*?)\nPY\n",STEP['run'],re.S).group(1))
class Tests(unittest.TestCase):
 def run_case(self,mode):
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d);(p/'bin').mkdir();state=p/'state.json'
   script='''#!/usr/bin/python3
import json,pathlib,sys,time,os
root=pathlib.Path(ROOT);mode=MODE;target=root/'state.json';state=json.loads(target.read_text())if target.exists()else{'held':False,'commands':[]}
assert 'SSH_PRIVATE_KEY'not in os.environ and 'SSH_KNOWN_HOSTS'not in os.environ
command=sys.argv[-1];body=json.load(sys.stdin);state['commands'].append(command)
def out(value,code=0):target.write_text(json.dumps(state));print(json.dumps(value));raise SystemExit(code)
if command=='writer-status':
 out({'schema':2,'repository_id':'4daea08c03744d89ff9954c22b337c38beea7a2cc7c517d50e7370776fc13a11','publication_producers_enrolled':True,'source_review_integrity':True,'local_inventory_complete':True,'active_known_writer_units':['synthetic']if mode=='busy'else[],'active_known_repository_clients':0,'unknown_repository_clients':0,'unknown_writer_units':[],'next_known_writer_start_epoch':time.time()+(60 if mode=='near-timer'else 1000),'writer_policy_sha256':'b'*64})
if command=='publication-acquire':
 if state['held']:
  if mode=='second-accepted':out({'acquired':True})
  out({'ok':False,'failure_type':'ValueError'},1)
 assert body['maximum_seconds']==60 and body['producer_policy_sha256']=='b'*64
 state.update(held=True,owner=body['owner_nonce'])
 if mode=='acquire-response-lost':target.write_text(json.dumps(state));raise SystemExit(255)
 out({'acquired':True,'created_epoch':time.time(),'expires_epoch':time.time()+60,'application_writers_blocked':False})
if command=='publication-release':
 assert state['held']and body['owner_nonce']==state['owner']
 if mode=='release-response-lost':target.write_text(json.dumps(state));raise SystemExit(255)
 state['held']=False;out({'released':True})
raise AssertionError('Unexpected command; no native action permitted')
'''.replace('ROOT',repr(str(p))).replace('MODE',repr(mode))
   ssh=p/'bin/ssh';ssh.write_text(script);ssh.chmod(0o755)
   self.assertEqual(CODE.count('time.sleep(8)'),1)
   (p/'controller.py').write_text(CODE.replace('time.sleep(8)','time.sleep(0)'))
   env={'PATH':str(p/'bin')+':/usr/bin:/bin','HOME':str(p),'RUNNER_TEMP':str(p),'SSH_PRIVATE_KEY':'SYNTHETIC-NOT-A-KEY','SSH_KNOWN_HOSTS':'SYNTHETIC-NOT-A-HOSTPIN'}
   r=subprocess.run([sys.executable,str(p/'controller.py')],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
   value=json.loads(r.stdout);saved=json.loads(state.read_text());return r.returncode,value,saved
 def test_normal_exact_response_fields_and_finally_release(self):
  code,value,state=self.run_case('normal');self.assertEqual(code,0);self.assertFalse(state['held']);self.assertTrue(value['HOLD_released']);self.assertFalse(value['B2_mutations']);self.assertEqual(state['commands'],['writer-status','publication-acquire','publication-acquire','publication-release'])
 def test_busy_refuses_before_hold(self):
  code,value,state=self.run_case('busy');self.assertNotEqual(code,0);self.assertFalse(state['held']);self.assertEqual(state['commands'],['writer-status']);self.assertFalse(value['HOLD_may_remain'])
 def test_close_timer_refuses_before_hold(self):
  code,value,state=self.run_case('near-timer');self.assertNotEqual(code,0);self.assertFalse(state['held']);self.assertEqual(state['commands'],['writer-status'])
 def test_acquire_uncertain_still_releases_exact_known_owner(self):
  code,value,state=self.run_case('acquire-response-lost');self.assertNotEqual(code,0);self.assertFalse(state['held']);self.assertEqual(state['commands'],['writer-status','publication-acquire','publication-release']);self.assertFalse(value['HOLD_may_remain'])
 def test_invalid_second_owner_success_fails_and_releases(self):
  code,value,state=self.run_case('second-accepted');self.assertNotEqual(code,0);self.assertFalse(state['held'])
 def test_unknown_release_keeps_manual_reconcile_boundary(self):
  code,value,state=self.run_case('release-response-lost');self.assertNotEqual(code,0);self.assertTrue(state['held']);self.assertTrue(value['manual_reconciliation_required']);self.assertFalse(value['native_action_started'])
 def test_same_free_guards_only_explicit_default_false_input_step(self):
  old=yaml.safe_load((HERE/'maintenance-transport-schema2.publication.yml').read_text());new=copy.deepcopy(DOC);event='on'if'on'in new else True
  spec=new[event]['workflow_dispatch']['inputs'];self.assertEqual(set(spec),{'publication_hold_test'});self.assertEqual(spec['publication_hold_test']['type'],'boolean');self.assertIs(spec['publication_hold_test']['default'],False)
  new[event]['workflow_dispatch']=None;added=new['jobs']['transport']['steps'].pop();self.assertEqual(new,old);self.assertEqual(added['if'],'${{ inputs.publication_hold_test == true }}')
  self.assertNotIn('publication-begin-forget',CODE);self.assertNotIn('restic',CODE);self.assertNotIn('systemctl',CODE)
if __name__=='__main__':unittest.main()
