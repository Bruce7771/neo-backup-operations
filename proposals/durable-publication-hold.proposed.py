"""Inactive durable publication HOLD, using flock+root-private files only.

No B2 client, service control, database writes, auto-expiry/unfence or pruning.
Install/producer enrollment/SSH protocol are separately reviewed requirements.
"""
import contextlib,fcntl,hashlib,json,os,pathlib,re,secrets,stat,time
HEX=re.compile('[0-9a-f]{64}')
class PublicationHeld(RuntimeError):pass
def need(x,m):
 if not x:raise ValueError(m)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def identity(nonce):
 need(isinstance(nonce,str)and HEX.fullmatch(nonce),'Invalid owner nonce');return hashlib.sha256(nonce.encode()).hexdigest()
class Gate:
 def __init__(self,root,now=time.time):
  self.root=pathlib.Path(root);self.now=now;st=self.root.lstat();need(stat.S_ISDIR(st.st_mode)and not self.root.is_symlink()and st.st_uid==os.geteuid()and stat.S_IMODE(st.st_mode)==0o700,'Private gate directory required');self.lock=self.root/'publication.lock';self.state=self.root/'hold.json'
 @contextlib.contextmanager
 def mutex(self,exclusive):
  fd=os.open(self.lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
  try:
   s=os.fstat(fd);need(stat.S_ISREG(s.st_mode)and s.st_uid==os.geteuid()and stat.S_IMODE(s.st_mode)==0o600 and s.st_nlink==1,'Unsafe gate mutex');fcntl.flock(fd,(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB);yield fd
  finally:os.close(fd)
 def read(self):
  try:fd=os.open(self.state,os.O_RDONLY|os.O_NOFOLLOW)
  except FileNotFoundError:return None
  with os.fdopen(fd,'rb')as f:
   st=os.fstat(f.fileno());need(stat.S_ISREG(st.st_mode)and st.st_uid==os.geteuid()and stat.S_IMODE(st.st_mode)==0o600 and st.st_nlink==1 and st.st_size<=4096,'Unsafe HOLD state');raw=f.read(4097)
  v=json.loads(raw);need(v.get('schema')==1 and v.get('phase')in('held','native-inflight','native-complete','uncertain')and HEX.fullmatch(v.get('owner_hash',''))and HEX.fullmatch(v.get('producer_policy_sha256','')),'Invalid HOLD schema');return v
 def write(self,v):
  temp=self.root/('.hold-'+secrets.token_hex(8));fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  try:
   with os.fdopen(fd,'wb')as f:f.write(canonical(v));f.flush();os.fsync(f.fileno())
   os.replace(temp,self.state);d=os.open(self.root,os.O_DIRECTORY);os.fsync(d);os.close(d)
  finally:
   if temp.exists():temp.unlink()
 @contextlib.contextmanager
 def writer(self):
  # Enter BEFORE selecting any parent/capture/job lock; retain through native
  # snapshot publication. Application writers never import/use this gate.
  with self.mutex(False)as fd:
   if self.read()is not None:raise PublicationHeld('Publication HOLD; expired state also requires reconciliation')
   # Pass this FD explicitly to every native publishing child. subprocess
   # close_fds defaults to True; inheritance is not automatic in Python.
   yield fd
 def acquire(self,nonce,producer_policy_sha256,maximum_seconds=120):
  need(HEX.fullmatch(producer_policy_sha256)and type(maximum_seconds)is int and 30<=maximum_seconds<=120,'Invalid bounded publication lease')
  with self.mutex(True):
   need(self.read()is None,'Existing HOLD including expired/uncertain cannot be replaced');start=self.now();v=dict(schema=1,phase='held',owner_hash=identity(nonce),producer_policy_sha256=producer_policy_sha256,created_epoch=start,expires_epoch=start+maximum_seconds,native_started=False,native_completed=False,postcondition_verified=False);self.write(v);return {k:v[k]for k in('created_epoch','expires_epoch','producer_policy_sha256')}
 def owned(self,nonce):
  v=self.read();need(v is not None and secrets.compare_digest(v['owner_hash'],identity(nonce)),'Missing/wrong HOLD owner');return v
 def begin_forget(self,nonce,exact_candidate_sha256,native_timeout_seconds):
  need(HEX.fullmatch(exact_candidate_sha256)and type(native_timeout_seconds)is int and 1<=native_timeout_seconds<=60,'Bounded exact forget only')
  with self.mutex(True):
   v=self.owned(nonce);need(v['phase']=='held'and self.now()+native_timeout_seconds+15<=v['expires_epoch'],'Insufficient remaining HOLD budget; no native action');v.update(phase='native-inflight',native_started=True,candidate_sha256=exact_candidate_sha256,native_deadline=self.now()+native_timeout_seconds);self.write(v)
 def acknowledge(self,nonce,*,native_exit_zero,exact_transition_verified):
  need(type(native_exit_zero)is bool and type(exact_transition_verified)is bool,'Explicit boolean native outcome required')
  with self.mutex(True):
   v=self.owned(nonce);need(v['phase']=='native-inflight','No matching native action');v.update(phase='native-complete'if native_exit_zero and exact_transition_verified else'uncertain',native_completed=bool(native_exit_zero),postcondition_verified=bool(exact_transition_verified));self.write(v)
 def release(self,nonce):
  with self.mutex(True):
   v=self.owned(nonce);need((v['phase']=='held'and not v['native_started'])or(v['phase']=='native-complete'and v['native_completed']and v['postcondition_verified']),'Unknown/in-flight native outcome cannot release HOLD');self.state.unlink();d=os.open(self.root,os.O_DIRECTORY);os.fsync(d);os.close(d)
 def status(self):
  with self.mutex(False):
   v=self.read()
   if v is None:return {'held':False}
   return {'held':True,'phase':v['phase'],'expired':self.now()>=v['expires_epoch'],'automatic_unfence':False,'producer_policy_sha256':v['producer_policy_sha256']}
