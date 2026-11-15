"""Offline exact startup handoff and root-only fixture command regression."""
import ast,os,pathlib,subprocess,sys,tempfile,time,unittest
H=pathlib.Path(__file__).parent
class Handoff(unittest.TestCase):
 def test_audit_child_receives_dynamic_budget_and_required_metadata(self):
  tree=ast.parse((H/'publication-retention-coordinator.candidate.py').read_text())
  main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  scope=next(n for n in main.body if isinstance(n,ast.With))
  start=next(i for i,n in enumerate(scope.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='audit' for t in n.targets))
  stop=next(i for i,n in enumerate(scope.body[start:],start) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='bounded')
  with tempfile.TemporaryDirectory() as d:
   required=('NEO_POLICY_JSON','NEO_PROTECTED_JSON','NEO_RESTORED_JSON','NEO_DEPENDENCIES_JSON','NEO_HOURLY_RECOVERY_JSON')
   env={k:'{}' for k in required};env['NEO_RESTIC_PASSWORD']='SYNTHETIC'
   ns=dict(native={'PATH':os.environ['PATH']},env=env,work=pathlib.Path(d),time=time)
   before=time.monotonic();exec(compile(ast.Module(body=scope.body[start:stop],type_ignores=[]),'actual-child-handoff','exec'),ns)
   self.assertLessEqual(before,float(ns['audit']['NEO_STAGED_JOB_START']));self.assertLessEqual(float(ns['audit']['NEO_STAGED_JOB_START']),time.monotonic())
   for key in required:self.assertEqual(ns['audit'][key],env[key])
   child="import os,time;start=float(os.environ['NEO_STAGED_JOB_START']);assert 0<=time.monotonic()-start<10;assert 'NEO_MAINTENANCE_SSH_KEY' not in os.environ"
   subprocess.run([sys.executable,'-c',child],env=ns['audit'],check=True,timeout=5)
 def test_only_root_fixture_uses_sudo(self):
  s=(H.parent/'.github/workflows/retention-manual.yml').read_text()
  self.assertEqual(s.count('sudo -n'),1)
  self.assertIn('sudo -n /usr/bin/python3 -B proposals/publication-native-endtoend-test.py --restic-executable "$(command -v restic)"',s)
  self.assertIn('python3 -B proposals/run-publication-retention.candidate.py --mode "$REQUEST_MODE"',s)
if __name__=='__main__':unittest.main()