"""Probe command/cleanup/redaction tests; no service credentials or B2."""
import importlib.util,json,os,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
H=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('probe_candidate',H/'publication-retention-coordinator.candidate.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
class Tests(unittest.TestCase):
 def exercise(self,source,timeout=5):
  with tempfile.TemporaryDirectory()as td:
   p=pathlib.Path(td)/'fixture.py';p.write_text(source);real=subprocess.Popen;commands=[]
   def spawn(command,**kw):
    commands.append(command);self.assertEqual(command,['/usr/bin/prlimit','--fsize=33554432:33554432','--','restic','--no-lock','snapshots','--json']);self.assertTrue(kw['start_new_session']);self.assertEqual(kw['stdin'],subprocess.DEVNULL)
    return real([sys.executable,str(p)],**kw)
   with patch.object(c.subprocess,'Popen',side_effect=spawn):r=c.inventory_probe({'PATH':os.environ['PATH']},pathlib.Path(td),timeout)
   self.assertEqual(len(commands),1);return r
 def test_only_counts_hash_bytes_no_rows_or_stderr(self):
  r=self.exercise('import json,sys\nprint(json.dumps([{"id":"'+'a'*64+'","paths":["SYNTHETIC-PRIVATE-PATH"]}]))\nprint("SYNTHETIC-PRIVATE-HEADER",file=sys.stderr)\n')
  self.assertEqual(r['snapshot_count'],1);self.assertEqual(r['exit_class'],'success');self.assertEqual(len(r['sha256']),64);self.assertNotIn('SYNTHETIC',json.dumps(r));self.assertEqual(set(r),{'result','elapsed_seconds','snapshot_count','bytes','sha256','exit_class'})
 def test_nonzero_no_raw_error(self):
  r=self.exercise('import sys\nprint("SYNTHETIC-SECRET",file=sys.stderr)\nraise SystemExit(2)\n');self.assertEqual(r['exit_class'],'native-exit-nonzero');self.assertIsNone(r['snapshot_count']);self.assertNotIn('SYNTHETIC',json.dumps(r))
 def test_invalid_json_never_forwarded(self):
  r=self.exercise('print("SYNTHETIC-PRIVATE-RESPONSE")\n');self.assertEqual(r['exit_class'],'invalid-bounded-json');self.assertIsNone(r['snapshot_count'])
 def test_timeout_owned_SIGINT_reaps(self):
  r=self.exercise('import time\ntime.sleep(30)\n',.03);self.assertEqual(r['exit_class'],'timeout');self.assertLess(r['elapsed_seconds'],2)
if __name__=='__main__':unittest.main()