"""Actual subprocess + existing generated safe JSON parser, no credentials/network."""
import contextlib,importlib.util,io,json,os,pathlib,tempfile,unittest
H=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('audit_child_coordinator',H/'publication-retention-coordinator.candidate.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
s=importlib.util.spec_from_file_location('audit_child_engine',H/'run-publication-retention.candidate.py');launcher=importlib.util.module_from_spec(s);s.loader.exec_module(launcher)
class Tests(unittest.TestCase):
 def test_actual_generated_diagnostic_json_preserved_raw_secrets_removed(self):
  with tempfile.TemporaryDirectory()as td:
   engine=launcher.build_engine(H,pathlib.Path(td)/'engine')
   failure=dict(failure_type='ValueError',phase='validate-candidate',source_module='retention-audit.py',source_line=155,metadata_stats={'native_batches':3},nested_failure_code='CONFIG_DEPENDENCY_COVERAGE_MISMATCH',nested_source_module='retention-plan.py',nested_source_line=155)
   secret='SYNTHETIC-PRIVATE-RESPONSE-BODY'
   (engine/'retention-audit.py').write_text('import sys\nprint('+repr(secret)+',file=sys.stderr)\nprint('+repr('NEO_RETENTION_SAFE_FAILURE '+json.dumps(failure))+',file=sys.stderr)\nraise SystemExit(1)\n')
   captured=io.StringIO()
   with contextlib.redirect_stderr(captured),self.assertRaisesRegex(ValueError,'audit-child-failed-inspect-safe-diagnostic'):c.run_audit_child(engine,{'PATH':os.environ['PATH']},5)
   self.assertEqual(json.loads(captured.getvalue()),{'audit_safe_failure':failure});self.assertNotIn(secret,captured.getvalue())
 def test_unreviewed_diagnostic_fields_and_raw_child_errors_not_forwarded(self):
  with tempfile.TemporaryDirectory()as td:
   engine=launcher.build_engine(H,pathlib.Path(td)/'engine')
   (engine/'retention-audit.py').write_text('import sys\nprint(\'NEO_RETENTION_SAFE_FAILURE {"phase":"inventory","secret":"SYNTHETIC"}\',file=sys.stderr)\nraise SystemExit(1)\n')
   captured=io.StringIO()
   with contextlib.redirect_stderr(captured),self.assertRaises(ValueError):c.run_audit_child(engine,{'PATH':os.environ['PATH']},5)
   self.assertEqual(captured.getvalue(),'')
 def test_timeout_reaps_own_child(self):
  with tempfile.TemporaryDirectory()as td:
   engine=launcher.build_engine(H,pathlib.Path(td)/'engine');(engine/'retention-audit.py').write_text('import time\ntime.sleep(30)\n')
   with self.assertRaisesRegex(ValueError,'audit-child-timeout-no-blind-unlock'):c.run_audit_child(engine,{'PATH':os.environ['PATH']},.05)
if __name__=='__main__':unittest.main()