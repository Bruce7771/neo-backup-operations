"""Main-thread authenticated parse/LRU, up to four RAW-only native workers."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,json,re,time
from native_pg_catalog_v2 import NativePGCatalog,need

class ParallelPGCatalog(NativePGCatalog):
 def __init__(self,*args,cancel_callback=lambda:None,**kwargs):
  super().__init__(*args,**kwargs);self.cancel_callback=cancel_callback
  self.tree_cache=OrderedDict();self.tree_bytes=0
  self.stats.update(tree_cache_evictions=0,max_parallel_fetches=0)
 def _cache_get(self,identifier):
  if identifier not in self.tree_cache:return None
  item=self.tree_cache.pop(identifier);self.tree_cache[identifier]=item
  self.stats['tree_cache_hits']+=1;return item[0]
 def _cache_put(self,identifier,raw,nodes):
  need(len(raw)<=self.max_tree_bytes,'Individual native tree exceeds cache bound')
  while self.tree_cache and(len(self.tree_cache)>=self.max_trees or self.tree_bytes+len(raw)>self.max_tree_bytes):
   _,(_,size)=self.tree_cache.popitem(last=False);self.tree_bytes-=size;self.stats['tree_cache_evictions']+=1
  self.tree_cache[identifier]=(nodes,len(raw));self.tree_bytes+=len(raw)
 def subtree(self,identifier):
  # Preserve original public helper semantics with bounded main-thread LRU.
  self.check();cached=self._cache_get(identifier)
  if cached is not None:return cached
  raw=self.read_blob_tree(identifier);nodes=self.tree(raw,identifier)
  self._cache_put(identifier,raw,nodes);self.stats['native_subtree_reads']+=1;return nodes
 def nodes(self,sid):
  pool=None
  try:
   self.check();need(sid in self.allowed and re.fullmatch('[0-9a-f]{64}',sid)is not None,'Snapshot outside exact hourly scope')
   root_raw=self.read_tree(sid,self.root+'/postgres-selfcontained');first=self.tree(root_raw);self.stats['native_pg_root_reads']+=1
   pending=[('',first)];files={};directories=0
   pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='neo-native-raw')
   while pending:
    self.check();requests=[]
    for prefix,nodes in pending:
     directories+=1;need(directories<=self.max_trees,'Per-point directory bound exceeded')
     for n in nodes:
      relative=prefix+n['name']
      if n['type']=='dir':requests.append((relative+'/',n['subtree']))
      else:files[relative]={'bytes':n.get('size',0),'content':tuple(n.get('content')or[])}
      need(len(files)<=self.max_rows,'Native row bound exceeded')
    need(directories+len(requests)<=self.max_trees,'Per-point directory bound exceeded')
    # Deterministic path order; duplicated subtree IDs join one Future/read.
    requests.sort();unique=list(dict.fromkeys(identifier for _,identifier in requests));resolved={}
    for start in range(0,len(unique),4):
     ids=unique[start:start+4];future_by_id={};parsed={}
     for identifier in ids:
      cached=self._cache_get(identifier)
      if cached is not None:resolved[identifier]=cached
      else:future_by_id[identifier]=pool.submit(self.read_blob_tree,identifier)
     self.stats['max_parallel_fetches']=max(self.stats['max_parallel_fetches'],len(future_by_id))
     remaining=self.deadline-time.monotonic()
     if remaining<=0:raise TimeoutError('Native catalog deadline exceeded')
     for future in as_completed(future_by_id.values(),timeout=remaining):
      identifier=next(k for k,v in future_by_id.items()if v is future)
      # Authentication/parsing happens ONLY here in the main thread. A corrupt
      # early result aborts and cancels other own children immediately.
      raw=future.result();parsed[identifier]=(raw,self.tree(raw,identifier))
      known=dict(resolved);known.update({i:n for i,(_,n)in parsed.items()})
      weight=sum(len(known[i])for _,i in requests if i in known)
      need(len(files)+weight<=self.max_rows+self.max_trees,'Pending native node bound exceeded')
     for identifier in ids:
      if identifier in parsed:
       raw,nodes=parsed.pop(identifier);self._cache_put(identifier,raw,nodes)
       resolved[identifier]=nodes;self.stats['native_subtree_reads']+=1
     weight=sum(len(resolved[i])for _,i in requests if i in resolved)
     need(len(files)+weight<=self.max_rows+self.max_trees,'Pending native node bound exceeded')
    pending=[(prefix,resolved[identifier])for prefix,identifier in requests]
   return files,hashlib.sha256(root_raw).hexdigest()
  except BaseException:
   self.cancel_callback();raise
  finally:
   if pool is not None:pool.shutdown(wait=True,cancel_futures=True)