"""Real local child-process tests; zero cloud, credentials, or restic repositories."""
import json,os,pathlib,subprocess,sys,tempfile,time,unittest
M=globals().get('DIAGNOSTIC_MODULE')
if M is None:
 import importlib.util
 p=pathlib.Path(__file__).with_name('native-dump-controlled-diagnostic.proposed.py');s=importlib.util.spec_from_file_location('controlled_dump',p);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
class T(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.work=pathlib.Path(self.tmp.name);self.env={'PATH':os.environ.get('PATH',''),'XDG_CACHE_HOME':str(self.work/'cache')};self.proofs=[]
 def tearDown(self):self.tmp.cleanup()
 def call(self,code,timeout=1,deadline=2):
  def child(args,**kwargs):return subprocess.Popen([sys.executable,'-c',code],**kwargs)
  return M.diagnostic_dump(['restic','--no-lock','dump','a'*64,'/capture/base/backup_manifest'],self.env,self.work,8192,timeout,time.monotonic()+deadline,self.proofs.append,popen=child,poll_seconds=.01,sample_seconds=.02)
 def test_delayed_first_bytes_and_cache_metadata(self):
  raw=self.call("import os,pathlib,time;time.sleep(.04);p=pathlib.Path(os.environ['XDG_CACHE_HOME']);p.mkdir();(p/'index').write_bytes(b'x'*64);print('{}',flush=True);time.sleep(.04)")
  self.assertEqual(raw,b'{}\n');p=self.proofs[0];self.assertIsNotNone(p['first_stdout_observed_ms']);self.assertGreaterEqual(p['first_stdout_observed_ms'],20);self.assertEqual(p['stdout_bytes'],3);self.assertGreaterEqual(p['cache_after']['files'],1);self.assertTrue(p['own_child_reaped'])
 def test_stalled_child_cancelled_reaped_no_first_byte(self):
  with self.assertRaises(subprocess.TimeoutExpired):self.call('import time;time.sleep(10)',.15,1)
  p=self.proofs[0];self.assertTrue(p['timed_out']);self.assertTrue(p['own_child_reaped']);self.assertEqual(p['stdout_bytes'],0);self.assertIsNone(p['first_stdout_observed_ms'])
 def test_server_code_only_no_error_body_disclosure(self):
  with self.assertRaises(subprocess.CalledProcessError):self.call("import sys;sys.stderr.write('AccessDenied https://private.example.test/?FAKE_SECRET_TEST_VALUE');sys.exit(7)")
  p=self.proofs[0];self.assertEqual(p['stderr_static_codes'],['AccessDenied']);self.assertNotIn('FAKE_SECRET',json.dumps(p));self.assertEqual(p['exit_code'],7)
 def test_overall_deadline_wins_over_per_call_limit(self):
  with self.assertRaises(subprocess.TimeoutExpired):self.call('import time;time.sleep(10)',90,.12)
  self.assertLess(self.proofs[0]['elapsed_milliseconds'],2000);self.assertTrue(self.proofs[0]['own_child_reaped'])
 def test_above_reviewed_90_limit_refused_before_start(self):
  with self.assertRaises(ValueError):self.call('raise AssertionError()',90.01,120)
  self.assertEqual(self.proofs,[])
r=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(T));print(json.dumps({'scope':'controlled-dump-native-child-process-tests','tests':r.testsRun,'passed':r.wasSuccessful(),'cloud_requests':0,'real_restic_repository_used':False,'production_secrets_used':False}));raise SystemExit(not r.wasSuccessful())
