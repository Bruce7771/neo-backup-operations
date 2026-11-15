"""Actual generated sibling imports through the actual launcher; zero cloud I/O."""
import contextlib,importlib.util,io,json,os,pathlib,sys,tempfile,types,unittest
from unittest.mock import patch
H=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('parent_import_launcher',H/'run-publication-retention.candidate.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def exercise(self,fail=False):
  original=m.load;before=list(sys.path);observed=[]
  def postprocess(engine,args):
   self.assertEqual(sys.path[0],str(engine));wiring=original('actual_import_wiring',H/'publication-existing-coordinator.proposed.py')
   planner=wiring.load('actual_parent_planner',engine/'retention-plan.py')
   self.assertTrue(callable(planner.build));self.assertEqual(pathlib.Path(sys.modules['reviewed_control_artifacts'].__file__).parent,engine)
   self.assertEqual(pathlib.Path(sys.modules['reviewed_composed_control'].__file__).parent,engine)
   fixed=wiring.load('actual_parent_asof',engine/'asof_recovery_hold.py');self.assertTrue(callable(fixed.fixed_hold));observed.append(True)
   if fail:raise ValueError('SYNTHETIC-POSTPROCESS-FAILURE')
   return {'result':'LOCAL-import-only-NOT-a-cloud-PLAN'}
  def loader(name,path):return types.SimpleNamespace(main=postprocess)if name=='publication_candidate_coordinator'else original(name,path)
  saved={k:v for k,v in sys.modules.items()if k in('reviewed_control_artifacts','reviewed_composed_control')}
  for k in saved:del sys.modules[k]
  try:
   with tempfile.TemporaryDirectory()as td,patch.dict(os.environ,{'RUNNER_TEMP':td}),patch.object(m,'load',side_effect=loader),contextlib.redirect_stdout(io.StringIO()):
    if fail:
     with self.assertRaisesRegex(ValueError,'SYNTHETIC-POSTPROCESS-FAILURE'):m.main()
    else:m.main()
   self.assertEqual(sys.path,before);self.assertEqual(observed,[True])
  finally:
   for k in('reviewed_control_artifacts','reviewed_composed_control'):sys.modules.pop(k,None)
   sys.modules.update(saved)
 def test_actual_parent_planner_and_siblings_load(self):self.exercise()
 def test_import_context_restored_on_postprocess_failure(self):self.exercise(True)
if __name__=='__main__':unittest.main()
