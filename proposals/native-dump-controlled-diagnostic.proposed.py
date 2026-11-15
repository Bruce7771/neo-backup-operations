"""Manual-only controlled native-dump diagnostic; normal retention limits unchanged."""
import os,re,signal,stat,subprocess,tempfile,time
from pathlib import Path
HEX=re.compile('[0-9a-f]{64}')
def need(ok,msg):
 if not ok:raise ValueError(msg)
def path_kind(path):
 if path.endswith('/base/backup_manifest'):return 'postgres-base-manifest'
 if path.endswith('/manifest.json'):return 'hourly-outer-manifest'
 if re.search('/wal/[0-9A-F]{24}\\.gz$',path):return 'postgres-wal-archive'
 return 'other-reviewed-metadata'
def cache_stats(root,max_files=4096,max_dirs=1024):
 """Metadata only; bounded scan, no file contents/names returned."""
 result={'files':0,'bytes':0,'directories':0,'capped':False,'invalid':False}
 if not root.exists():return result
 if root.is_symlink()or not root.is_dir():result['invalid']=True;return result
 pending=[root];until=time.monotonic()+.025
 while pending:
  if result['directories']>=max_dirs or time.monotonic()>=until:result['capped']=True;break
  p=pending.pop();result['directories']+=1
  try:
   with os.scandir(p)as entries:
    for e in entries:
     if result['files']>=max_files or time.monotonic()>=until:result['capped']=True;return result
     info=e.stat(follow_symlinks=False)
     if stat.S_ISLNK(info.st_mode):result['invalid']=True;continue
     if stat.S_ISDIR(info.st_mode):pending.append(Path(e.path))
     elif stat.S_ISREG(info.st_mode):result['files']+=1;result['bytes']+=info.st_size
  except (FileNotFoundError,PermissionError):result['invalid']=True
 return result
def rss_kib(pid):
 try:
  for line in Path('/proc',str(pid),'status').read_text().splitlines():
   if line.startswith('VmRSS:'):return int(line.split()[1])
 except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 return 0
def valid(proof):
 keys={'schema','command_kind','snapshot','path_kind','expected_max_bytes','timeout_milliseconds','elapsed_milliseconds','stdout_bytes','peak_rss_kib','cache_before','cache_after','samples','timed_out','exit_code','own_child_reaped','cache_diagnostics_bounded','first_stdout_observed_ms','stderr_static_codes'}
 need(isinstance(proof,dict)and set(proof)==keys,'Invalid native dump diagnostic fields')
 need(proof['schema']==1 and proof['command_kind']=='restic-dump'and isinstance(proof['snapshot'],str)and HEX.fullmatch(proof['snapshot']),'Invalid native dump diagnostic identity')
 need(proof['path_kind']in('postgres-base-manifest','hourly-outer-manifest','postgres-wal-archive','other-reviewed-metadata'),'Invalid native dump path class')
 for key in('expected_max_bytes','timeout_milliseconds','elapsed_milliseconds','stdout_bytes','peak_rss_kib'):need(type(proof[key])is int and 0<=proof[key]<=2**40,'Invalid native dump numeric diagnostic')
 need(proof['expected_max_bytes']<=20*1024*1024 and proof['timeout_milliseconds']<=90000,'Native dump bound increased')
 for key in('timed_out','own_child_reaped','cache_diagnostics_bounded'):need(type(proof[key])is bool,'Invalid native dump boolean')
 need(proof['exit_code']is None or type(proof['exit_code'])is int and -256<=proof['exit_code']<=256,'Invalid native dump exit code')
 for key in('cache_before','cache_after'):
  row=proof[key];need(isinstance(row,dict)and set(row)=={'files','bytes','directories','capped','invalid'},'Invalid cache diagnostic')
  need(all(type(row[k])is int and 0<=row[k]<=2**50 for k in('files','bytes','directories'))and all(type(row[k])is bool for k in('capped','invalid')),'Invalid cache numeric diagnostic')
 need(isinstance(proof['samples'],list)and len(proof['samples'])<=256,'Oversize native dump progress')
 for row in proof['samples']:need(isinstance(row,dict)and set(row)=={'elapsed_milliseconds','stdout_bytes','rss_kib'}and all(type(n)is int and 0<=n<=2**40 for n in row.values()),'Invalid native dump sample')
 need(proof['first_stdout_observed_ms'] is None or(type(proof['first_stdout_observed_ms'])is int and proof['first_stdout_observed_ms']>=0),'Invalid first stdout timing')
 need(isinstance(proof['stderr_static_codes'],list)and all(x in ('AccessDenied','InvalidAccessKeyId','SignatureDoesNotMatch','ExpiredToken','SlowDown','ServiceUnavailable','RequestTimeout','TooManyRequests','NoSuchKey')for x in proof['stderr_static_codes']),'Invalid static error codes')
 return True

