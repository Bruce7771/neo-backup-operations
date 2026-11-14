"""CODE-ONLY same-job staged derive. No cloud calls, import actions or deletion."""
import hashlib,hmac,json,os,re,secrets,stat,time,threading
from pathlib import Path
HEX=re.compile('[0-9a-f]{64}')
def need(ok,msg):
 if not ok:raise ValueError(msg)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
class Budget:
 def __init__(self,start=None,now=time.monotonic):
  self.now=now;self.start=now()if start is None else start
  need(type(self.start)in(int,float)and 0<=now()-self.start<540,'Invalid same-job origin')
  self.metadata_end=self.start+240;self.finalize_end=self.start+270;self.job_end=self.start+540
  self.segment_end=None;self.segments=0
 def metadata(self):
  if self.now()>=self.metadata_end:raise TimeoutError('Metadata total budget exhausted')
 def begin_child(self):
  self.metadata()
  if self.segment_end is None or self.segment_end-self.now()<35:
   self.segments+=1;need(self.segments<=2,'Two metadata segments exhausted')
   self.segment_end=min(self.now()+120,self.metadata_end)
  self.check();return self.segment_end
 def check(self):
  self.metadata()
  if self.segment_end is not None and self.now()>=self.segment_end:raise TimeoutError('Metadata segment exhausted')
 def phase_timeout(self,phase,maximum):
  boundary=self.metadata_end if phase=='metadata'else self.finalize_end if phase=='finalize'else self.job_end
  left=boundary-self.now()
  if phase=='integrity':left-=90
  if left<=0:raise TimeoutError('Same-job phase budget exhausted')
  return min(maximum,left)
