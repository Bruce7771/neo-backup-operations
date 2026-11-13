#!/usr/bin/env python3
"""Synthetic actual-workflow contract tests; never a GitHub/cloud call."""
import hashlib,importlib.util,os,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).parent;ROOT=HERE.parent

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('external_contract',HERE/'external-reader-contract.proposed.py')
class Contract(unittest.TestCase):
 def fixture(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.workflow=self.root/'.github/workflows/retention-readonly-check.yml';self.workflow.parent.mkdir(parents=True);self.workflow.write_bytes((HERE/'retention-readonly-native-trial.proposed.yml').read_bytes())
  return {'NEO_EXTERNAL_READER_MODE':m.MODE,'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'Bruce7771/neo-backup-operations','GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_JOB':'readonly-maintenance','GITHUB_WORKFLOW_REF':'Bruce7771/neo-backup-operations/.github/workflows/retention-readonly-check.yml@refs/heads/main','GITHUB_SHA':'a'*40,'NEO_REVIEWED_TRIAL_COMMIT':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKSPACE':str(self.root)}
 def test_exact_workflow_contract_guard(self):
  p=m.verify(self.fixture());self.assertEqual(p['credential_class'],'audit-read-list-only');self.assertFalse(p['native_shared_lock_used'])
 def test_default_local_still_native_shared(self):self.assertEqual(m.command(['restic','cat','tree','synthetic'],{}),['restic','cat','tree','synthetic'])
 def test_external_reads_explicit_nolock(self):
  env=self.fixture();self.assertEqual(m.command(['restic','cat','tree','synthetic'],env),['restic','--no-lock','cat','tree','synthetic'])
 def test_wrong_context_ref_job_commit_refused(self):
  for key,value in [('GITHUB_REF','refs/heads/other'),('GITHUB_JOB','other'),('GITHUB_EVENT_NAME','schedule'),('GITHUB_REPOSITORY','other/repo'),('NEO_REVIEWED_TRIAL_COMMIT','b'*40)]:
   env=self.fixture();env[key]=value
   with self.assertRaises(ValueError):m.verify(env)
 def test_changed_workflow_group_hash_refused(self):
  env=self.fixture();self.workflow.write_bytes(self.workflow.read_bytes().replace(b'backup-repository-maintenance',b'changed-group'))
  with self.assertRaises(ValueError):m.verify(env)
 def test_mutation_verbs_and_non_dry_forget_refused(self):
  env=self.fixture()
  for args in [['restic','prune'],['restic','backup','x'],['restic','unlock'],['restic','forget','a'*64],['restic','forget','--dry-run','--json','--prune']]:
   with self.assertRaises(ValueError):m.command(args,env)
  self.assertIn('--dry-run',m.command(['restic','forget','--dry-run','--json'],env))
 def test_workflow_default_false_same_group_environment_audit3_only(self):
  source=(HERE/'retention-readonly-native-trial.proposed.yml').read_text();self.assertIn('default: false',source);self.assertIn('group: backup-repository-maintenance',source);self.assertIn('cancel-in-progress: false',source);self.assertIn('environment: NEO_BACKUP_MAINTENANCE',source);self.assertNotIn('secrets.NEO_B2_MAINTENANCE',source);self.assertNotIn('schedule:',source);self.assertIn('if: ${{ !inputs.native_trial }}',source)
 def test_generated_external_copy_actual_code_compile_and_extended_diagnostics(self):
  with tempfile.TemporaryDirectory()as d:
   b=load('external_builder',HERE/'build-native-external-engine.proposed.py');out=b.build(ROOT/'scripts',Path(d)/'engine')
   for n in ['retention-audit.py','hourly_metadata_batch.py','external_reader_contract.py','retention-readonly-check.py']:compile((out/n).read_text(),n,'exec')
   audit=(out/'retention-audit.py').read_text();self.assertIn("args=external_command(args,env)",audit);self.assertIn("external_command(['restic','dump',snapshot,path],env)",audit)
   batch=(out/'hourly_metadata_batch.py').read_text();self.assertIn('args=external_command(args,env)',batch)
   checker=(out/'retention-readonly-check.py').read_text();self.assertIn("'catalog_cli_processes'",checker)
if __name__=='__main__':unittest.main()
