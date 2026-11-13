#!/usr/bin/env python3
"""LOCAL synthetic cancellation observation; not GC timeout authority."""
import hashlib,json,os,select,shutil,signal,socket,subprocess,tempfile,time
from pathlib import Path

def main():
 with tempfile.TemporaryDirectory(prefix='neo-native-cancel-',dir='/var/tmp')as temp:
  root=Path(temp);root.chmod(0o700)
  if shutil.disk_usage(root).free<2_064_000_000:raise RuntimeError('Fixture reserve unavailable')
  password=root/'password';password.write_text('synthetic-only');password.chmod(0o600)
  data=root/'fixture.bin';data.write_bytes(os.urandom(4*1024*1024))
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(root),'RESTIC_REPOSITORY':str(root/'repo'),'RESTIC_PASSWORD_FILE':str(password)}
  def run(args):return subprocess.run(['/usr/bin/restic',*args],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=15).stdout
  if not run(['version']).startswith(b'restic 0.16.4 '):raise RuntimeError('Wrong fixture version')
  run(['init']);snapshot=next(json.loads(x)['snapshot_id']for x in run(['backup','--json',str(data)]).splitlines()if json.loads(x).get('message_type')=='summary')
  result=[]
  for sig in(signal.SIGINT,signal.SIGKILL):
   if run(['--no-lock','list','locks']).splitlines():raise RuntimeError('Fixture baseline not empty')
   p=subprocess.Popen(['/usr/bin/restic','dump',snapshot,str(data)],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
   try:
    if not select.select([p.stdout],[],[],5)[0]or p.poll()is not None:raise RuntimeError('Native reader not held')
    locks=run(['--no-lock','list','locks']).splitlines()
    if len(locks)!=1:raise RuntimeError('Not exactly own fixture lock')
    own=json.loads(run(['--no-lock','cat','lock',locks[0].decode()]))
    if own['pid']!=p.pid or own['hostname']!=socket.gethostname():raise RuntimeError('Lock ownership mismatch')
    start=time.monotonic();p.send_signal(sig)
    try:p.wait(5);forced=False
    except subprocess.TimeoutExpired:p.kill();p.wait(3);forced=True
    after=run(['--no-lock','list','locks']).splitlines();cleaned=not after
    if after:
     # Exact-repository local fixture only. Unknown additional locks forbid unlock.
     if after!=locks:raise RuntimeError('Unknown lock: no cleanup authority')
     again=json.loads(run(['--no-lock','cat','lock',after[0].decode()]))
     if again!=own:raise RuntimeError('Lock mutated: no cleanup authority')
     run(['unlock'])
     if run(['--no-lock','list','locks']).splitlines():raise RuntimeError('Native cleanup left own lock')
    result.append({'signal':sig.name,'reaped':True,'forced_after_five_seconds':forced,'native_lock_cleaned_without_unlock':cleaned,'own_lock_only_guard_passed':True,'native_unlock_cleaned_remaining':bool(after),'elapsed_seconds':round(time.monotonic()-start,6)})
   finally:
    if p.poll()is None:p.kill();p.wait(3)
    p.stdout.close()
  print(json.dumps({'scope':'local-native-dump-cancellation-observation','observations':result,'prune_midoperation_cancellation_proved':False,'cloud_calls':0,'real_repository_mutations':0}))
if __name__=='__main__':main()
