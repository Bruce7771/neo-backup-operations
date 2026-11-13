"""Bounded read-only hourly JSON fetch with private per-point checkpoints.

No SQLite/media/base/WAL payload is selected. Exact marker WAL and physical base
manifest remain separately bounded/authenticated by the existing derivation.
Cache lives only in private RUNNER_TEMP; no artifact/cache publication is used.
"""
import hashlib,json,os,re,resource,shutil,stat,subprocess,tempfile,time
from pathlib import Path

LIMITS={'manifest.json':8*1024*1024,'capture-result.json':1024*1024,
        'postgres-point.private.json':1024*1024,'postgres-archive-delivery.json':1024*1024,
        'postgres-selfcontained/sealed-pg.json':8*1024*1024}

def require(ok,reason):
    if not ok:raise ValueError(reason)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def private_directory(path):
    path=Path(path)
    require(not path.is_symlink(),'Unsafe private metadata directory')
    path.mkdir(mode=0o700,parents=False,exist_ok=True)
    info=path.stat()
    require(stat.S_ISDIR(info.st_mode)and info.st_uid==os.geteuid()and stat.S_IMODE(info.st_mode)==0o700,
            'Metadata cache must be private to the runner')
    return path

def native_restore(command,env,deadline):
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('Hourly metadata audit exceeded its read-only deadline')
    def restrict():resource.setrlimit(resource.RLIMIT_FSIZE,(max(LIMITS.values()),)*2)
    subprocess.run(command,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                   check=True,timeout=min(40,remaining),preexec_fn=restrict)

