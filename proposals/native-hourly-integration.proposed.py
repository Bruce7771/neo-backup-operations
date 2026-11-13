#!/usr/bin/env python3
"""UNACTIVATED integration: native locked readers + four-JSON v3 batch.

Modules are generated in a disposable engine COPY by build-native-engine.py.
No cloud call occurs on import. All subprocess output stays private/bounded.
"""
import hashlib,json,os,re,resource,shutil,signal,subprocess,tempfile,time
from pathlib import Path
from types import MappingProxyType
from hourly_metadata_batch_legacy import HourlyMetadataBatch as LegacyBatch,LIMITS,require
from native_pg_catalog_v2 import NativePGCatalog

FOUR=set(LIMITS)-{'manifest.json'}
HEX=re.compile('[0-9a-f]{64}')
def graceful_native_run(args,env,stdout,stderr,check,timeout,preexec_fn):
 process=subprocess.Popen(args,env=env,stdout=stdout,stderr=stderr,preexec_fn=preexec_fn)
 try:code=process.wait(timeout=timeout)
 except BaseException:
  # Let restic remove its OWN shared lock; never blanket-unlock repository.
  if process.poll()is None:
   process.send_signal(signal.SIGINT)
   try:process.wait(timeout=8)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
  raise
 if check and code:raise subprocess.CalledProcessError(code,args)
 return subprocess.CompletedProcess(args,code)

def native_locked_restore(args,env,deadline):
 remaining=deadline-time.monotonic()
 if remaining<=0:raise TimeoutError('Metadata restore deadline exceeded')
 def restrict():resource.setrlimit(resource.RLIMIT_FSIZE,(max(LIMITS.values()),)*2)
 graceful_native_run(args,env,subprocess.DEVNULL,subprocess.DEVNULL,True,min(40,remaining),restrict)

class BoundedNativeCLI:
 def __init__(self,env,deadline,directory,execute=graceful_native_run):
  self.env=env;self.deadline=deadline;self.directory=Path(directory);self.execute=execute
  self.calls=0;self.output_bytes=0
 def read(self,args,maximum):
  require(type(maximum)is int and 0<maximum<=20*1024*1024,'Invalid native read bound')
  remaining=self.deadline-time.monotonic()
  if remaining<=0:raise TimeoutError('Native read deadline exceeded')
  require(self.calls<4096,'Native process-count bound exceeded')
  require(args and args[0]in('cat','dump'),'Only reviewed data readers allowed')
  if args[0]=='cat':require(len(args)==3 and args[1]in('tree','blob'),'Only tree metadata cat allowed')
  self.calls+=1
  def restrict():resource.setrlimit(resource.RLIMIT_FSIZE,(maximum,maximum))
  with tempfile.TemporaryFile(dir=self.directory)as out:
   self.execute(['restic']+args,env=self.env,stdout=out,stderr=subprocess.DEVNULL,check=True,timeout=min(35,remaining),preexec_fn=restrict)
   size=out.tell();require(size<=maximum,'Native output bound exceeded');self.output_bytes+=size
   require(self.output_bytes<=512*1024*1024,'Native aggregate read bound exceeded')
   out.seek(0);return out.read(maximum+1)

