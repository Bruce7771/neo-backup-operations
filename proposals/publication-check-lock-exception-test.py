"""Execute actual nested native-call admission; no native or remote calls."""
import ast,importlib.util,pathlib,unittest
H=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('check_native',H/'publication-retention-coordinator.candidate.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
class Tests(unittest.TestCase):
 def test_actual_exact_call_whitelist(self):
  tree=ast.parse((H/'publication-retention-coordinator.candidate.py').read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main');fn=next(n for n in ast.walk(main)if isinstance(n,ast.FunctionDef)and n.name=='call');calls=[]
  ns=dict(require=c.require,bounded=lambda argv,env,timeout:calls.append(argv),native={});exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual-native-call','exec'),ns)
  ns['call'](['--no-lock','check'],150)
  for args in [['cat','config'],['snapshots','--json'],['dump','SYNTHETIC','/synthetic'],['restore','SYNTHETIC','--target','/synthetic'],['forget','SYNTHETIC']]:ns['call'](args)
  for args in [['--no-lock','forget','SYNTHETIC'],['--no-lock','forget','--dry-run'],['--no-lock','check','--read-data'],['check','--no-lock'],['--no-lock','dump','SYNTHETIC','/synthetic']]:
   with self.assertRaises(ValueError):ns['call'](args)
  self.assertEqual(len(calls),6)
if __name__=='__main__':unittest.main()