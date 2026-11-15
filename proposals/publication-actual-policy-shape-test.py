"""Whole coordinator control-flow with exact deployed seven-field policy SHAPE.
All external operations are injected offline; never credentials or B2 mutation.
"""
import hashlib,importlib.util,json,os,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch
H=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('candidate_actualshape',H/'publication-retention-coordinator.candidate.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
class WholeCoordinator(unittest.TestCase):
 def exercise(self,mode,remove,enabled):
  with tempfile.TemporaryDirectory()as tmp:
   root=pathlib.Path(tmp);wf=root/'.github/workflows/retention-manual.yml';wf.parent.mkdir(parents=True);wf.write_text('group: backup-repository-maintenance\ncancel-in-progress: false\nenvironment: NEO_BACKUP_MAINTENANCE\n')
   policy=dict(configuration_scopes=[],schema=1,scopes=[dict(host=k,tag=k,paths=['/'+k],kind=k)for k in ('daily','hourly','pitr')],maintenance_postcheck={},protected_unknown_hourly=[],unknown_recovery_hold_mode='reviewed-as-of-immutable-root-set',as_of_unknown_hold={})
   static=dict(protected=[],restored=[],dependencies=[],hourly_overrides=[]);candidate=dict(remove_snapshot_ids=['a'*64]if remove else[],protected_snapshot_ids=[],retained_snapshot_ids=[],inventory_stable_for_admission=True)
   approval=dict(schema=1,reviewed=True,executor_sha='b'*40,policy_sha256=c.sha(policy),static_sha256=c.sha(static),workflow_sha256=hashlib.sha256(wf.read_bytes()).hexdigest(),producer_policy_sha256='c'*64,maximum_removals=10)
   env=dict(PATH='/usr/bin:/bin',RUNNER_TEMP=str(root),HOME=tmp,GITHUB_ACTIONS='true',GITHUB_REPOSITORY='Bruce7771/neo-backup-operations',GITHUB_REF='refs/heads/main',GITHUB_JOB='manual',GITHUB_WORKFLOW_REF='Bruce7771/neo-backup-operations/.github/workflows/retention-manual.yml@refs/heads/main',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_SHA='b'*40,GITHUB_RUN_ID='123',GITHUB_WORKSPACE=tmp,NEO_RETENTION_APPLY_CONTRACT_JSON=json.dumps(approval),NEO_POLICY_JSON=json.dumps(policy),NEO_PROTECTED_JSON='[]',NEO_RESTORED_JSON='[]',NEO_DEPENDENCIES_JSON='[]',NEO_HOURLY_RECOVERY_JSON='[]',NEO_GITHUB_READ_TOKEN='SYNTHETIC',NEO_RESTIC_PASSWORD='SYNTHETIC',AWS_ACCESS_KEY_ID='SYNTHETIC',AWS_SECRET_ACCESS_KEY='SYNTHETIC',RESTIC_REPOSITORY='s3:https://synthetic.invalid/bucket/restic',NEO_MAINTENANCE_SSH_KEY='SYNTHETIC',NEO_MAINTENANCE_SSH_KNOWN_HOSTS='SYNTHETIC',NEO_BACKUP_APPLY_ENABLED='true'if enabled else'false')
   events=[]
   def fetch(url):
    events.append('githubGET')
    return dict(total_count=1,branch_policies=[dict(name='main',type='branch')])if '/deployment-branch-policies?'in url else dict(name='NEO_BACKUP_MAINTENANCE',can_admins_bypass=False,deployment_branch_policy=dict(custom_branch_policies=True))
   def bounded(argv,e,timeout):
    self.assertNotIn('NEO_GITHUB_READ_TOKEN',e);self.assertNotIn('GITHUB_TOKEN',e)
    if argv[0]=='git':return ('b'*40+'\n').encode()if 'rev-parse'in argv else b''
    if argv[0]=='restic':
     events.append('native:'+argv[1]);return b'restic 0.16.4 synthetic'if argv[1]=='version'else b'{"id":"d"}'if argv[1:]==['cat','config']else b''
    self.assertIn('NEO_STAGED_JOB_START',e);pathlib.Path(e['NEO_RETENTION_VALIDATION_BUNDLE_OUTPUT']).write_text('{}');return b''
   class RPC:
    hold_started=None
    def __init__(self,argv,*args):self.assert_target=argv[-1];events.append('target:'+argv[-1])
    def status(self):return dict(schema=2,repository_id='d',writer_policy_sha256='c'*64,local_inventory_complete=True,source_review_integrity=True,publication_producers_enrolled=True,unknown_writer_units=[],unknown_repository_clients=0)
   def coordinate(bundle,engine,native,work,call,p,st,rpc,*args):
    admission=args[-2];postcheck=args[-1];admission();events.append('coordinate');return dict(result='synthetic-coordinated',deleted_snapshots=0,**postcheck(candidate))
   def observe(repos,repo,run,fetch):self.assertEqual(repos,['Bruce7771/neo-backup-operations']);fetch('https://synthetic-not-network');return dict(complete=True,other_running_jobs=0)
   wiring=types.SimpleNamespace(ExistingSSH=RPC,load=lambda n,p:types.SimpleNamespace(fixed_hold=lambda*a:None),revalidate=lambda*a:candidate,coordinate=coordinate)
   modules={'candidate_external_observer':types.SimpleNamespace(observe=observe),'candidate_github_read':types.SimpleNamespace(GitHubRead=lambda token,repos:fetch),'candidate_bounded':types.SimpleNamespace(bounded=bounded),'candidate_access':types.SimpleNamespace(MAINTENANCE='synthetic',repository_target=lambda r:('bucket','endpoint','prefix'),authorize_pair=lambda*a:None),'candidate_wiring':wiring,'candidate_review':types.SimpleNamespace(removal_review_digest=lambda*a:'e'*64),'candidate_postcheck':types.SimpleNamespace(validate=lambda*a:None,restore=lambda*a:dict(component_restore_verified=True))}
   with patch.dict(os.environ,env,clear=True),patch.object(c,'load',side_effect=lambda n,p:modules[n]),patch.object(c,'run_audit_child',side_effect=lambda engine,audit,timeout:bounded([sys.executable,str(engine/'retention-audit.py')],audit,timeout)):result=c.main(root,['--mode',mode])
   return result,events
 def test_PLAN_zero_and_nonzero_under_actual_seven_field_policy(self):
  for remove in (False,True):
   r,e=self.exercise('plan',remove,False);self.assertEqual(r['result'],'plan-only');self.assertEqual(r['removal_candidates'],int(remove));self.assertNotIn('coordinate',e)
 def test_nonzero_disabled_refuses_without_ssh(self):
  with self.assertRaisesRegex(ValueError,'Apply remains disabled'):self.exercise('policy-apply',True,False)
 def test_nonzero_enabled_reaches_reviewed_target_and_both_external_checks(self):
  r,e=self.exercise('policy-apply',True,True);self.assertIn('target:root@2.24.129.173',e);self.assertIn('coordinate',e);self.assertEqual(e.count('githubGET'),5);self.assertEqual(r['deleted_snapshots'],0)
if __name__=='__main__':unittest.main()