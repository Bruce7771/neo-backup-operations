"""Bounded four-process native metadata transport, inactive candidate only."""
import os,resource,signal,subprocess,tempfile,threading,time
from pathlib import Path
from external_reader_contract import command as external_command

def require(ok,message):
 if not ok:raise ValueError(message)

class ParallelNativeCLI:
 def __init__(self,env,deadline,directory,max_live=4,process_limit=4096,byte_limit=512*1024*1024,popen=subprocess.Popen):
  require(max_live==4,'Exactly four maximum native children reviewed')
  self.env=env;self.deadline=deadline;self.directory=Path(directory);self.popen=popen
  self.max_live=max_live;self.process_limit=process_limit;self.byte_limit=byte_limit
  self.calls=0;self.output_bytes=0;self.max_live_children=0;self.peak_children_rss_kib=0
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
 def read(self,args,maximum):
  require(type(maximum)is int and 0<maximum<=20*1024*1024,'Invalid native read bound')
  require(args and args[0]in('cat','dump'),'Only native metadata reads allowed')
  if args[0]=='cat':require(len(args)==3 and args[1]in('tree','blob'),'Only native tree cat allowed')
  remaining=self.deadline-time.monotonic()
  if remaining<=0:raise TimeoutError('Native reader deadline exceeded')
  if not self._slots.acquire(timeout=remaining):raise TimeoutError('Native child slot deadline exceeded')
  reserved=False;p=None
  try:
   require(not self._cancelled.is_set(),'Native transport cancelled')
   remaining=self.deadline-time.monotonic()
   if remaining<=0:raise TimeoutError('Native reader deadline exceeded')
   with tempfile.TemporaryFile(dir=self.directory)as out:
    cmd=external_command(['restic']+args,self.env)
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
    end=min(self.deadline,time.monotonic()+35)
    while True:
     self._sample_rss();left=end-time.monotonic()
     if left<=0:raise subprocess.TimeoutExpired('reviewed-native-reader',35)
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
