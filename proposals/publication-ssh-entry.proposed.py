#!/usr/bin/python3 -I
"""Inactive forced-command entry for EXISTING observer/maintenance SSH keys.

Install reviewed byte-identical root-owned copies at the two exact entry paths.
The SSH authorized_keys forced command selects identity; remote argv cannot.
No key installation, native B2 commands, service control or automatic reconcile.
"""
import hashlib,json,os,pathlib,signal,stat,subprocess,sys
ROOT=pathlib.Path('/usr/local/libexec')
PINS={
 'neo_publication_gate.py':'c308a50618084d30fbe5734bd27be9fc2fb2c63f051bd23f9bbc8b6d511c6e41',
 'neo-publication-restricted-command.py':'ab10bd773bbb9a723c7c6267e0533e14b051c87865a7f205bf6d45637c034c0c',
 'neo-offsite-retention-writer-status':'cb633f2660c76d89b0fcc8d2f1e6ec7df99de3b75a3bf75890b6af34e374d81d'}

def require(value,message):
 if not value:raise ValueError(message)

def private_read(path,mode=None,limit=1024*1024):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb')as f:
  st=os.fstat(f.fileno());require(stat.S_ISREG(st.st_mode)and st.st_uid==0 and not st.st_mode&0o022 and st.st_nlink==1 and st.st_size<=limit,'Untrusted reviewed file')
  require(mode is None or stat.S_IMODE(st.st_mode)==mode,'Private file mode required');raw=f.read(limit+1);after=os.fstat(f.fileno())
  require(len(raw)<=limit and (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'Review file changed')
 return raw

def module(name):
 path=ROOT/name;raw=private_read(path);require(hashlib.sha256(raw).hexdigest()==PINS[name],'Reviewed helper changed');namespace={'__name__':'neo_forced_helper'};exec(compile(raw,str(path),'exec'),namespace);return namespace

def entry_identity(path):
 require(path.parent==ROOT and not path.is_symlink(),'Fixed forced-command path required')
 require(path.name in('neo-retention-observer-ssh','neo-retention-maintenance-ssh','neo-offsite-retention-ssh-command'),'Unsupported forced entry')
 return path.name in('neo-retention-maintenance-ssh','neo-offsite-retention-ssh-command')

def main():
 require(os.geteuid()==0 and len(sys.argv)==1,'Fixed root forced entry required');maintenance=entry_identity(pathlib.Path(__file__))
 command=os.environ.get('SSH_ORIGINAL_COMMAND','');require(command in('status','writer-status','publication-acquire','publication-begin-forget','publication-acknowledge','publication-release'),'Unsupported literal command')
 legacy_status=command=='status'
 if legacy_status:command='writer-status'
 # Reject mutation before loading gate/policy or invoking any process.
 require(command=='writer-status'or maintenance,'Observer key is read-only')
 def expired(signum,frame):raise TimeoutError('Bounded request deadline')
 previous=signal.signal(signal.SIGALRM,expired);signal.alarm(5)
 try:raw=sys.stdin.buffer.read(8193)
 finally:signal.alarm(0);signal.signal(signal.SIGALRM,previous)
 require(len(raw)<=8192,'Bounded request required');body={}if legacy_status and not raw.strip()else json.loads(raw)
 policy=private_read(pathlib.Path('/etc/neo/backup/maintenance-writer-policy.json'),mode=0o600,limit=262144);policy_sha=hashlib.sha256(policy).hexdigest()
 def status():
  # Verify bytes immediately before the fixed Python invocation. Root controls
  # this source directory; caller input never becomes argv or environment.
  name='neo-offsite-retention-writer-status';require(hashlib.sha256(private_read(ROOT/name)).hexdigest()==PINS[name],'Status source changed')
  result=subprocess.run(['/usr/bin/python3','-I','-B',str(ROOT/name)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=12,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},check=True)
  require(len(result.stdout)<=65536,'Bounded status required');return json.loads(result.stdout)
 dispatch=module('neo-publication-restricted-command.py')['dispatch']
 if command=='writer-status':gate=None
 else:gate=module('neo_publication_gate.py')['Gate']('/var/lib/neo-backup-publication')
 result=dispatch(command,body,gate,status,policy_sha,maintenance_identity=maintenance)
 sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'))+'\n')

if __name__=='__main__':
 try:main()
 except BaseException as error:
  # No exception messages, request fields, owner nonce, stdout body or argv.
  sys.stdout.write(json.dumps({'ok':False,'failure_type':type(error).__name__})+'\n');raise SystemExit(1)
