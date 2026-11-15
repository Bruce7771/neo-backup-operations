#!/usr/bin/env python3
"""Publication guards; no credentials, subprocesses or network calls."""
import hashlib,importlib.util,re,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).parent

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

class Tests(unittest.TestCase):
 def test_workflow_exact_pin(self):
  workflow=HERE/'retention-readonly-check.long-bounded.publication.yml';contract=load('long_contract',HERE/'external-reader-contract.long-bounded.publication.py')
  self.assertEqual(hashlib.sha256(workflow.read_bytes()).hexdigest(),contract.WORKFLOW_SHA256)
 def test_workflow_guards_unchanged(self):
  s=(HERE/'retention-readonly-check.long-bounded.publication.yml').read_text()
  for line in ('timeout-minutes: 80','contents: read','group: backup-repository-maintenance','cancel-in-progress: false','environment: NEO_BACKUP_MAINTENANCE','runs-on: ubuntu-24.04','default: false','native_trial && !inputs.native_dump_diagnostic'):
   self.assertIn(line,s)
  for forbidden in ('contents: write','id-token: write','schedule:','NEO_B2_MAINTENANCE_KEY','--prune'):
   self.assertNotIn(forbidden,s)
 def test_launcher_exact_new_limits(self):
  s=(HERE/'run-long-bounded-external-trial.publication.py').read_text();self.assertIn("here/'build-long-bounded-retention-engine.proposed.py'",s);self.assertIn('check=True,timeout=4500)',s);self.assertNotIn('timeout=540)',s)
 def test_source_compiles(self):
  for name in ('run-long-bounded-external-trial.publication.py','external-reader-contract.long-bounded.publication.py'):
   compile((HERE/name).read_text(),name,'exec')
 def test_generated_contract_copy_exact(self):
  # Publication replaces the existing contract path. Build only inside own
  # temporary source copy to verify upstream builders copy the reviewed pin.
  import shutil
  with tempfile.TemporaryDirectory()as t:
   root=Path(t);shutil.copytree(HERE,root/'proposals');shutil.copytree(HERE.parent/'scripts',root/'scripts')
   shutil.copyfile(root/'proposals/external-reader-contract.long-bounded.publication.py',root/'proposals/external-reader-contract.proposed.py')
   out=load('packet_builder',root/'proposals/build-long-bounded-retention-engine.proposed.py').build(root/'scripts',root/'generated')
   self.assertEqual((out/'external_reader_contract.py').read_bytes(),(root/'proposals/external-reader-contract.long-bounded.publication.py').read_bytes())
if __name__=='__main__':unittest.main()
