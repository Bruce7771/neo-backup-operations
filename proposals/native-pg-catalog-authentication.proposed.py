#!/usr/bin/env python3
"""CODE-ONLY PG catalog prototype, NOT wired into retention or deletion.

read_tree(snapshot, absolute_path) must be default-locked native `cat tree
snapshot:path`; read_blob_tree(id) must be default-locked native `cat blob id`.
The latter accepts ONLY subtree IDs reached from a native authenticated tree.
No file data blob is fetched. Repository/scope binding belongs to this instance.
"""
import hashlib,json,re,time
HEX=re.compile('[0-9a-f]{64}')
def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
class NeedFullManifest(ValueError):pass
class NativePGCatalog:
 def __init__(self,repository_binding,scope,inventory,read_tree,read_blob_tree,deadline,max_tree_bytes=16*1024*1024,max_trees=512,max_rows=20000):
  need(bool(repository_binding),'Repository binding required');self.binding=repository_binding;self.scope=scope;self.read_tree=read_tree;self.read_blob_tree=read_blob_tree;self.deadline=deadline
  need(len(scope['paths'])==1,'Single hourly root required');self.root=scope['paths'][0].rstrip('/')
  need(self.root.startswith('/') and '..'not in self.root.split('/'),'Invalid scope root')
  self.allowed={r['id']for r in inventory if r.get('hostname')==scope['host'] and scope['tag']in r.get('tags',[]) and r.get('paths')==scope['paths']}
  self.max_tree_bytes=max_tree_bytes;self.max_trees=max_trees;self.max_rows=max_rows;self.tree_cache={};self.tree_bytes=0;self.proven_hashes={};self.seed_roots={};self.stats={'native_pg_root_reads':0,'native_subtree_reads':0,'tree_cache_hits':0,'full_outer_seed_reads':0}
 def check(self):
  if time.monotonic()>=self.deadline:raise TimeoutError('Native catalog deadline exceeded')
 def tree(self,raw,expected=None):
  self.check();need(isinstance(raw,bytes) and len(raw)<=8*1024*1024,'Oversize native tree')
  if expected:need(sha(raw)==expected,'Native subtree hash mismatch')
  x=json.loads(raw);need(isinstance(x,dict) and isinstance(x.get('nodes'),list),'Invalid native tree')
  seen=set()
  for n in x['nodes']:
   name=n.get('name');need(isinstance(name,str) and name not in ('','.','..') and '/'not in name and '\\'not in name and name not in seen,'Unsafe/duplicate native node');seen.add(name)
   need(n.get('type')in ('file','dir'),'Unsupported PG native node')
   if n['type']=='dir':need(isinstance(n.get('subtree'),str) and HEX.fullmatch(n['subtree'])is not None,'Invalid native subtree ID')
   else:
    need(type(n.get('size'))is int and n['size']>=0,'Invalid native file size')
    ids=n.get('content')or[];need(isinstance(ids,list) and all(isinstance(v,str)and HEX.fullmatch(v)is not None for v in ids),'Invalid content identity');need((n['size']==0 and not ids)or(n['size']>0 and bool(ids)),'Missing/inconsistent content identity')
  return x['nodes']
 def subtree(self,identifier):
  self.check()
  if identifier in self.tree_cache:self.stats['tree_cache_hits']+=1;return self.tree_cache[identifier]
  need(len(self.tree_cache)<self.max_trees,'Native tree-count bound exceeded')
  raw=self.read_blob_tree(identifier);nodes=self.tree(raw,identifier);need(self.tree_bytes+len(raw)<=self.max_tree_bytes,'Native tree-byte bound exceeded')
  self.tree_cache[identifier]=nodes;self.tree_bytes+=len(raw);self.stats['native_subtree_reads']+=1;return nodes
 def nodes(self,sid):
  self.check();need(sid in self.allowed and HEX.fullmatch(sid)is not None,'Snapshot outside exact hourly scope')
  raw=self.read_tree(sid,self.root+'/postgres-selfcontained');first=self.tree(raw);self.stats['native_pg_root_reads']+=1
  todo=[('',first)];files={};dirs=0
  while todo:
   prefix,nodes=todo.pop();dirs+=1;need(dirs<=self.max_trees and len(files)<=self.max_rows,'Native namespace bound exceeded')
   for n in nodes:
    rel=prefix+n['name']
    if n['type']=='dir':todo.append((rel+'/',self.subtree(n['subtree'])))
    else:files[rel]={'bytes':n['size'],'content':tuple(n.get('content')or[])}
  need(len(files)<=self.max_rows,'Native row bound exceeded');return files,sha(raw)
 @staticmethod
 def key(node):return (node['bytes'],node['content'])
 def seed(self,sid,nodes,outer_raw,sealed_raw,files):
  """Authenticate same original manifest↔seal contract once for unseen content.

  Caller MUST obtain outer_raw with exact immutable sid's native dump, bounded
  <=8MiB. No cache entry is established from unauthenticated external JSON.
  This preserves the previous metadata trust boundary, not physical replay.
  """
  need(isinstance(outer_raw,bytes) and len(outer_raw)<=8*1024*1024,'Oversize seed outer manifest')
  outer=json.loads(outer_raw);need(isinstance(outer,list),'Invalid seed manifest');by={r['path']:r for r in outer};need(len(by)==len(outer),'Duplicate seed row')
  expected=[dict(r,path='postgres-selfcontained/'+r['path'])for r in files]+[{'path':'postgres-selfcontained/sealed-pg.json','bytes':len(sealed_raw),'sha256':sha(sealed_raw)}]
  for r in expected:need(by.get(r['path'])==r,'Seed outer/seal mismatch')
  additions={}
  for r in files:
   n=nodes[r['path']];k=self.key(n);old=self.proven_hashes.get(k)or additions.get(k)
   need(old is None or old==r['sha256'],'Conflicting same-content seed hash');additions[k]=r['sha256']
  need(len(set(self.proven_hashes)|set(additions))<=self.max_rows,'Content hash-cache bound exceeded')
  self.proven_hashes.update(additions);self.seed_roots[sid]=sha(outer_raw);self.stats['full_outer_seed_reads']+=1
 def verify(self,sid,files,sealed_raw,read_outer=None):
  nodes,pg_tree=self.nodes(sid);need(isinstance(files,list) and files,'Empty PG seal')
  by={}
  for r in files:
   name=r.get('path');need(isinstance(name,str)and name and not name.startswith('/') and '..'not in name.split('/') and '\\'not in name and name!='sealed-pg.json' and name not in by,'Unsafe/duplicate PG seal row')
   need(set(r)=={'path','bytes','sha256'} and type(r['bytes'])is int and r['bytes']>=0 and isinstance(r['sha256'],str)and HEX.fullmatch(r['sha256'])is not None,'Invalid seal row');by[name]=r
  need(set(nodes)==set(by)|{'sealed-pg.json'},'Native PG namespace differs from seal')
  need(nodes['sealed-pg.json']['bytes']==len(sealed_raw),'Native seal length differs')
  seal_ids=nodes['sealed-pg.json']['content']
  if len(seal_ids)==1:need(seal_ids[0]==sha(sealed_raw),'Native seal content differs')
  unknown=[]
  for name,r in by.items():
   n=nodes[name];need(n['bytes']==r['bytes'],'Native sealed file length differs');ids=n['content']
   direct=sha(b'')if n['bytes']==0 else ids[0]if len(ids)==1 else None
   known=direct if direct is not None else self.proven_hashes.get(self.key(n))
   if known is None:unknown.append(name)
   else:need(known==r['sha256'],'Native content hash differs from seal')
  if unknown:
   if read_outer is None:raise NeedFullManifest('Unseen multi-blob file requires authenticated outer seed')
   self.seed(sid,nodes,read_outer(sid,self.root+'/manifest.json'),sealed_raw,files)
  provenance={'schema':1,'validation':'native-PG-catalog-content-identity-v1','repository_scope_binding':self.binding,'snapshot':sid,'pg_root_tree_sha256':pg_tree,'files':[{**by[n],'content_blob_ids':list(nodes[n]['content'])}for n in sorted(by)],'authenticated_seed_outer_sha256':dict(sorted(self.seed_roots.items())),'physical_restore_claimed':False,'synthetic_outer_manifest':False}
  return {'validation':'native-PG-catalog-content-identity-v1','snapshot':sid,'catalog_proof_sha256':sha(canonical(provenance)),'file_rows':len(by),'outer_seed_used_for_this_point':sid in self.seed_roots,'physical_restore_claimed':False}