def diagnostic_dump(command,env,work,maximum,timeout,job_deadline,sink,popen=subprocess.Popen,poll_seconds=.1,sample_seconds=.5):
 args=list(command);need(args and args[0]=='restic','Native dump command required');tail=[a for a in args[1:]if a!='--no-lock'];need(len(tail)==3 and tail[0]=='dump'and HEX.fullmatch(tail[1]),'Exact native dump only');snapshot,path=tail[1:];need(isinstance(path,str)and path.startswith('/')and'..'not in path.split('/'),'Invalid reviewed dump path')
 need(type(maximum)is int and 0<maximum<=20*1024*1024 and type(timeout)in(int,float)and 0<timeout<=90,'Native dump bound increased')
 start=time.monotonic();operation_end=min(start+timeout,job_deadline);need(operation_end>start,'Native dump has no remaining job budget')
 cache=Path(env.get('XDG_CACHE_HOME',str(Path(work)/'cache')));need(cache.is_relative_to(Path(work)),'Cache diagnostic outside private work')
 before=cache_stats(cache);samples=[];peak=0;last=-1.;child=None;timed_out=False;code=None;failure=None;stdout_bytes=0;first_stdout=None;static_codes=[]
 with tempfile.TemporaryFile(dir=work)as output,tempfile.TemporaryFile(dir=work)as errors:
  try:
   # prlimit execs native CLI in the same owned PID; stderr is never retained.
   child=popen(['/usr/bin/prlimit','--fsize='+str(maximum)+':'+str(maximum),'--']+args,env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=errors,start_new_session=True)
   while True:
    now=time.monotonic();stdout_bytes=os.fstat(output.fileno()).st_size
    if stdout_bytes and first_stdout is None:first_stdout=int((now-start)*1000)
    rss=rss_kib(child.pid);peak=max(peak,rss)
    if now-last>=sample_seconds and len(samples)<256:samples.append({'elapsed_milliseconds':int((now-start)*1000),'stdout_bytes':stdout_bytes,'rss_kib':rss});last=now
    code=child.poll()
    if code is not None:break
    if now>=operation_end:timed_out=True;raise subprocess.TimeoutExpired('reviewed-native-dump',timeout)
    time.sleep(min(poll_seconds,operation_end-now))
   need(stdout_bytes<=maximum,'Native dump output exceeds bound')
   if code:raise subprocess.CalledProcessError(code,'reviewed-native-dump')
  except BaseException as e:failure=e
  finally:
   if child is not None:
    if child.poll()is None:
     try:child.send_signal(signal.SIGINT)
     except ProcessLookupError:pass
     grace=max(.001,min(3,job_deadline-time.monotonic()))
     try:child.wait(timeout=grace)
     except subprocess.TimeoutExpired:child.kill();child.wait(timeout=max(.001,min(2,job_deadline-time.monotonic())))
    else:child.wait(timeout=.001)
    code=child.returncode
   stdout_bytes=os.fstat(output.fileno()).st_size
   errors.seek(0);error_text=errors.read(16384).decode('utf-8',errors='replace')
   static_codes=[x for x in ('AccessDenied','InvalidAccessKeyId','SignatureDoesNotMatch','ExpiredToken','SlowDown','ServiceUnavailable','RequestTimeout','TooManyRequests','NoSuchKey')if re.search(r'\b'+x+r'\b',error_text)]
   proof={'schema':1,'first_stdout_observed_ms':first_stdout,'stderr_static_codes':static_codes,'command_kind':'restic-dump','snapshot':snapshot,'path_kind':path_kind(path),'expected_max_bytes':maximum,'timeout_milliseconds':int(timeout*1000),'elapsed_milliseconds':int((time.monotonic()-start)*1000),'stdout_bytes':stdout_bytes,'peak_rss_kib':peak,'cache_before':before,'cache_after':cache_stats(cache),'samples':samples,'timed_out':timed_out,'exit_code':code,'own_child_reaped':child is not None and child.poll()is not None,'cache_diagnostics_bounded':True}
   valid(proof);sink(proof)
  if failure is not None:raise failure
  output.seek(0);return output.read(maximum+1)