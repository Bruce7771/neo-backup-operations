"""Synthetic strict response assertions; no SSH, key, service or B2 calls."""
import copy,json,pathlib,re,subprocess,sys,tempfile,textwrap,unittest
import yaml
HERE=pathlib.Path(__file__).parent
PROPOSED=HERE/'maintenance-transport-schema2.publication.yml'
ORIGINAL=HERE.parent/'.github/workflows/maintenance-transport-check.yml'
BODY=yaml.safe_load(PROPOSED.read_text())['jobs']['transport']['steps'][0]['run']
PYTHON=textwrap.dedent(re.search(r"<<'PY'\n(.*?)\nPY\n",BODY,re.S).group(1))
class Tests(unittest.TestCase):
 def fixture(self):return {'schema':2,'repository_id':'4daea08c03744d89ff9954c22b337c38beea7a2cc7c517d50e7370776fc13a11','publication_producers_enrolled':True,'source_review_integrity':True,'publication_hold_maximum_seconds':120,'service_or_schedule_changes':False,'environment_values_read':False,'credential_values_returned':False,'active_known_writer_units':['main-fixture.service'],'active_known_repository_clients':1}
 def run_assertion(self,state=None,denied=None,exit_code=1):
  with tempfile.TemporaryDirectory()as d:
   p=pathlib.Path(d);(p/'check.py').write_text(PYTHON);(p/'status.json').write_text(json.dumps(state if state is not None else self.fixture()));(p/'denied.json').write_text(json.dumps(denied if denied is not None else {'ok':False,'failure_type':'ValueError'}))
   return subprocess.run([sys.executable,str(p/'check.py'),str(p/'status.json'),str(p/'denied.json'),str(exit_code)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).returncode
 def test_exact_schema2_and_explicit_denial1_or2_accept_busy_readonly_status(self):
  for value in(1,2):self.assertEqual(self.run_assertion(exit_code=value),0)
 def test_wrong_repository_or_old_schema_refused(self):
  for key,val in [('repository_id','0'*64),('schema',1)]:
   state=self.fixture();state[key]=val
   with self.subTest(key=key):self.assertNotEqual(self.run_assertion(state),0)
  self.assertNotEqual(self.run_assertion({'fenced':False}),0)
 def test_source_enrollment_leak_or_control_flag_change_refused(self):
  for key,val in [('publication_producers_enrolled',False),('source_review_integrity',False),('environment_values_read',True),('credential_values_returned',True),('service_or_schedule_changes',True),('publication_hold_maximum_seconds',121),('lease','SYNTHETIC')]:
   state=self.fixture();state[key]=val
   with self.subTest(key=key):self.assertNotEqual(self.run_assertion(state),0)
 def test_network_error_or_general_command_success_not_access_denial(self):
  for value in(0,255,127):self.assertNotEqual(self.run_assertion(exit_code=value),0)
  for denied in [{'uid':0},{'ok':True},{'ok':False,'failure_type':'PermissionError'}]:self.assertNotEqual(self.run_assertion(denied=denied),0)
 def test_guards_secrets_permissions_runner_and_timeout_unchanged(self):
  old=yaml.safe_load(ORIGINAL.read_text());new=yaml.safe_load(PROPOSED.read_text())
  if len(old['jobs']['transport']['steps'])==2:
   self.assertEqual(old['jobs']['transport']['steps'][-1]['name'],'Explicit bounded publication HOLD and release only')
   event='on'if'on'in old else True;inputs=old[event]['workflow_dispatch']['inputs'];self.assertEqual(set(inputs),{'publication_hold_test'});self.assertIs(inputs['publication_hold_test']['default'],False)
   old[event]['workflow_dispatch']=None;old['jobs']['transport']['steps']=old['jobs']['transport']['steps'][:1]
  old['jobs']['transport']['steps'][0]['run']='REPLACED_ASSERTIONS';new['jobs']['transport']['steps'][0]['run']='REPLACED_ASSERTIONS';self.assertEqual(old,new)
 def test_no_mutation_verbs_and_bash_parses(self):
  self.assertNotIn('publication-acquire',BODY);self.assertNotIn('acquire 300',BODY);self.assertNotIn('restic ',BODY)
  r=subprocess.run(['bash','-n'],input=BODY.encode(),stderr=subprocess.PIPE);self.assertEqual(r.returncode,0)
if __name__=='__main__':unittest.main()
