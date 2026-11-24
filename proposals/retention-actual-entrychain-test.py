"""Resolve actual workflow run commands, not historical publication copies."""
import ast,hashlib,importlib.util,pathlib,py_compile,tempfile,unittest
import yaml
ROOT=pathlib.Path(__file__).resolve().parents[1];P=ROOT/'proposals'
FAMILY='build-unverified-base-family-retention-engine.proposed.py'
class Tests(unittest.TestCase):
 def workflow(self,name):return yaml.safe_load((ROOT/'.github/workflows'/name).read_text())
 def selector(self,path):
  tree=ast.parse((ROOT/path).read_text());found=[]
  for n in ast.walk(tree):
   if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='builder'for t in n.targets):
    value=n.value;self.assertIsInstance(value,ast.Call);self.assertEqual(value.func.id,'load');self.assertIsInstance(value.args[1],ast.BinOp);found.append(value.args[1].right.value)
  self.assertEqual(found,[FAMILY])
 def test_actual_manual_native_step_resolves_family(self):
  w=self.workflow('retention-readonly-check.yml');steps=w['jobs']['readonly-maintenance']['steps'];step=next(s for s in steps if s.get('name')=='One explicit serialized readonly native-catalog trial')
  self.assertEqual(step['run'],'python3 proposals/run-native-external-trial.proposed.py');self.assertIn('inputs.native_trial && !inputs.native_dump_diagnostic',step['if']);self.selector(step['run'].split()[1])
 def test_actual_weekly_step_resolves_family(self):
  w=self.workflow('retention-audit.yml');runs=[s['run']for s in w['jobs']['audit']['steps']if s.get('run','').startswith('python3 proposals/run-scheduled-retention-audit.proposed.py')]
  self.assertEqual(runs,['python3 proposals/run-scheduled-retention-audit.proposed.py']);self.selector(runs[0].split()[1])
 def test_default_and_diagnostic_paths_stay_distinct(self):
  w=self.workflow('retention-readonly-check.yml');steps=w['jobs']['readonly-maintenance']['steps']
  default=next(s for s in steps if s.get('name')=='Read-only plan, integrity and limited restore without backup pause');self.assertIn('!inputs.native_trial && !inputs.native_dump_diagnostic',default['if']);self.assertIn('scripts/retention-readonly-check.py',default['run'])
  diag=next(s for s in steps if s.get('name')=='One reviewed cold PITR manifest diagnostic only');self.assertIn('inputs.native_dump_diagnostic',diag['if']);self.assertIn('run-native-dump-diagnostic.proposed.py',diag['run'])
 def test_reviewed_workflow_bytes_and_deadlines_unchanged(self):
  for name,want in [('retention-readonly-check.yml','e1f27020e3f3bba20d71d75ffcfc8c8c01327f592ca74a0cacde301bbd7f593e'),('retention-audit.yml','063b2405c4e565d957569a2f8a0153e220ae38e7d5e861cc20969729f8d81f2c')]:
   self.assertEqual(hashlib.sha256((ROOT/'.github/workflows'/name).read_bytes()).hexdigest(),want)
 def test_selected_builder_generates_quarantine_and_compiles(self):
  spec=importlib.util.spec_from_file_location('actual_family_builder',P/FAMILY);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  with tempfile.TemporaryDirectory()as td:
   out=m.build(ROOT/'scripts',pathlib.Path(td)/'engine');self.assertIn('protected-unverified-base-family',(out/'retention-plan.py').read_text());self.assertIn('protected-unverified-base-family',(out/'hourly_selfcontained_v3.py').read_text())
   for f in out.glob('*.py'):py_compile.compile(str(f),doraise=True)
 def test_weekly_cold_inventory_deadline_preserves_job_budgets(self):
  path=P/'run-scheduled-retention-audit.proposed.py'
  spec=importlib.util.spec_from_file_location('scheduled_audit',path);launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
  builder=launcher.load('family_builder',P/FAMILY)
  with tempfile.TemporaryDirectory()as td:
   engine=builder.build(ROOT/'scripts',pathlib.Path(td)/'engine')
   audit=engine/'retention-audit.py';checker=engine/'retention-readonly-check.py'
   before=audit.read_text();checker_before=checker.read_bytes()
   anchor="inventory=run(['restic','snapshots','--json'],env)"
   self.assertEqual(before.count(anchor),1)
   launcher.configure_cold_inventory_deadline(engine)
   self.assertEqual(audit.read_text(),before.replace(anchor,anchor[:-1]+',timeout=240)'))
   self.assertEqual(checker.read_bytes(),checker_before)
 def test_only_scheduled_inventory_uses_extra_connections(self):
  path=P/'external-reader-contract.proposed.py'
  spec=importlib.util.spec_from_file_location('reader_contract',path);contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
  for workflow,mode,job,event in [('retention-audit.yml',contract.SCHEDULED_MODE,'audit','schedule'),('retention-readonly-check.yml',contract.MODE,'readonly-maintenance','workflow_dispatch')]:
   env=dict(NEO_EXTERNAL_READER_MODE=mode,GITHUB_ACTIONS='true',GITHUB_REPOSITORY='Bruce7771/neo-backup-operations',GITHUB_REF='refs/heads/main',GITHUB_EVENT_NAME=event,GITHUB_JOB=job,GITHUB_WORKFLOW_REF='Bruce7771/neo-backup-operations/.github/workflows/'+workflow+'@refs/heads/main',GITHUB_SHA='a'*40,NEO_REVIEWED_TRIAL_COMMIT='a'*40,GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',GITHUB_WORKSPACE=str(ROOT))
   expected=['restic','--no-lock']+(['-o','s3.connections=12']if mode==contract.SCHEDULED_MODE else[])+['snapshots','--json']
   self.assertEqual(contract.command(['restic','snapshots','--json'],env),expected)
   self.assertEqual(contract.command(['restic','forget','--dry-run','--json'],env),['restic','--no-lock','forget','--dry-run','--json'])
   with self.assertRaises(ValueError):contract.command(['restic','forget','--prune'],env)
if __name__=='__main__':unittest.main()
