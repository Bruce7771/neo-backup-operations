"""Authenticate v3 embedded recovery metadata; never declares a physical replay."""
import gzip,hashlib,io,json,re

def require(ok,message):
    if not ok:raise ValueError(message)

def derive_v3(sid,root,capture_raw,delivery_raw,marker_raw,accepted_bases,dump):
    delivery=json.loads(delivery_raw);marker=json.loads(marker_raw)
    sealed_raw=dump(sid,root+'/postgres-selfcontained/sealed-pg.json',8*1024*1024)
    require(hashlib.sha256(sealed_raw).hexdigest()==delivery.get('sealed_pg_sha256'),'V3 PG seal fingerprint differs')
    sealed=json.loads(sealed_raw)
    require(sealed.get('schema')==3 and sealed.get('scope')=='main-neo-builder-physical-postgres-selfcontained'
            and sealed.get('external_parent_dependency')is None and 'wal_snapshot'not in delivery
            and delivery.get('external_parent_dependency')is None,'V3 must not have a cloud parent dependency')
    require(delivery.get('postgres_recovery_included')is True,'V3 embedded recovery scope missing')
    for name in('restore_point','wal_segment','wal_lsn'):
        require(sealed.get(name)==marker.get(name),'V3 sealed marker differs')
    require(delivery.get('marker_restore_point')==marker.get('restore_point')and delivery.get('wal_segment')==marker.get('wal_segment'),'V3 delivery marker differs')
    require(re.fullmatch('neo_hourly_[0-9]+_[0-9a-f]{8}',marker.get('restore_point',''))is not None,'V3 invalid named point')
    segment=marker.get('wal_segment','');require(re.fullmatch('[0-9A-F]{24}',segment)is not None,'V3 invalid WAL name')
    outer_raw=dump(sid,root+'/manifest.json',8*1024*1024);outer=json.loads(outer_raw)
    outer_by={row['path']:row for row in outer};require(len(outer_by)==len(outer),'V3 duplicate manifest path')
    seal_row=outer_by.get('postgres-selfcontained/sealed-pg.json',{})
    require(seal_row.get('sha256')==hashlib.sha256(sealed_raw).hexdigest()and seal_row.get('bytes')==len(sealed_raw),'V3 seal not bound by outer manifest')
    files=sealed.get('files',[]);require(files and len({row['path']for row in files})==len(files),'V3 empty/duplicate PG files')
    for row in files:
        name=row['path'];require(not name.startswith('/')and'..'not in name.split('/'),'V3 unsafe relative path')
        require(outer_by.get('postgres-selfcontained/'+name)==dict(row,path='postgres-selfcontained/'+name),'V3 embedded file not bound by outer manifest')
    rows={row['path']:row for row in files}
    base_raw=dump(sid,root+'/postgres-selfcontained/base/backup_manifest',8*1024*1024)
    base_sha=hashlib.sha256(base_raw).hexdigest()
    require(base_sha==sealed.get('base_manifest_sha256')==delivery.get('base_manifest_sha256')and
            rows.get('base/backup_manifest',{}).get('sha256')==base_sha,'V3 physical base manifest differs')
    require(base_sha in accepted_bases,'V3 physical base needs compatible actual restore evidence')
    manifest=json.loads(base_raw);ranges=manifest.get('WAL-Ranges',[])
    require(len(ranges)==1,'V3 requires one explicit timeline')
    def lsn(value):
        require(re.fullmatch('[0-9A-F]+/[0-9A-F]+',value)is not None,'V3 invalid LSN')
        hi,lo=value.split('/');return int(hi,16)*2**32+int(lo,16)
    span=ranges[0];start,end,target=lsn(span['Start-LSN']),lsn(span['End-LSN']),lsn(marker['wal_lsn'])
    require(start<=end<=target and span['Timeline']==int(segment[:8],16),'V3 base after marker or timeline differs')
    first,last=start//(16*1024*1024),(target-1)//(16*1024*1024)
    require(0<=last-first<100000,'V3 invalid WAL span')
    for number in range(first,last+1):
        name=f"{span['Timeline']:08X}{number//256:08X}{number%256:08X}.gz"
        require('wal/'+name in rows,'V3 contiguous WAL missing')
    require(segment==f"{span['Timeline']:08X}{last//256:08X}{last%256:08X}",'V3 marker segment/LSN differs')
    compressed=dump(sid,root+'/postgres-selfcontained/wal/'+segment+'.gz',20*1024*1024)
    require(hashlib.sha256(compressed).hexdigest()==rows['wal/'+segment+'.gz']['sha256'],'V3 marker WAL fingerprint differs')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed))as stream:raw=stream.read(16*1024*1024+1)
    require(len(raw)==16*1024*1024 and marker['restore_point'].encode()in raw,'V3 exact named marker absent')
    return dict(child_snapshot=sid,kind='selfcontained-pg-named-point',source='postgres-archive-delivery.json',
                verified=True,evidence_sha256=hashlib.sha256(capture_raw+b'\0'+delivery_raw+b'\0'+marker_raw+b'\0'+sealed_raw+b'\0'+outer_raw).hexdigest(),
                restore_point=marker['restore_point'],wal_segment=segment,postgres_recovery_included=True,
                external_parent_dependency=None,metadata_verified=True,postgres_named_target_restore_verified=False,
                base_manifest_sha256=base_sha)
