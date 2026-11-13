#!/usr/bin/env python3
"""REVIEW ONLY: serialized byte-pinned eight-source reader-controls installer; default PLAN.

No service/timer/backup/GC action. --apply requires separately reviewed package
and existing config collector coverage. Exact originals are preserved first.
"""
import argparse,base64,contextlib,datetime,fcntl,hashlib,json,os,signal,stat,subprocess,sys,tempfile,time
from pathlib import Path
LIB=Path('/usr/local/libexec');BACKUP=Path('/etc/neo/backup')
BEFORE={'neo-builder-preview-config-collect.py':'947b48f75984171df88d26ad18544b91d437d832f6664d432c682d08cff56cbc','neo-daily-backup.sh':'c20802ff9bdcf915abb882b3b13a87dd3862b71023b15d44b1d006099175a9a8','neo-hourly-online-run.py':'3d78c95a9535dba5b4c0eaca7b37d9a2116954b858f90512e2765851e0c83d18','neo-hourly-v3-config-collect.py':'947b48f75984171df88d26ad18544b91d437d832f6664d432c682d08cff56cbc','neo-hourly-v3-config-coverage.py':'dc36f83664c11599d113b13da295f610dd0a7140fe8bed42a473aa9b2a92a479','neo-hourly-v3-run.py':'03099ff16f6e6cf4c11efb29796863ac37ddff123463a09aa53176c520bca203','neo-main-preview-b2-accept.sh':'43d02440de45c3872ec3071f7b5d6a410caed0df33aa877ee8dde142b4a55167','neo-main-preview-restore-check.sh':'a04d88e3528521fd501734a717949e7e5abffda73a9d80f0d077f39574f101bb'}
AFTER={'neo-builder-preview-config-collect.py':'731d25970f1974323223bc5a4f541487d9fcc13618d9312a2b79ff09d47999e3','neo-daily-backup.sh':'99e42f49c698cecaab92b0b0917a9b45b6246c048d170c14af4a225a91525ae9','neo-hourly-online-run.py':'e257c8b498d894c8dfa745eb413996449f9d8ef8ce5a3fcefdd2a164bde88c84','neo-hourly-v3-config-collect.py':'731d25970f1974323223bc5a4f541487d9fcc13618d9312a2b79ff09d47999e3','neo-hourly-v3-config-coverage.py':'03797183187afdedd33c7882ab1f1782fff08d3ac551e7f5e8de61ed5c14d29c','neo-hourly-v3-run.py':'96b95a419894b030fce5e126b0e744e8bade1f977de08a4987886761fb676c5d','neo-main-preview-b2-accept.sh':'6185d762a15dd3f3998384d0fb1fd6dd57b10eea224c275fc0aac00babea2350','neo-main-preview-restore-check.sh':'e0a4c098f99d764ca76289460c8509a53cbdc7f5f82db2677a5fe0857dbc8691'}
LOCKS=('/var/lib/neo-b2-main-preview/collector.lock','/var/lib/neo-main-hourly/job.lock','/var/lib/neo-main-pitr/job.lock','/var/lib/neo-builder-preview-config/job.lock','/run/lock/neo-main-application-capture.lock')
UNITS=('neo-main-preview-backup','neo-main-preview-scheduled-backup','neo-main-preview-b2-accept','neo-main-hourly-files','neo-builder-preview-config-backup','neo-main-pitr-ship','neo-main-pitr-rotate','neo-main-pitr-restore-acceptance')
TIMERS=('neo-main-hourly-files','neo-main-preview-backup','neo-main-pitr-ship','neo-main-pitr-rotate')

def digest(data):return hashlib.sha256(data).hexdigest()
def need(ok,message):
 if not ok:raise ValueError(message)
def secure(path,directory=False):
 s=path.lstat();need(not path.is_symlink()and path.resolve()==path and s.st_uid==0 and not s.st_mode&0o022 and (stat.S_ISDIR(s.st_mode)if directory else stat.S_ISREG(s.st_mode)),'Untrusted root-owned path')
 return stat.S_IMODE(s.st_mode)
def atomic(path,data,mode):
 need(not path.is_symlink(),'Symlink destination refused');fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
 try:
  with os.fdopen(fd,'wb')as f:f.write(data);f.flush();os.fchmod(f.fileno(),mode);os.fsync(f.fileno())
  os.replace(name,path)
  directory_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(directory_fd)
  finally:os.close(directory_fd)
 finally:
  if os.path.exists(name):os.unlink(name)
def decoded(package):
 need(set(package)==set(AFTER),'Exact eight-source package required');out={}
 for name,value in package.items():
  data=base64.b64decode(value,validate=True);need(digest(data)==AFTER[name]and b'\r'not in data,'Candidate byte pin mismatch');out[name]=data
 return out

