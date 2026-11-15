#!/usr/bin/env python3
"""Exact weekly audit context and unchanged manual/local safety, no network."""
import importlib.util,hashlib,tempfile,pathlib,unittest,shutil
HERE=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('scheduled_contract',HERE/'external-reader-contract.scheduled-audit.publication.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);d=self.root/'.github/workflows';d.mkdir(parents=True);shutil.copyfile(HERE/'retention-audit.scheduled-native.publication.yml',d/'retention-audit.yml');shutil.copyfile(HERE.parent/'.github/workflows/retention-readonly-check.yml',d/'retention-readonly-check.yml')
 def tearDown(self):self.tmp.cleanup()
 def env(self,scheduled=True):
  workflow='retention-audit.yml'if scheduled else'retention-readonly-check.yml'
  return dict(NEO_EXTERNAL_READER_MODE=m.SCHEDULED_MODE if scheduled else m.MODE,GITHUB_ACTIONS='true',GITHUB_REPOSITORY='Bruce7771/neo-backup-operations',GITHUB_REF='refs/heads/main',GITHUB_EVENT_NAME='schedule'if scheduled else'workflow_dispatch',GITHUB_JOB='audit'if scheduled else'readonly-maintenance',GITHUB_WORKFLOW_REF='Bruce7771/neo-backup-operations/.github/workflows/'+workflow+'@refs/heads/main',GITHUB_SHA='a'*40,NEO_REVIEWED_TRIAL_COMMIT='a'*40,GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',GITHUB_WORKSPACE=str(self.root))
 def test_actual_exact_schedule_context(self):self.assertEqual(m.verify(self.env())['execution'],'actual-scheduled-main-GHA-job')
 def test_manual_audit_context(self):
  e=self.env();e['GITHUB_EVENT_NAME']='workflow_dispatch';self.assertEqual(m.verify(e)['execution'],'actual-manual-main-GHA-job')
 def test_original_manual_context_preserved(self):self.assertEqual(m.verify(self.env(False))['workflow_sha256'],m.WORKFLOW_SHA256)
 def test_manual_trial_schedule_not_allowed(self):
  e=self.env(False);e['GITHUB_EVENT_NAME']='schedule'
  with self.assertRaises(ValueError):m.verify(e)
 def test_wrong_event_job_branch_sha_refused(self):
  for k,v in [('GITHUB_EVENT_NAME','push'),('GITHUB_JOB','other'),('GITHUB_REF','refs/heads/other'),('NEO_REVIEWED_TRIAL_COMMIT','b'*40),('GITHUB_WORKFLOW_REF','foreign/repo/other')]:
   e=self.env();e[k]=v
   with self.assertRaises(ValueError):m.verify(e)
 def test_changed_workflow_denied(self):
  p=self.root/'.github/workflows/retention-audit.yml';p.write_bytes(p.read_bytes()+b'\n# changed')
  with self.assertRaises(ValueError):m.verify(self.env())
 def test_no_mutation_admitted(self):
  for args in(['restic','prune'],['restic','forget','a'*64],['restic','forget','--dry-run','--json','--prune'],['restic','backup','x']):
   with self.assertRaises(ValueError):m.command(args,self.env())
  self.assertEqual(m.command(['restic','cat','config'],{}),['restic','cat','config'])
 def test_exact_workflow_existing_cron_free_group_readonly_no_new_creds(self):
  text=(HERE/'retention-audit.scheduled-native.publication.yml').read_text();self.assertIn("cron: '11 4 * * 1'",text);self.assertIn('timeout-minutes: 80',text);self.assertIn('contents: read',text);self.assertIn('group: backup-repository-maintenance',text);self.assertIn('cancel-in-progress: false',text);self.assertIn('environment: NEO_BACKUP_MAINTENANCE',text);self.assertIn('runs-on: ubuntu-24.04',text);self.assertNotIn('secrets.NEO_B2_MAINTENANCE',text);self.assertNotIn('--prune',text)
if __name__=='__main__':unittest.main()
