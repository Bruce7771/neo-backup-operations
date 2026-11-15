"""REAL LOCAL restic + durable files + forced-entry subprocess JSON protocol.

Only fixed-path adapters and OS status observations are fixture-local. This is
not a production SSH/status proof. Repo/env/contents are fresh and synthetic;
no B2 credentials, application databases or provider calls are involved.
"""
import argparse,hashlib,importlib.util,json,os,pathlib,shutil,subprocess,sys,tempfile,time
HERE=pathlib.Path(__file__).parent
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=load('existing_coordinator_native_fixture',HERE/'publication-existing-coordinator.proposed.py')
g=load('gate_native_fixture',HERE/'durable-publication-hold.proposed.py')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--restic-executable',default=shutil.which('restic'));args=parser.parse_args()
 if not args.restic_executable:raise ValueError('Explicit installed restic executable required')
 restic=str(pathlib.Path(args.restic_executable).resolve(strict=True))
 if not pathlib.Path(restic).is_file() or not os.access(restic,os.X_OK):raise ValueError('Restic executable unavailable')
 with tempfile.TemporaryDirectory(prefix='neo-real-local-publication-')as td:
  root=pathlib.Path(td);repo=root/'repository';home=root/'home';home.mkdir();gate=root/'gate';gate.mkdir(mode=0o700);lib=root/'libexec';lib.mkdir(mode=0o700)
  env={'PATH':'/usr/bin:/bin','HOME':str(home),'RESTIC_REPOSITORY':str(repo),'RESTIC_PASSWORD':'LOCAL-SYNTHETIC-ONLY-NOT-A-SERVICE-KEY'}
  calls=[]
  def native(args,timeout=20):
   calls.append(tuple(args));r=subprocess.run([restic]+args,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=timeout)
   if len(r.stdout)>2*1024*1024:raise ValueError('Synthetic native output exceeded bound')
   return r.stdout
  version=native(['version']).decode();assert version.startswith('restic 0.16.4 ')
  native(['init'])
  def publish(name,payload):
   p=root/name;p.mkdir();(p/'component.json').write_text(json.dumps(payload,sort_keys=True))
   with g.Gate(gate).writer()as fd:
    result=subprocess.run([restic,'backup','--json','--host','local-main-only-publication-fixture',str(p)],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=20,pass_fds=(fd,))
   sid=[r['snapshot_id']for r in map(json.loads,result.stdout.splitlines())if r.get('message_type')=='summary'][0];return sid,p
  obsolete,_=publish('obsolete',{'synthetic':True,'revision':1});parent,_=publish('parent',{'synthetic':True,'revision':2});pre_inventory=json.loads(native(['snapshots','--json']))
  child,childpath=publish('child',{'synthetic':True,'external_parent_snapshot':parent})
  policy=root/'policy.json';policy.write_text('{"synthetic_only":true}');policy.chmod(0o600);policysha=hashlib.sha256(policy.read_bytes()).hexdigest()
  status={'local_inventory_complete':True,'source_review_integrity':True,'publication_producers_enrolled':True,'unknown_writer_units':[],'unknown_repository_clients':0,'active_known_writer_units':[],'active_known_repository_clients':0,'writer_policy_sha256':policysha}
  statusfile=lib/'neo-offsite-retention-writer-status';statusfile.write_text('import json\nprint('+repr(json.dumps(status))+')\n')
  for source,dest in [('durable-publication-hold.proposed.py','neo_publication_gate.py'),('publication-restricted-command.proposed.py','neo-publication-restricted-command.py')]:
   (lib/dest).write_bytes((HERE/source).read_bytes());(lib/dest).chmod(0o700)
  # Import the unchanged entry source, changing ONLY fixture paths/status pin.
  driver=root/'fixed-entry-driver.py';driver.write_text('''import importlib.util,pathlib,sys
s=importlib.util.spec_from_file_location('entry',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
base=pathlib.Path(sys.argv[2]);m.ROOT=base/'libexec';m.__file__=str(m.ROOT/sys.argv[3]);m.PINS['neo-offsite-retention-writer-status']=sys.argv[4]
read=m.private_read
m.private_read=lambda p,*a,**k:read(base/'policy.json'if str(p)=='/etc/neo/backup/maintenance-writer-policy.json'else p,*a,**k)
module=m.module
def mapped(name):
 d=module(name)
 if name=='neo_publication_gate.py':
  Gate=d['Gate'];d['Gate']=lambda ignored:Gate(base/'gate')
 return d
m.module=mapped;m.sys.argv=['fixed-forced-entry']
try:m.main()
except BaseException as error:print('{"ok":false,"failure_type":"'+type(error).__name__+'"}');raise SystemExit(1)
''')
  entry=HERE/'publication-ssh-entry.proposed.py';statussha=hashlib.sha256(statusfile.read_bytes()).hexdigest()
  def bounded(argv,clean,timeout,input=None):
   assert argv[:2]==['ssh','fixture-fixed-pinned-target']
   clean={'PATH':'/usr/bin:/bin','SSH_ORIGINAL_COMMAND':argv[-1]}
   return subprocess.run([sys.executable,str(driver),str(entry),str(root),'neo-offsite-retention-ssh-command',statussha],input=input,env=clean,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=timeout).stdout
  rpc=m.ExistingSSH(['ssh','fixture-fixed-pinned-target'],{'PATH':'/usr/bin:/bin'},bounded)
  assert rpc.status()['publication_producers_enrolled']
  # A readonly forced identity cannot release even an existing known HOLD.
  nonce='a'*64;rpc.acquire(nonce,policysha,120)
  denied=subprocess.run([sys.executable,str(driver),str(entry),str(root),'neo-retention-observer-ssh',statussha],input=json.dumps({'owner_nonce':nonce}).encode(),env={'PATH':'/usr/bin:/bin','SSH_ORIGINAL_COMMAND':'publication-release'},stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10)
  assert denied.returncode!=0 and g.Gate(gate).status()['held'];rpc.release(nonce)
  def candidate(ids):return {'remove_snapshot_ids':ids,'protected_snapshot_ids':[parent,child],'retained_snapshot_ids':[parent,child],'inventory_stable_for_admission':True,'apply_ready':False}
  review=lambda c:hashlib.sha256(json.dumps(sorted(c['remove_snapshot_ids'])).encode()).hexdigest()
  old=dict(candidate([obsolete,parent]),protected_snapshot_ids=[],retained_snapshot_ids=[]);current=candidate([obsolete]);before_forget=sum('forget'in args for args in calls)
  def fresh(deadline):
   assert deadline-time.monotonic()<=45
   try:
    with g.Gate(gate).writer():raise AssertionError('Publisher bypassed durable HOLD')
   except g.PublicationHeld:pass
   inventory=json.loads(native(['snapshots','--json']));assert len(inventory)==3;return current,inventory
  def forget(ids,timeout):native(['--retry-lock','0s','forget','--json']+ids,timeout)
  def post(c):
   assert not g.Gate(gate).status()['held'];native(['check']);raw=native(['dump',child,str(childpath/'component.json')]);assert json.loads(raw)['external_parent_snapshot']==parent;return {'synthetic_component_restore_verified':True}
  try:m.core.execute(old,review(old),review,policysha,rpc,fresh,forget,lambda t:json.loads(native(['snapshots','--json'],t)),post)
  except ValueError as e:assert str(e)=='Fresh removals/config require a new exact review'
  else:raise AssertionError('Stale parent deletion should have required review')
  assert sum('forget'in args for args in calls)==before_forget and not g.Gate(gate).status()['held']
  result=m.core.execute(current,review(current),review,policysha,rpc,fresh,forget,lambda t:json.loads(native(['snapshots','--json'],t)),post)
  actual=json.loads(native(['snapshots','--json']));assert {r['id']for r in actual}=={parent,child}
  print(json.dumps({'scope':'local-synthetic-native-forced-protocol-only','restic_version':'0.16.4','snapshots_created':3,'stale_preplan_native_mutation_refused':True,'observer_write_denied':True,'known_parent_retained':True,'obsolete_snapshots_forgotten':result['deleted_snapshots'],'native_integrity_and_synthetic_json_restore':True,'HOLD_released_before_postcheck':True,'repository_bytes':sum(p.stat().st_size for p in repo.rglob('*')if p.is_file()),'B2_access':False,'production_SSH_or_status_proof':False,'prune':False},sort_keys=True))

if __name__=='__main__':main()