def idle_preflight():
 for unit in UNITS:
  state=subprocess.check_output(['systemctl','show',unit+'.service','-p','MainPID','-p','ActiveState'],text=True,timeout=5)
  p=dict(x.split('=',1)for x in state.splitlines()if'='in x)
  need(p.get('MainPID')=='0'and p.get('ActiveState')in('inactive','failed'),'Backup reader or writer active')
 for timer in TIMERS:
  text=subprocess.check_output(['systemctl','show',timer+'.timer','-p','NextElapseUSecRealtime','--value'],text=True,timeout=5).strip()
  need(bool(text)and text!='n/a','Unproved next timer boundary')
  epoch=float(subprocess.check_output(['date','-d',text,'+%s'],text=True,timeout=5))
  need(epoch-time.time()>120,'Timer too near control publication')

def coverage_required(candidates=None):
 names=set(BEFORE)|{'native-reader-enrollment.json'}
 names.update('native-reader-before-'+n+'.'+h+'.txt'for n,h in BEFORE.items())
 for collector in('neo-hourly-v3-config-collect.py','neo-builder-preview-config-collect.py'):
  text=candidates[collector].decode() if candidates is not None else (LIB/collector).read_text()
  # Conservatively require literal names; dynamic globs are not reviewed here.
  need(all(n in text for n in names),'Config capture does not cover exact enrollment and rollback set')

def replace_batch(originals,modes,candidates,rollback,receipt,*,lib=LIB,fail_after=None,deadline=None):
 """Caller holds all job/capture locks and checked idle timer window."""
 secure(rollback,directory=True);written=[]
 for name,old in originals.items():
  path=rollback/('native-reader-before-'+name+'.'+digest(old)+'.txt')
  if path.exists():need(path.read_bytes()==old,'Existing rollback differs');need(secure(path)==0o700,'Rollback mode must be700')
  else:atomic(path,old,0o700)
  need(path.read_bytes()==old,'Rollback verify failed')
 state={'scope':'native-reader-enrollment','status':'PUBLISHING','before':{n:digest(v)for n,v in originals.items()},'after':{n:digest(v)for n,v in candidates.items()},'before_modes':modes,'after_modes':{n:448 for n in candidates},'nonzero_guard_removed':False}
 atomic(receipt,(json.dumps(state,sort_keys=True)+'\n').encode(),0o600)
 try:
  for name,data in candidates.items():
   need(deadline is None or time.monotonic()<deadline,'Publication deadline exceeded')
   written.append(name);atomic(lib/name,data,0o700)
   if fail_after==len(written):raise RuntimeError('Synthetic interruption')
  need(all((lib/n).read_bytes()==v for n,v in candidates.items()),'Installed candidate readback mismatch')
  state['status']='INSTALLED';atomic(receipt,(json.dumps(state,sort_keys=True)+'\n').encode(),0o600)
 except BaseException:
  for name in reversed(written):atomic(lib/name,originals[name],modes[name])
  need(all((lib/n).read_bytes()==v for n,v in originals.items()),'Rollback readback mismatch')
  state['status']='ROLLED_BACK';atomic(receipt,(json.dumps(state,sort_keys=True)+'\n').encode(),0o600);raise
 return state

def main(package,apply=False):
 need(os.geteuid()==0,'Root only');os.umask(0o077);data=decoded(package);originals={};modes={}
 for name,expected in BEFORE.items():
  p=LIB/name;modes[name]=secure(p);originals[name]=p.read_bytes();need(digest(originals[name])==expected,'Installed source drift')
 result={'scope':'native-reader-eight-source-install-plan','byte_pins_verified':True,'idle_window_verified':False,'apply_requested':apply,'nonzero_guard_removed':False,'app_stops':0,'timers_changed':False,'backup_invoked':False}
 if not apply:return result
 secure(LIB,directory=True);secure(BACKUP,directory=True);coverage_required(data)
 with contextlib.ExitStack()as stack:
  for name in LOCKS:
   p=Path(name);fd_number=os.open(p,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC,0o600);fd=stack.enter_context(os.fdopen(fd_number,'a'));st=os.fstat(fd.fileno());need(stat.S_ISREG(st.st_mode)and st.st_uid==0 and not st.st_mode&0o022,'Untrusted lock inode');fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  idle_preflight();deadline=time.monotonic()+15
  for name,old in originals.items():need((LIB/name).read_bytes()==old,'Source changed during preflight')
  rollback=BACKUP/'rollback';secure(rollback,directory=True)
  need(time.monotonic()<deadline,'Publication deadline exceeded')
  return replace_batch(originals,modes,data,rollback,BACKUP/'native-reader-enrollment.json',deadline=deadline)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 def interrupted(*args):raise InterruptedError('Control publication interrupted')
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
 try:print(json.dumps(main(json.load(sys.stdin),args.apply),sort_keys=True))
 except Exception as error:print(json.dumps({'status':'failed','safe_exception_type':type(error).__name__}));raise SystemExit(1)
