"""Actual generated maintenance engine only; two inventory reads get 90 seconds."""
import ast,importlib.util,pathlib,subprocess,tempfile,types,unittest
from unittest.mock import patch
H=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('inventory_limit_launcher',H/'run-publication-retention.candidate.py');launcher=importlib.util.module_from_spec(s);s.loader.exec_module(launcher)
class Tests(unittest.TestCase):
 def test_exact_two_inventory_calls_and_other_limits_unchanged(self):
  original=(H.parent/'scripts/retention-audit.py').read_bytes()
  with tempfile.TemporaryDirectory()as td:
   engine=launcher.build_engine(H,pathlib.Path(td)/'engine');source=(engine/'retention-audit.py').read_text();self.assertEqual(source.count("run(['restic','--no-lock','snapshots','--json'],env,90)"),2)
   tree=ast.parse(source);run=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run');self.assertEqual(run.args.defaults[0].value,45)
   new90=[n for n in ast.walk(tree)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='run'and len(n.args)==3 and isinstance(n.args[2],ast.Constant)and n.args[2].value==90];self.assertEqual(len(new90),2)
   self.assertEqual(source.count("['restic','--no-lock','forget','--dry-run'"),1)
   budget=(engine/'staged_derive.py').read_text();self.assertIn('self.now()+120',budget);self.assertIn('self.job_end=self.start+4500',budget);self.assertIn('spawned+35',(engine/'native_parallel_transport.py').read_text())
   self.assertEqual((H.parent/'scripts/retention-audit.py').read_bytes(),original)
 def test_actual_run_phase_budget_still_clamps_requested90(self):
  with tempfile.TemporaryDirectory()as td:
   engine=launcher.build_engine(H,pathlib.Path(td)/'engine');tree=ast.parse((engine/'retention-audit.py').read_text());run=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run');spec=importlib.util.spec_from_file_location('actual_inventory_budget',engine/'staged_derive.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
   for phase,now,expected in [('inventory',0,90),('inventory',3590,10),('final-inventory',3620,10)]:
    b=m.Budget(start=0,now=lambda:now);ns={'BUDGET':b,'SAFE_DIAGNOSTIC':{'phase':phase},'subprocess':subprocess,'Path':pathlib.Path,'external_command':lambda a,e:a};exec(compile(ast.Module(body=[run],type_ignores=[]),'actual-generated-run','exec'),ns)
    seen=[]
    with patch.object(subprocess,'run',side_effect=lambda*a,**kw:seen.append(kw['timeout'])or types.SimpleNamespace(stdout='SYNTHETIC')):self.assertEqual(ns['run'](['restic','--no-lock','snapshots','--json'],{},90),'SYNTHETIC')
    self.assertEqual(seen,[expected])
if __name__=='__main__':unittest.main()