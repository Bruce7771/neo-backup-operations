"""Source admission tests; zero cloud, zero Docker and no private contents."""
import importlib.util,pathlib,tempfile,tarfile,io,unittest
p=pathlib.Path(__file__).with_name('main-current-cold-restore.py');s=importlib.util.spec_from_file_location('cold_current',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_current_composed_scope_only(self):
  v={'hostname':'srv2140404-main-daily-composed','tags':['neo-daily-composed-v1'],'paths':list(m.FULL_PATHS)};m.snapshot_scope(v)
  with self.assertRaises(m.Refused):m.snapshot_scope(dict(v,hostname='old-independent-project'))
 def test_private_data_not_selected(self):
  for name in('backend/uploads/private.txt','apps/neoacademy/neo_portal.db','frontend/.env','frontend/.env.production','backend/app/config/secrets.json','backend/app/key.pem','frontend/node_modules/tool.js','data/portal.db'):self.assertFalse(m.selected_source(name))
  self.assertTrue(m.selected_source('backend/app/main.py'));self.assertTrue(m.selected_source('data/catalog_seed.db'))
 def test_traversal_refused(self):
  for name in('../backend/main.py','/backend/main.py','backend/../../etc/private'):
   with self.assertRaises(m.Refused):m.selected_source(name)
 def test_exact_stream_filter(self):
  with tempfile.TemporaryDirectory()as td:
   base=pathlib.Path(td);a=base/'source.tar.gz';target=base/'out';target.mkdir()
   with tarfile.open(a,'w:gz')as t:
    for name in('backend/app/startup_entrypoint.py','data/catalog_seed.db','frontend/index.html','apps/neoacademy/neo_portal.db','backend/uploads/private.txt'):
     b=b'synthetic';v=tarfile.TarInfo(name);v.size=len(b);t.addfile(v,io.BytesIO(b))
   result=m.extract_source(a,target);self.assertEqual(result['selected_files'],3);self.assertFalse((target/'apps/neoacademy/neo_portal.db').exists());self.assertEqual((target/'backend').stat().st_mode&0o777,0o755)
 def test_real_application_probe_is_not_generic_import(self):
  text=p.read_text();self.assertIn('backend.app.startup_entrypoint',text);self.assertIn("v.get('catalog')=='ok'",text);self.assertIn("'--network','none'",text);self.assertIn("'NEO_SOCIAL_WORKER':'0'",text);self.assertNotIn("'forget'",text);self.assertNotIn("'prune'",text)
if __name__=='__main__':unittest.main()
