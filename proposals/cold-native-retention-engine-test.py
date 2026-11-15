"""Tests the actual generated dump closure; no native/cloud execution."""
import ast,importlib.util,json,pathlib,subprocess,tempfile,time,types,unittest,copy
HERE=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('cold_builder',HERE/'build-cold-native-retention-engine.proposed.py');builder=importlib.util.module_from_spec(s);s.loader.exec_module(builder)
class T(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.root=pathlib.Path(cls.tmp.name);cls.engine=builder.build(HERE.parent/'scripts',cls.root/'engine');cls.source=(cls.engine/'retention-audit.py').read_text();main=next(n for n in ast.parse(cls.source).body if isinstance(n,ast.FunctionDef)and n.name=='main');cls.node=next(n for n in ast.walk(main)if isinstance(n,ast.FunctionDef)and n.name=='dump')
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def setUp(self):
  self.now=0.;self.calls=[];self.failure=False;self.env={'fixture':'no-credentials'};self.budget=types.SimpleNamespace(segment_end=120.,job_end=540.)
  def run(args,**kw):
   self.calls.append({'args':args,'timeout':kw['timeout'],'env_identical':kw['env']is self.env,'FSIZE_hook':kw.get('preexec_fn')is not None})
   if self.failure:raise subprocess.CalledProcessError(1,'synthetic-reviewed-dump')
   kw['stdout'].write(b'{}')
  fake=types.SimpleNamespace(run=run,DEVNULL=subprocess.DEVNULL);g={'time':types.SimpleNamespace(monotonic=lambda:self.now),'deadline':240.,'BUDGET':self.budget,'tempfile':tempfile,'work':self.root,'env':self.env,'metadata_batch':types.SimpleNamespace(handles=lambda *a:False),'subprocess':fake,'external_command':lambda a,e:['restic','--no-lock']+a[1:]};factory=ast.FunctionDef(name='factory',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=[ast.Assign(targets=[ast.Name(id='cold_pitr_manifest_used',ctx=ast.Store())],value=ast.Constant(False)),copy.deepcopy(self.node),ast.Return(value=ast.Name(id='dump',ctx=ast.Load()))],decorator_list=[]);exec(compile(ast.fix_missing_locations(ast.Module(body=[factory],type_ignores=[])),'actual-generated-cold-dump','exec'),g);self.dump=g['factory']()
 def test_first_cold90_then_warm25_same_cache_and_fsize(self):
  self.dump('a'*64,'/pitr/base/backup_manifest',8*1024*1024);self.now=61.624;self.dump('b'*64,'/pitr/base/backup_manifest',8*1024*1024);self.assertEqual([x['timeout']for x in self.calls],[90,25]);self.assertTrue(all(x['env_identical']and x['FSIZE_hook']for x in self.calls))
 def test_other_metadata25_does_not_consume_cold_manifest_slot(self):
  self.dump('a'*64,'/other/manifest.json',8*1024*1024);self.dump('a'*64,'/pitr/base/backup_manifest',8*1024*1024);self.assertEqual([x['timeout']for x in self.calls],[25,90])
 def test_wrong_size_contract_remains25(self):
  self.dump('a'*64,'/pitr/base/backup_manifest',1024);self.dump('a'*64,'/pitr/base/backup_manifest',8*1024*1024);self.assertEqual([x['timeout']for x in self.calls],[25,90])
 def test_segment_and_global_remaining_bound_cold_call(self):
  self.budget.segment_end=40.;self.dump('a'*64,'/pitr/base/backup_manifest',8*1024*1024);self.assertEqual(self.calls[0]['timeout'],40)
  self.setUp();self.budget.job_end=12.;self.dump('a'*64,'/pitr/base/backup_manifest',8*1024*1024);self.assertEqual(self.calls[0]['timeout'],12)
 def test_exhausted_remaining_refuses_child(self):
  self.now=241.
  with self.assertRaises(TimeoutError):self.dump('a'*64,'/pitr/base/backup_manifest',8*1024*1024)
  self.assertEqual(self.calls,[])
 def test_native_error_no_second_attempt_candidate_or_GC(self):
  self.failure=True;before=sorted(x.name for x in self.root.iterdir())
  with self.assertRaises(subprocess.CalledProcessError):self.dump('a'*64,'/pitr/base/backup_manifest',8*1024*1024)
  self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0]['args'][2],'dump');self.assertEqual(before,sorted(x.name for x in self.root.iterdir()))
 def test_actual_global_budgets_and_other_sources_unchanged(self):
  budget=(self.engine/'staged_derive.py').read_text();self.assertIn('self.job_end=self.start+540',budget);self.assertIn('self.metadata_end=self.start+240',budget);self.assertIn('self.now()+120',budget);self.assertIn('resource.setrlimit(resource.RLIMIT_FSIZE,(maximum,maximum))',self.source)
  self.assertNotIn('forget',ast.unparse(self.node));self.assertNotIn('prune',ast.unparse(self.node))
r=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(T));print(json.dumps({'scope':'actual-generated-native-cold-read-budget-fix','tests':r.testsRun,'passed':r.wasSuccessful(),'cloud_calls':0,'normal_other_calls_seconds':25,'first_cold_manifest_max_seconds':90,'whole_job_seconds':540,'metadata_total_seconds':240,'metadata_segment_seconds':120,'deletion_enabled':False}));raise SystemExit(not r.wasSuccessful())