class NativeHourlyMetadataBatch(LegacyBatch):
 def __init__(self,cache,env,inventory,hourly_scope,deadline,restore=None,reader=None):
  # Native restore callback keeps the original file-size/deadline enforcement.
  native=restore or native_locked_restore
  def locked_restore(args,env,deadline):
   require(args[:2]==['restic','--no-lock']or args[:2]==['restic','restore'],'Unexpected native restore prefix')
   return native([a for a in args if a!='--no-lock'],env,deadline)
  super().__init__(cache,env,inventory,hourly_scope,deadline,locked_restore)
  self.reader=reader or BoundedNativeCLI(env,deadline,self.cache)
  self._memo=None;self._memo_sid=None;self._origins={}
  self.stats.update(memory_payload_hits=0,native_v3_four_json_points=0,legacy_full_manifest_points=0)
  self.catalog=NativePGCatalog(self.binding,hourly_scope,inventory,
    lambda sid,path:self.reader.read(['cat','tree',sid+':'+path],8*1024*1024),
    lambda tree:self.reader.read(['cat','blob',tree],8*1024*1024),deadline,
    authenticated_file_origin=self.assert_native_origin)
 def assert_native_origin(self,sid,path,raw):
  # Receipt is established ONLY after exact-snapshot native restore --verify.
  require(self._origins.get((sid,path))==(len(raw),hashlib.sha256(raw).hexdigest()),'Missing exact-snapshot native file provenance')
  return True
 def _four(self,snapshot):
  scratch=Path(tempfile.mkdtemp(prefix='.v3-four-native-',dir=self.cache));scratch.chmod(0o700)
  try:
   command=['restic','restore','--verify','--target',str(scratch),snapshot]
   for name in sorted(FOUR):command+=['--include',self.root+'/'+name]
   self.restore(command,self.env,self.deadline);self.stats['native_batches']+=1
   point=scratch/self.root.lstrip('/');payload={}
   for p in scratch.rglob('*'):
    require(not p.is_symlink()and(p.is_file()or p.is_dir()),'Unsafe restored metadata node')
    if p.is_file():
     require(p.is_relative_to(point),'Metadata outside exact hourly root');name=p.relative_to(point).as_posix()
     require(name in FOUR and p.stat().st_size<=LIMITS[name],'Unexpected or oversize selected metadata');payload[name]=p.read_bytes()
   self.stats['selected_json_bytes']+=sum(map(len,payload.values()))
   require(self.stats['selected_json_bytes']<=256*1024*1024,'Selected JSON aggregate bound exceeded')
   delivery=json.loads(payload.get('postgres-archive-delivery.json',b'{}'))
   if delivery.get('schema')!=3:return None
   require(set(payload)==FOUR,'V3 requires exactly four selected metadata JSON files')
   for raw in payload.values():json.loads(raw)
   require(delivery.get('sealed_pg_sha256')==hashlib.sha256(payload['postgres-selfcontained/sealed-pg.json']).hexdigest(),'V3 seal fingerprint differs')
   self._origins={(snapshot,self.root+'/'+name):(len(raw),hashlib.sha256(raw).hexdigest())for name,raw in payload.items()}
   self.stats['native_v3_four_json_points']+=1
   return payload
  finally:shutil.rmtree(scratch)
 def _fetch(self,snapshot):
  if self._memo_sid==snapshot:
   self.stats['memory_payload_hits']+=1;return self._memo
  self._origins={};payload=self._four(snapshot)
  if payload is None:
   # The original legacy validator/checkpoint behavior is preserved exactly.
   payload=super()._fetch(snapshot);self.stats['legacy_full_manifest_points']+=1
   require(self.stats['selected_json_bytes']<=256*1024*1024,'Selected JSON aggregate bound exceeded')
  self._memo_sid=snapshot;self._memo=MappingProxyType(dict(payload));return self._memo
 def get(self,snapshot,path,maximum):
  # UNKNOWN's original exact archived manifest remains available, not projected.
  if path==self.root+'/manifest.json':
   require(snapshot in self.authorized,'Snapshot outside metadata scope')
   return self.reader.read(['dump',snapshot,path],maximum)
  return super().get(snapshot,path,maximum)
 def verify_catalog(self,sid,root,files,sealed_raw):
  require(root==self.root and sid in self.authorized,'Catalog outside exact scope')
  result=self.catalog.verify(sid,files,sealed_raw,
      lambda snapshot,path:self.reader.read(['dump',snapshot,path],8*1024*1024))
  self.stats.update({'catalog_'+k:v for k,v in self.catalog.stats.items()})
  self.stats['catalog_cli_processes']=self.reader.calls;self.stats['catalog_cli_selected_bytes']=self.reader.output_bytes
  return result
