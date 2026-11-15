"""Bounded four-process native metadata transport, inactive candidate only."""
import math,os,re,resource,signal,subprocess,tempfile,threading,time
from pathlib import Path
from external_reader_contract import command as external_command

def require(ok,message):
 if not ok:raise ValueError(message)

def readonly_metadata_command(args):
 require(isinstance(args,list)and len(args)==3 and all(isinstance(a,str)for a in args),'Exact metadata read arguments required')
 if args[:2]==['cat','blob']:
  require(re.fullmatch('[0-9a-f]{64}',args[2])is not None,'Exact native tree identifier required')
 elif args[:2]==['cat','tree']:
  sid,sep,path=args[2].partition(':')
  require(re.fullmatch('[0-9a-f]{64}',sid)is not None,'Exact native snapshot/tree identifier required')
  require(not sep or(path.startswith('/')and re.fullmatch('/[A-Za-z0-9_./-]+',path)is not None and'..'not in path.split('/')),'Exact native metadata path required')
 elif args[0]=='dump':
  require(re.fullmatch('[0-9a-f]{64}',args[1])is not None and re.fullmatch('/[A-Za-z0-9_./-]+',args[2])is not None and'..'not in args[2].split('/'),'Exact native metadata dump required')
 else:raise ValueError('Only immutable metadata cat/tree/blob or exact snapshot dump permitted')
 return ['restic','--no-lock']+args

class ParallelNativeCLI:
 def __init__(self,env,deadline,directory,max_live=4,process_limit=4096,byte_limit=512*1024*1024,popen=subprocess.Popen,deadline_reserver=None,preplan_read_only_nolock=False):
  require(max_live==4,'Exactly four maximum native children reviewed')
  require(deadline_reserver is None or callable(deadline_reserver),'Optional trusted deadline reservation callback required')
  require(type(preplan_read_only_nolock)is bool,'Explicit preplan read-only flag required')
  self.env=env;self.deadline=deadline;self.directory=Path(directory);self.popen=popen
  self.deadline_reserver=deadline_reserver;self.preplan_read_only_nolock=preplan_read_only_nolock
  self.max_live=max_live;self.process_limit=process_limit;self.byte_limit=byte_limit
  self.calls=0;self.output_bytes=0;self.max_live_children=0;self.peak_children_rss_kib=0;self.timeout_diagnostic={}
  self._reserved=0;self._children={};self._lock=threading.Lock();self._cancel_lock=threading.Lock();self._cancelled=threading.Event();self._slots=threading.BoundedSemaphore(max_live)
 def _sample_rss(self):
  with self._lock:pids=list(self._children)
  rss=0
  for pid in pids:
   try:
    for line in Path('/proc',str(pid),'status').read_text().splitlines():
     if line.startswith('VmRSS:'):rss+=int(line.split()[1]);break
   except (FileNotFoundError,ProcessLookupError,PermissionError):pass
  with self._lock:self.peak_children_rss_kib=max(self.peak_children_rss_kib,rss)
 def cancel_all(self):
  """No new child after this point; signal every OWN child before waiting any."""
  self._cancelled.set()
  with self._cancel_lock:
   with self._lock:children=list(self._children.values())
   for p in children:
    if p.poll()is None:
     try:p.send_signal(signal.SIGINT)
     except ProcessLookupError:pass
   stop=time.monotonic()+8
   for p in children:
    if p.poll()is None:
     try:p.wait(timeout=max(.001,stop-time.monotonic()))
     except subprocess.TimeoutExpired:pass
   for p in children:
    if p.poll()is None:
     try:p.kill()
     except ProcessLookupError:pass
   stop=time.monotonic()+5
   for p in children:
    # Reap even if a different worker has already observed its exit.
    p.wait(timeout=max(.001,stop-time.monotonic()))
 def _reserved_deadline(self):
  value=self.deadline if self.deadline_reserver is None else self.deadline_reserver()
  require(type(value)in(int,float)and math.isfinite(value),'Finite absolute native read deadline required')
  require(value<=self.deadline,'Native reservation exceeds configured absolute deadline')
  return value
 def read(self,args,maximum):
  require(type(maximum)is int and 0<maximum<=20*1024*1024,'Invalid native read bound')
  require(args and args[0]in('cat','dump'),'Only native metadata reads allowed')
  if args[0]=='cat':require(len(args)==3 and args[1]in('tree','blob'),'Only native tree cat allowed')
  command=readonly_metadata_command(args)if self.preplan_read_only_nolock else ['restic']+args
  require(not self._cancelled.is_set(),'Native transport cancelled')
  remaining=self._reserved_deadline()-time.monotonic()
  if remaining<=0:raise TimeoutError('Native reader deadline exceeded')
  if not self._slots.acquire(timeout=remaining):raise TimeoutError('Native child slot deadline exceeded')
  reserved=False;p=None
  try:
   require(not self._cancelled.is_set(),'Native transport cancelled')
   reserved_deadline=self._reserved_deadline()
   remaining=reserved_deadline-time.monotonic()
   if remaining<=0:raise TimeoutError('Native reader deadline exceeded')
   with tempfile.TemporaryFile(dir=self.directory)as out:
    cmd=external_command(command,self.env)
    # prlimit execs restic in the SAME PID; no unsafe Python preexec_fn in threads.
    cmd=['/usr/bin/prlimit','--fsize='+str(maximum)+':'+str(maximum),'--']+cmd
    with self._lock:
     require(not self._cancelled.is_set(),'Native transport cancelled')
     require(self.calls<self.process_limit,'Native process-count bound exceeded')
     require(self.output_bytes+self._reserved+maximum<=self.byte_limit,'Native aggregate byte reservation exceeded')
     self._reserved+=maximum;reserved=True
     # Registration and spawn serialize with cancellation to avoid an unseen PID.
     p=self.popen(cmd,env=self.env,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.DEVNULL,start_new_session=True)
     self.calls+=1;self._children[p.pid]=p;self.max_live_children=max(self.max_live_children,len(self._children))
    spawned=time.monotonic();parent_deadline=reserved_deadline
    end=min(parent_deadline,spawned+35);kind=1 if spawned+35<=parent_deadline else 2
    while True:
     self._sample_rss();left=end-time.monotonic()
     if left<=0:
      with self._lock:
       if not self.timeout_diagnostic:self.timeout_diagnostic={'native_timeout_childwait_ms':max(0,int((time.monotonic()-spawned)*1000)),'native_timeout_parentremaining_ms':max(0,int((parent_deadline-spawned)*1000)),'native_timeout_deadline_kind':kind}
      raise subprocess.TimeoutExpired('reviewed-native-reader',35)
     try:code=p.wait(timeout=min(.05,left));break
     except subprocess.TimeoutExpired:continue
    require(code==0,'Native metadata command failed')
    size=out.tell();require(size<=maximum,'Native output bound exceeded')
    with self._lock:
     self._reserved-=maximum;reserved=False;self.output_bytes+=size
     require(self.output_bytes+self._reserved<=self.byte_limit,'Native aggregate byte bound exceeded')
    out.seek(0);return out.read(maximum+1)
  except BaseException:
   self.cancel_all();raise
  finally:
   # cancel_all reaps before any failed worker releases registry/slot.
   with self._lock:
    if p is not None:self._children.pop(p.pid,None)
    if reserved:self._reserved-=maximum
   self._slots.release()