class Journal:
 """New 0700 directory; RAM-only MAC authority, never trust persisted JSON."""
 def __init__(self,path,binding,budget,max_bytes=512*1024*1024,max_entries=4096):
  self.root=Path(path);self.root.mkdir(mode=0o700,exist_ok=False);self.binding=sha(enc(binding));self.budget=budget
  self.guard=threading.RLock();self.key=secrets.token_bytes(32);self.sources={};self.trees={};self.receipts={};self.bytes=0;self.max_bytes=max_bytes;self.max_entries=max_entries;self.replay=False;self.seen=set()
  self._private(self.root,True)
 def _private(self,p,directory=False):
  st=p.lstat();need(not stat.S_ISLNK(st.st_mode)and st.st_uid==os.geteuid()and stat.S_IMODE(st.st_mode)==(0o700 if directory else 0o600),'Unsafe private staged node')
  need(stat.S_ISDIR(st.st_mode)if directory else stat.S_ISREG(st.st_mode)and st.st_nlink==1,'Unsafe staged node type/link')
 def _body(self,raw):
  with self.guard:return self._body_locked(raw)
 def _body_locked(self,raw):
  need(isinstance(raw,bytes),'Staged source bytes required');digest=sha(raw);p=self.root/(digest+'.bin')
  if not p.exists():
   need(self.bytes+len(raw)<=self.max_bytes and len(list(self.root.glob('*.bin')))<self.max_entries,'Staged byte/entry cap exhausted')
   fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
   with os.fdopen(fd,'wb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
   self.bytes+=len(raw)
  else:need(self._read({'sha256':digest,'bytes':len(raw)})==raw,'Conflicting staged body')
  return {'sha256':digest,'bytes':len(raw)}
 def _read(self,row):
  need(set(row)=={'sha256','bytes'}and HEX.fullmatch(row['sha256'])and type(row['bytes'])is int and 0<=row['bytes']<=self.max_bytes,'Invalid staged identity')
  p=self.root/(row['sha256']+'.bin');raw=self._private_bytes(p,row['bytes']);need(sha(raw)==row['sha256'],'Staged digest changed');return raw
 def _private_bytes(self,p,maximum):
  self._private(p);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
  with os.fdopen(fd,'rb')as f:
   st=os.fstat(f.fileno());need(stat.S_ISREG(st.st_mode)and st.st_uid==os.geteuid()and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1 and st.st_size<=maximum,'Unsafe private staged read');raw=f.read(maximum+1);need(len(raw)<=maximum,'Oversize private staged read');return raw
 def source(self,sid,path,maximum,fetch,origin='native-exact-snapshot-file'):
  self.budget.check();need(HEX.fullmatch(sid)and isinstance(path,str)and path.startswith('/')and'..'not in path.split('/'),'Invalid staged source identity');key=(sid,path,origin)
  if key not in self.sources:
   need(not self.replay,'Replay source was not verified');raw=fetch();need(len(raw)<=maximum,'Oversize staged source');self.sources[key]=self._body(raw)
  row=self.sources[key];need(row['bytes']<=maximum,'Staged source exceeds requested bound');return self._read(row)
 def tree(self,identifier,fetch):
  self.budget.check();need(HEX.fullmatch(identifier),'Invalid reached tree identity')
  if identifier not in self.trees:
   need(not self.replay,'Replay tree was not verified');raw=fetch();need(sha(raw)==identifier,'Reached native tree differs');self.trees[identifier]=self._body(raw)
  raw=self._read(self.trees[identifier]);need(sha(raw)==identifier,'Cached reached tree differs');return raw
 def finish(self,sid,edge):
  self.budget.check();need(not self.replay and sid not in self.receipts,'Duplicate or replayed child completion')
  body={'schema':1,'binding':self.binding,'snapshot':sid,'edge':edge,'sources':[{'snapshot':s,'path':p,'origin':o,**r}for(s,p,o),r in sorted(self.sources.items())], 'native_trees':[{'tree_id':i,**r}for i,r in sorted(self.trees.items())]}
  raw=enc(body);record={'body':body,'mac':hmac.new(self.key,raw,'sha256').hexdigest()};p=self.root/(sid+'.receipt');fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb')as f:f.write(enc(record));f.flush();os.fsync(f.fileno())
  self.receipts[sid]=sha(enc(record))
 def verify_receipt(self,sid):
  need(sid in self.receipts,'Child has no completed verified receipt');p=self.root/(sid+'.receipt');raw=self._private_bytes(p,4*1024*1024);need(sha(raw)==self.receipts[sid],'Child receipt changed');record=json.loads(raw);body=record['body'];need(hmac.compare_digest(record['mac'],hmac.new(self.key,enc(body),'sha256').hexdigest()),'Child receipt MAC mismatch');need(body['binding']==self.binding and body['snapshot']==sid,'Cross-input child receipt');return body
 def start_replay(self,roster):
  need(set(roster)==set(self.receipts),'Partial metadata cannot be admitted')
  for sid in roster:self.verify_receipt(sid)
  for row in self.sources.values():self._read(row)
  for identifier,row in self.trees.items():need(sha(self._read(row))==identifier,'Native cached tree changed')
  self.replay=True

def staged_derive(derive,inventory,plans,policy,overrides,restored,dump,batch,budget,path):
 """No source reads in final replay. Existing derive validates final full roster."""
 scope=[s for s in policy['scopes']if s['kind']=='hourly'];need(len(scope)==1,'One hourly scope required');s=scope[0]
 roster=[]
 journal=Journal(path,{'inventory':inventory,'plans':plans,'policy':policy,'overrides':overrides,'restored':restored,'repository_scope_binding':batch.binding},budget)
 catalog=batch.catalog;native_tree=catalog.read_tree;native_blob=catalog.read_blob_tree;native_catalog=dump.native_pg_catalog;old_origin=catalog.authenticated_file_origin
 catalog.read_tree=lambda sid,p:journal.source(sid,p,8*1024*1024,lambda:native_tree(sid,p),'native-cat-tree-exact-snapshot')
 catalog.read_blob_tree=lambda identity:journal.tree(identity,lambda:native_blob(identity))
 def recorded(sid,p,maximum):return journal.source(sid,p,maximum,lambda:dump(sid,p,maximum))
 def verify(sid,root,files,sealed):
  if journal.replay:journal.verify_receipt(sid)
  return native_catalog(sid,root,files,sealed)
 recorded.native_pg_catalog=verify
 def deadline(value):batch.deadline=value;batch.reader.deadline=value;catalog.deadline=value
 try:
  deadline(budget.begin_child());derive(inventory,plans,policy,overrides,restored,recorded,child_subset=[],child_observer=roster.extend);need(len(roster)<=4096,'Staged child cap exhausted')
  for sid in roster:
   deadline(budget.begin_child());edges,_,_=derive(inventory,plans,policy,overrides,restored,recorded,child_subset=[sid]);need(len(edges)==1 and edges[0]['child_snapshot']==sid,'Staged child edge mismatch');journal.finish(sid,edges[0])
  budget.check();journal.start_replay(roster);deadline(budget.segment_end)
  def origin(sid,p,raw):
   key=(sid,p,'native-exact-snapshot-file');need(key in journal.sources and journal._read(journal.sources[key])==raw,'Replay file lacks exact native origin');return True
  catalog.authenticated_file_origin=origin;catalog.proven_hashes={};catalog.seed_roots={}
  result=derive(inventory,plans,policy,overrides,restored,recorded)
  for edge in result[0]:
   body=journal.verify_receipt(edge['child_snapshot']);need(body['edge']==edge,'Final replay edge differs from verified child')
  budget.check();batch.stats.update(staged_completed_children=len(roster),staged_segments=budget.segments,staged_cache_bytes=journal.bytes,staged_final_replay_verified=1)
  return result
 finally:
  catalog.authenticated_file_origin=old_origin
  # Tree wrappers retain private same-job data only; no authority persists off-job.