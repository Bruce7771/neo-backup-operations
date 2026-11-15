"""Advancing-clock tests only: unchanged 35s/process and parent deadlines."""
import ast,importlib.util,json,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
H=pathlib.Path(__file__).parent
s=importlib.util.spec_from_file_location('metrics_launcher',H/'run-publication-retention.candidate.py');launcher=importlib.util.module_from_spec(s);s.loader.exec_module(launcher)
class Tests(unittest.TestCase):
 def fixture(self,parent):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);engine=launcher.build_engine(H,pathlib.Path(temp.name)/'engine');sys.path.insert(0,str(engine));self.addCleanup(lambda:sys.path.remove(str(engine)))
  spec=importlib.util.spec_from_file_location('metric_transport',engine/'native_parallel_transport.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);clock=[100.0]
  class Child:
   pid=99999999
   returncode=None
   def poll(self):return self.returncode
   def wait(self,timeout):
    if self.returncode is not None:return self.returncode
    clock[0]+=timeout;raise subprocess.TimeoutExpired('SYNTHETIC-PRIVATE-ARGV',timeout)
   def send_signal(self,signal):self.returncode=-2
   def kill(self):self.returncode=-9
  child=Child();reader=m.ParallelNativeCLI({'PATH':'/synthetic'},100+parent,temp.name,popen=lambda*a,**k:child)
  with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]),patch.object(m,'external_command',side_effect=lambda a,e:a),self.assertRaises(subprocess.TimeoutExpired):reader.read(['cat','blob','SYNTHETIC-PRIVATE-ID'],1024)
  return reader.timeout_diagnostic,engine
 def test_call_deadline_and_exact_numeric_fields(self):
  d,_=self.fixture(100);self.assertEqual(d['native_timeout_deadline_kind'],1);self.assertEqual(d['native_timeout_parentremaining_ms'],100000);self.assertTrue(34900<=d['native_timeout_childwait_ms']<=35100);self.assertEqual(len(d),3)
 def test_parent_segment_deadline(self):
  d,_=self.fixture(10);self.assertEqual(d['native_timeout_deadline_kind'],2);self.assertEqual(d['native_timeout_parentremaining_ms'],10000);self.assertTrue(9900<=d['native_timeout_childwait_ms']<=10100)
 def test_generated_safe_json_whitelist_and_redaction(self):
  d,engine=self.fixture(10);tree=ast.parse((engine/'retention-readonly-check.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='safe_audit_failure');ns={'json':json};exec(compile(ast.Module(body=[fn],type_ignores=[]),'actual-generated-parser','exec'),ns)
  value=dict(failure_type='TimeoutExpired',phase='derive-metadata',source_module='native_parallel_transport.py',source_line=80,metadata_stats=d)
  raw=b'SYNTHETIC-SECRET-PATH-HEADERS\n'+('NEO_RETENTION_SAFE_FAILURE '+json.dumps(value)).encode();self.assertEqual(ns['safe_audit_failure'](raw),value)
  for key,bad in [('native_timeout_deadline_kind',3),('native_timeout_childwait_ms',4500001),('native_timeout_childwait_ms','SYNTHETIC-SECRET')]:
   v=json.loads(json.dumps(value));v['metadata_stats'][key]=bad;self.assertIsNone(ns['safe_audit_failure'](('NEO_RETENTION_SAFE_FAILURE '+json.dumps(v)).encode()))
  value['metadata_stats']['argv']='SYNTHETIC-SECRET';self.assertIsNone(ns['safe_audit_failure'](('NEO_RETENTION_SAFE_FAILURE '+json.dumps(value)).encode()))
if __name__=='__main__':unittest.main()