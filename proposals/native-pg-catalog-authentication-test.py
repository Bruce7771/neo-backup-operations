#!/usr/bin/env python3
"""Synthetic authenticated native trees; no native/cloud process or real data."""
import copy,hashlib,importlib.util,json,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('catalog',Path(__file__).with_name('native-pg-catalog-authentication.proposed.py'));candidate=load('candidate',Path(__file__).with_name('retention-safety-candidate.py'))
enc=lambda x:json.dumps(x,sort_keys=True).encode();sha=lambda x:hashlib.sha256(x).hexdigest()
class Catalog(unittest.TestCase):
 def fixture(self,multi=False):
  payload={'base/data':b'ABCDEF','wal/marker.gz':b'wal'};files=[dict(path=p,bytes=len(v),sha256=sha(v))for p,v in payload.items()];seal=enc({'files':files});payload['sealed-pg.json']=seal
  treebytes={};rootnodes=[]
  for directory in ('base','wal'):
   ns=[]
   for p,v in payload.items():
    if p.startswith(directory+'/'):
     ids=[sha(v)] if not(multi and p=='base/data')else[sha(b'ABC'),sha(b'DEF')]
     ns.append({'name':p.split('/')[1],'type':'file','size':len(v),'content':ids})
   raw=enc({'nodes':ns});treebytes[sha(raw)]=raw;rootnodes.append({'name':directory,'type':'dir','subtree':sha(raw)})
  rootnodes.append({'name':'sealed-pg.json','type':'file','size':len(seal),'content':[sha(seal)]});root=enc({'nodes':rootnodes});self.reads=[]
  scope={'host':'fixture','tag':'hourly','paths':['/fixture']};inv=[{'id':s*64,'hostname':'fixture','tags':['hourly'],'paths':['/fixture']}for s in('a','b')]
  self.roots={'a'*64:root,'b'*64:root};self.treebytes=treebytes
  def rt(s,p):self.assertEqual(p,'/fixture/postgres-selfcontained');return self.roots[s]
  def rb(i):self.reads.append(i);return self.treebytes[i]
  c=m.NativePGCatalog('synthetic-repository-and-scope',scope,inv,rt,rb,time.monotonic()+180)
  outer=enc([dict(r,path='postgres-selfcontained/'+r['path'])for r in files]+[{'path':'postgres-selfcontained/sealed-pg.json','bytes':len(seal),'sha256':sha(seal)}])
  return c,files,seal,outer
 def test_single_blob_direct_NO_outer_and_shared_tree_cache(self):
  c,f,s,o=self.fixture();self.assertFalse(c.verify('a'*64,f,s)['outer_seed_used_for_this_point']);c.verify('b'*64,f,s);self.assertEqual(c.stats['native_subtree_reads'],2);self.assertEqual(c.stats['tree_cache_hits'],2);self.assertEqual(c.stats['full_outer_seed_reads'],0)
 def test_multiblob_needs_seed_and_reuses_only_identical_ordered_content(self):
  c,f,s,o=self.fixture(True)
  with self.assertRaises(m.NeedFullManifest):c.verify('a'*64,f,s)
  calls=[]
  def read(sid,path):calls.append((sid,path));return o
  self.assertTrue(c.verify('a'*64,f,s,read)['outer_seed_used_for_this_point']);c.verify('b'*64,f,s,lambda *a:self.fail('Identical bytes must reuse authenticated seed'));self.assertEqual(len(calls),1)
 def test_changed_multichunk_does_not_reuse_old_hash(self):
  c,f,s,o=self.fixture(True);c.verify('a'*64,f,s,lambda *a:o)
  r=json.loads(self.roots['b'*64]);n=next(n for n in r['nodes']if n['name']=='base');v=json.loads(self.treebytes[n['subtree']]);v['nodes'][0]['content'].reverse();raw=enc(v);n['subtree']=sha(raw);self.treebytes[sha(raw)]=raw;self.roots['b'*64]=enc(r)
  with self.assertRaises(m.NeedFullManifest):c.verify('b'*64,f,s)
 def test_missing_file_refused(self):
  c,f,s,o=self.fixture();r=json.loads(self.roots['a'*64]);r['nodes']=[n for n in r['nodes']if n['name']!='base'];self.roots['a'*64]=enc(r)
  with self.assertRaisesRegex(ValueError,'namespace'):c.verify('a'*64,f,s)
 def test_same_size_substitution_refused(self):
  c,f,s,o=self.fixture();f[0]['sha256']='f'*64
  with self.assertRaisesRegex(ValueError,'content hash'):c.verify('a'*64,f,s)
 def test_bad_child_tree_hash_refused(self):
  c,f,s,o=self.fixture();k=next(iter(self.treebytes));self.treebytes[k]=b'{"nodes":[]}'
  with self.assertRaisesRegex(ValueError,'subtree hash'):c.verify('a'*64,f,s)
 def test_native_seal_substitution_refused(self):
  c,f,s,o=self.fixture()
  with self.assertRaisesRegex(ValueError,'seal content'):c.verify('a'*64,f,b'X'*len(s))
 def test_malicious_outer_cannot_seed_hash(self):
  c,f,s,o=self.fixture(True)
  with self.assertRaisesRegex(ValueError,'outer/seal'):c.verify('a'*64,f,s,lambda *a:b'[]')
  self.assertEqual(c.proven_hashes,{})
 def test_scope_deadline_and_caps(self):
  c,f,s,o=self.fixture()
  with self.assertRaisesRegex(ValueError,'outside'):c.verify('c'*64,f,s)
  c.deadline=time.monotonic()-1
  with self.assertRaises(TimeoutError):c.verify('a'*64,f,s)
 def test_ACTUAL_derive_v3_native_branch_keeps_base_WAL_marker_checks(self):
  fixture=load('v3fixtures',ROOT/'scripts/hourly_selfcontained_v3_test.py').SelfContained();data=fixture.fixture();blobs=data[-1];sid='e'*64;root='/fixture/hourly'
  source=candidate.v3_catalog_candidate((ROOT/'scripts/hourly_selfcontained_v3.py').read_text());ns={};exec(compile(source,'candidate-actual-v3','exec'),ns)
  sealedraw=blobs[sid,root+'/postgres-selfcontained/sealed-pg.json'];files=json.loads(sealedraw)['files'];treebytes={};rootnodes=[]
  for directory in ('base','wal'):
   nodes=[]
   for row in files:
    if row['path'].startswith(directory+'/'):nodes.append({'name':row['path'].split('/')[1],'type':'file','size':row['bytes'],'content':[row['sha256']]})
   raw=enc({'nodes':nodes});treebytes[sha(raw)]=raw;rootnodes.append({'name':directory,'type':'dir','subtree':sha(raw)})
  rootnodes.append({'name':'sealed-pg.json','type':'file','size':len(sealedraw),'content':[sha(sealedraw)]});rawroot=enc({'nodes':rootnodes})
  scope=data[2]['scopes'][1];cat=m.NativePGCatalog('synthetic',scope,data[0],lambda s,p:rawroot,lambda i:treebytes[i],time.monotonic()+180)
  reads=[]
  def dump(s,p,n):reads.append(p);return blobs[s,p]
  def native(s,r,f,seal):self.assertEqual(r,root);return cat.verify(s,f,seal)
  dump.native_pg_catalog=native
  b=blobs['c'*64,'/fixture/pitr/base/backup_manifest'];args=(sid,root,blobs[sid,root+'/capture-result.json'],blobs[sid,root+'/postgres-archive-delivery.json'],blobs[sid,root+'/postgres-point.private.json'],{sha(b)},dump)
  edge=ns['derive_v3'](*args);self.assertEqual(edge['metadata_validation'],'native-PG-catalog-content-identity-v1');self.assertFalse(edge['postgres_named_target_restore_verified']);self.assertNotIn(root+'/manifest.json',reads)
  blobs[sid,root+'/postgres-selfcontained/wal/000000010000000000000001.gz']=b'wrong'
  with self.assertRaisesRegex(ValueError,'WAL fingerprint'):ns['derive_v3'](*args)
if __name__=='__main__':unittest.main()
