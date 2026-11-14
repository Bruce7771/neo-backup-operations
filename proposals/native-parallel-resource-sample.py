#!/usr/bin/env python3
"""Real four-reader RSS/CPU-affinity sample, NEW <=2MiB dummy local repo."""
import hashlib,importlib.util,json,os,resource,subprocess,sys,tempfile,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE=Path(__file__).parent

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
mem={}
for line in Path('/proc/meminfo').read_text().splitlines():
 if line.startswith('MemAvailable:'):mem['available_kib']=int(line.split()[1])
assert mem['available_kib']>=1024*1024,'Local synthetic resource admission requires >=1GiB available'
original_affinity=os.sched_getaffinity(0);os.sched_setaffinity(0,set(sorted(original_affinity)[:2]));start=time.monotonic()
try:
 with tempfile.TemporaryDirectory(prefix='neo-parallel-native-resource-')as tmp:
  root=Path(tmp);root.chmod(0o700);engine=load('builder',HERE/'build-native-parallel-engine.proposed.py').build(HERE.parent/'scripts',root/'engine');sys.path.insert(0,str(engine));from native_parallel_transport import ParallelNativeCLI
  fixture=root/'fixture';fixture.mkdir();(fixture/'empty-one').touch();(fixture/'empty-two').touch();password=root/'password';password.write_text('synthetic-four-native-readers-only');password.chmod(0o600)
  env={'PATH':os.environ['PATH'],'HOME':str(root),'XDG_CACHE_HOME':str(root/'cache'),'RESTIC_REPOSITORY':str(root/'repo'),'RESTIC_PASSWORD_FILE':str(password),'LANG':'C.UTF-8'}
  def native(args):
   p=subprocess.run(['restic']+args,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=20);assert len(p.stdout)<=2*1024*1024;assert sum(p.stat().st_size for p in (root/'repo').rglob('*')if p.is_file())<=2*1024*1024;return p.stdout
  version=native(['version']).decode().strip();assert version.startswith('restic 0.16.4 ');native(['init']);raw=native(['backup','--json',str(fixture)]);sid=[json.loads(x)['snapshot_id']for x in raw.splitlines()if json.loads(x).get('message_type')=='summary'][0]
  tree=native(['cat','tree',sid+':'+str(fixture)]);tree_id=hashlib.sha256(tree).hexdigest();transport=ParallelNativeCLI(env,time.monotonic()+30,root)
  with ThreadPoolExecutor(max_workers=4)as pool:outputs=list(pool.map(lambda _:transport.read(['cat','blob',tree_id],1024*1024),range(4)))
  assert all(hashlib.sha256(x).hexdigest()==tree_id for x in outputs);assert transport.max_live_children==4;assert not transport._children and transport._reserved==0;assert native(['list','locks']).strip()==b''
  proof={'schema':1,'scope':'actual-four-native-readers-small-local-repository-resource-sample','restic_version':version,'own_process_cpu_affinity_count':len(os.sched_getaffinity(0)),'actual_max_live_native_children':transport.max_live_children,'sampled_peak_aggregate_own_children_RSS_KiB':transport.peak_children_rss_kib,'measured_parent_peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'native_output_bytes':transport.output_bytes,'native_processes':transport.calls,'elapsed_seconds':round(time.monotonic()-start,3),'all_four_raw_hashes_verified':True,'all_own_children_reaped':True,'own_native_locks_remaining':0,'repository_bytes':sum(p.stat().st_size for p in (root/'repo').rglob('*')if p.is_file()),'local_repository_cap_bytes':2097152,'dummy_environment_only':True,'cloud_or_Neo_data_read':False,'workflow_or_runner_configuration_changed':False,'limitation':'Small local repository sample, not real B2 index memory or current-volume latency acceptance'}
  print(json.dumps(proof,sort_keys=True))
finally:os.sched_setaffinity(0,original_affinity)
