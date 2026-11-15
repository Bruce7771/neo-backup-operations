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
if __name__=='__main__':unittest.main()
