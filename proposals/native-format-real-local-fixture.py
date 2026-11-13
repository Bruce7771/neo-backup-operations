#!/usr/bin/env python3
"""Real local restic format/lock fixture only. Never reads Neo or cloud."""
import hashlib,json,os,pathlib,re,signal,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(tempfile.mkdtemp(prefix='neo-native-format-',dir='/var/tmp'));ROOT.chmod(0o700)
fixture=ROOT/'fixture';pg=fixture/'exact/pg/path';(pg/'base').mkdir(parents=True);(pg/'wal').mkdir()
# Empty synthetic nodes make raw tree stdout exceed PIPE capacity for lock probe.
for i in range(1100):(pg/'base'/('synthetic-'+str(i).zfill(4)+'-'+'x'*64)).touch()
metadata=['capture-result.json','postgres-point.private.json','postgres-archive-delivery.json','postgres-selfcontained/sealed-pg.json']
for name in metadata:
 p=fixture/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'synthetic':True,'role':name})+'\n')
(fixture/'not-selected.txt').write_text('synthetic excluded payload\n')
password=ROOT/'password';password.write_text('synthetic-local-format-fixture-only');password.chmod(0o600)
env={'PATH':os.environ['PATH'],'HOME':str(ROOT),'XDG_CACHE_HOME':str(ROOT/'cache'),'RESTIC_REPOSITORY':str(ROOT/'repo'),'RESTIC_PASSWORD_FILE':str(password),'LANG':'C.UTF-8'}
start=time.monotonic();timeout=65

def disk_bytes():return sum(p.stat().st_size for p in ROOT.rglob('*')if p.is_file())
def run(args,max_bytes=2*1024*1024):
 remaining=timeout-(time.monotonic()-start)
 if remaining<=0:raise TimeoutError('Synthetic fixture deadline')
 x=subprocess.run(['restic']+args,env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=min(15,remaining));assert len(x.stdout)<=max_bytes;assert disk_bytes()<=2*1024*1024;return x.stdout
version=run(['version']).decode().strip();assert version.startswith('restic 0.16.4 ')
run(['init']);summary=run(['backup','--json',str(fixture)]);sid=[json.loads(v)['snapshot_id']for v in summary.splitlines()if json.loads(v).get('message_type')=='summary'][0];assert re.fullmatch('[0-9a-f]{64}',sid)
# Chosen SID:path syntax, verified against independently reached subtree ID.
raw=run(['cat','tree',sid+':'+str(pg)]);node=json.loads(raw);assert {n['name']for n in node['nodes']}=={'base','wal'}
base_id=next(n['subtree']for n in node['nodes']if n['name']=='base');child=run(['cat','blob',base_id]);assert hashlib.sha256(child).hexdigest()==base_id;assert len(json.loads(child)['nodes'])==1100
# Resolve PG subtree from authenticated snapshot/root chains, independently.
snap=json.loads(run(['cat','snapshot',sid]));tree_id=snap['tree']
for part in pg.parts[1:]:
 tree=run(['cat','blob',tree_id]);assert hashlib.sha256(tree).hexdigest()==tree_id
 matches=[n for n in json.loads(tree)['nodes']if n['name']==part];assert len(matches)==1 and matches[0]['type']=='dir';tree_id=matches[0]['subtree']
assert hashlib.sha256(raw).hexdigest()==tree_id
# Hold a real default-SH cat process blocked on its own >pipe raw output.
blocked=subprocess.Popen(['restic','cat','blob',base_id],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
observed=False;lock_count=0
try:
 deadline=time.monotonic()+6
 while time.monotonic()<deadline:
  assert blocked.poll()is None
  ids=[s for s in run(['list','locks']).decode().splitlines()if re.fullmatch('[0-9a-f]{64}',s)]
  if ids:
   values=[json.loads(run(['cat','lock',i]))for i in ids]
   if any(v.get('exclusive')is False for v in values):observed=True;lock_count=len(ids);break
  time.sleep(.15)
 assert observed,'Default shared lock not observed'
 out,_=blocked.communicate(timeout=10);assert blocked.returncode==0 and out==child
finally:
 if blocked.poll()is None:blocked.send_signal(signal.SIGINT);blocked.communicate(timeout=8)
assert run(['list','locks']).strip()==b''
target=ROOT/'restored';args=['restore','--verify','--target',str(target),sid]
for name in metadata:args+=['--include',str(fixture/name)]
run(args);point=target/str(fixture).lstrip('/');restored=sorted(p.relative_to(point).as_posix()for p in target.rglob('*')if p.is_file());assert restored==sorted(metadata)
for name in metadata:assert (point/name).read_bytes()==(fixture/name).read_bytes()
assert run(['list','locks']).strip()==b''
proof={'schema':1,'scope':'new-synthetic-local-repository-native-format-compatibility','restic_version':version,'snapshot_synthetic':sid,'cat_tree_snapshot_absolute_path_supported':True,'cat_tree_raw_hash_equals_reached_native_tree_id':True,'cat_blob_only_reached_tree_id_raw_hash_verified':True,'real_default_shared_lock_observed':observed,'observed_own_synthetic_lock_count':lock_count,'own_lock_removed_after_completion':True,'four_exact_restore_includes_verified':True,'unselected_payload_excluded':True,'real_repository_bytes':sum(p.stat().st_size for p in (ROOT/'repo').rglob('*')if p.is_file()),'complete_fixture_bytes':disk_bytes(),'fixture_cap_bytes':2*1024*1024,'elapsed_seconds':round(time.monotonic()-start,3),'Neo_or_user_data_read':False,'cloud_access':False,'deployment_changes':False,'private_fixture_path':str(ROOT)}
(ROOT/'safe-proof.json').write_text(json.dumps(proof,sort_keys=True)+'\n');print(json.dumps(proof,sort_keys=True))