class HourlyMetadataBatch:
    def __init__(self,cache,env,inventory,hourly_scope,deadline,restore=native_restore):
        self.cache=private_directory(cache);self.env=env;self.deadline=deadline;self.restore=restore
        self.root=hourly_scope['paths'][0].rstrip('/')
        require(len(hourly_scope['paths'])==1 and re.fullmatch('/[A-Za-z0-9_/-]+',self.root)is not None
                and '..'not in self.root.split('/')and'//'not in self.root,'Unsafe hourly metadata root')
        self.authorized={row['id']for row in inventory if row.get('hostname')==hourly_scope['host']
            and hourly_scope['tag']in row.get('tags',[])and row.get('paths')==hourly_scope['paths']}
        require(all(re.fullmatch('[0-9a-f]{64}',sid)is not None for sid in self.authorized),'Invalid authorized snapshot')
        self.binding=digest(json.dumps({'repository':env['RESTIC_REPOSITORY'],'scope':hourly_scope},sort_keys=True).encode())
        self.stats={'native_batches':0,'checkpoint_reads':0,'selected_json_bytes':0,'v3_points_authenticated':0}
        self._seen_v3=set()

    def _key(self,snapshot):return digest((self.binding+'\0'+snapshot).encode())

    def _validate(self,payload):
        require('manifest.json'in payload,'Hourly manifest was not fetched')
        rows=json.loads(payload['manifest.json']);require(isinstance(rows,list),'Invalid hourly manifest')
        by={}
        for row in rows:
            name=row['path']
            require(isinstance(name,str)and name and not name.startswith('/')and'..'not in name.split('/')
                    and'\\'not in name and name not in by,'Unsafe/duplicate hourly manifest entry')
            require(type(row['bytes'])is int and row['bytes']>=0 and re.fullmatch('[0-9a-f]{64}',row['sha256'])is not None,
                    'Invalid hourly manifest size/hash')
            by[name]=row
        for name,raw in payload.items():
            require(name in LIMITS and len(raw)<=LIMITS[name],'Unexpected/oversize metadata payload')
            json.loads(raw)
            if name!='manifest.json':
                require(name in by and by[name]['bytes']==len(raw)and by[name]['sha256']==digest(raw),
                        'Hourly metadata fingerprint differs from manifest')
        delivery=json.loads(payload.get('postgres-archive-delivery.json',b'{}'))
        if delivery.get('schema')==3:
            require(set(payload)==set(LIMITS),'V3 metadata must contain exactly five selected JSON files')
            require(delivery.get('sealed_pg_sha256')==digest(payload['postgres-selfcontained/sealed-pg.json']),
                    'V3 PG seal fingerprint differs')
        else:
            require('postgres-selfcontained/sealed-pg.json'not in payload,'Unexpected PG seal in non-v3 metadata')
        return payload

    def _read(self,path,snapshot):
        require(not path.is_symlink()and path.is_dir(),'Unsafe metadata checkpoint')
        record_path=path/'record.json'
        require(record_path.is_file()and not record_path.is_symlink(),'Incomplete metadata checkpoint')
        require(record_path.stat().st_size<=16384,'Oversize metadata checkpoint record')
        record=json.loads(record_path.read_text())
        require(record.get('schema')==1 and record.get('binding')==self.binding
                and record.get('snapshot')==snapshot and record.get('root')==self.root,'Cross-point metadata cache mismatch')
        entries=record.get('files',{})
        require(isinstance(entries,dict)and set(entries)<=set(LIMITS),'Invalid metadata cache inventory')
        allowed={'record.json'}|{self._filename(name)for name in entries}
        require(set(p.name for p in path.iterdir())==allowed,'Unexpected metadata checkpoint node')
        payload={}
        for name,entry in entries.items():
            p=path/self._filename(name)
            require(p.is_file()and not p.is_symlink()and p.stat().st_size<=LIMITS[name],'Unsafe/oversize cached JSON')
            raw=p.read_bytes();require(entry=={'bytes':len(raw),'sha256':digest(raw)},'Cached metadata fingerprint differs')
            payload[name]=raw
        return self._validate(payload)

    @staticmethod
    def _filename(name):return digest(name.encode())+'.json'

    def _fetch(self,snapshot):
        destination=self.cache/self._key(snapshot)
        if destination.exists():
            self.stats['checkpoint_reads']+=1
            return self._read(destination,snapshot)
        scratch=Path(tempfile.mkdtemp(prefix='.metadata-download-',dir=self.cache));scratch.chmod(0o700)
        checkpoint=None
        try:
            command=['restic','--no-lock','restore','--verify','--target',str(scratch),snapshot]
            # One native call selects at most five fixed JSON paths. A v2 point
            # has four; the v3-only include matches nothing there. No glob or
            # parent-directory include can select application data.
            for name in LIMITS:command+=['--include',self.root+'/'+name]
            self.restore(command,self.env,self.deadline)
            self.stats['native_batches']+=1
            point=scratch/self.root.lstrip('/');payload={}
            for p in scratch.rglob('*'):
                require(not p.is_symlink()and(p.is_file()or p.is_dir()),'Unsafe restored metadata node')
                if p.is_file():
                    require(p.is_relative_to(point),'Restored metadata outside exact hourly root')
                    name=p.relative_to(point).as_posix()
                    require(name in LIMITS and p.stat().st_size<=LIMITS[name],'Unexpected/oversize restored metadata')
                    payload[name]=p.read_bytes()
            self._validate(payload)
            self.stats['selected_json_bytes']+=sum(len(raw)for raw in payload.values())
            checkpoint=Path(tempfile.mkdtemp(prefix='.metadata-checkpoint-',dir=self.cache));checkpoint.chmod(0o700)
            record={'schema':1,'binding':self.binding,'snapshot':snapshot,'root':self.root,'files':{}}
            for name,raw in payload.items():
                with(checkpoint/self._filename(name)).open('xb')as stream:
                    os.fchmod(stream.fileno(),0o600);stream.write(raw);stream.flush();os.fsync(stream.fileno())
                record['files'][name]={'bytes':len(raw),'sha256':digest(raw)}
            with(checkpoint/'record.json').open('x')as stream:
                os.fchmod(stream.fileno(),0o600);json.dump(record,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())
            fd=os.open(checkpoint,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
            checkpoint.rename(destination);checkpoint=None
            fd=os.open(self.cache,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
            return self._read(destination,snapshot)
        finally:
            shutil.rmtree(scratch)
            if checkpoint is not None:shutil.rmtree(checkpoint)

    def get(self,snapshot,path,maximum):
        require(snapshot in self.authorized and re.fullmatch('[0-9a-f]{64}',snapshot)is not None,'Snapshot outside hourly metadata scope')
        prefix=self.root+'/'
        require(path.startswith(prefix)and path[len(prefix):]in LIMITS,'Path outside exact metadata allowlist')
        if time.monotonic()>=self.deadline:raise TimeoutError('Hourly metadata audit exceeded its read-only deadline')
        name=path[len(prefix):];payload=self._fetch(snapshot)
        if json.loads(payload.get('postgres-archive-delivery.json',b'{}')).get('schema')==3 and snapshot not in self._seen_v3:
            self._seen_v3.add(snapshot);self.stats['v3_points_authenticated']+=1
        if name not in payload:raise FileNotFoundError('Required hourly archive metadata absent')
        require(type(maximum)is int and maximum>=0 and len(payload[name])<=maximum,'Archive read exceeds reviewed size bound')
        return payload[name]

    def handles(self,snapshot,path):
        return snapshot in self.authorized and path.startswith(self.root+'/')and path[len(self.root)+1:]in LIMITS
