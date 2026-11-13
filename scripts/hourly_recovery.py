#!/usr/bin/env python3
"""Derive hourly recovery edges from private archive metadata. Never mutates B2."""
import copy
import gzip
import hashlib
import io
import json
import re
from asof_recovery_hold import fixed_hold
from hourly_selfcontained_v3 import derive_v3

HEX=re.compile(r'^[0-9a-f]{64}$')

def require(ok,reason):
    if not ok: raise ValueError(reason)

def derive(inventory,plans,policy,overrides,restored,dump):
    """dump(snapshot, absolute_path, max_bytes) returns bounded private bytes.

    Overrides are reviewed legacy/external exceptions only; normal new points
    are derived, not renewed by an owner every hour. Metadata verification is
    distinct from the separately scheduled full recovery exercise.
    """
    require(isinstance(overrides,list) and len(overrides)<=64,'Too many external hourly overrides')
    require(all(isinstance(e,dict) and isinstance(e.get('child_snapshot'),str) for e in overrides),'Invalid external hourly override')
    override={e['child_snapshot']:e for e in overrides}
    require(len(override)==len(overrides),'Duplicate external hourly override')
    require(all(HEX.fullmatch(sid) and e.get('source')=='reviewed-external-policy' for sid,e in override.items()),'Overrides require explicit external review')
    scopes={s['kind']:s for s in policy['scopes']}
    require(set(scopes)=={'daily','hourly','pitr'},'Exactly three distinct scope kinds required')
    require(len(scopes['hourly']['paths'])==len(scopes['pitr']['paths'])==1,'One exact hourly/PITR root required')
    rows={r['id']:r for r in inventory};require(len(rows)==len(inventory),'Duplicate inventory point')
    def authorized(row,kind):
        s=scopes[kind]
        return row.get('hostname')==s['host'] and s['tag'] in row.get('tags',[]) and set(row.get('paths',[]))==set(s['paths'])
    unknown=policy.get('protected_unknown_hourly',[])
    require(isinstance(unknown,list)and len(unknown)<=64,'Invalid protected UNKNOWN inventory')
    unknown_ids=[edge.get('child_snapshot')for edge in unknown]
    require(len(unknown_ids)==len(set(unknown_ids))and not set(unknown_ids)&set(override),'Conflicting UNKNOWN evidence')
    holds=set()
    if unknown:
        require(policy.get('unknown_recovery_hold_mode')in('hold-all-authorized-recovery-roots','reviewed-as-of-immutable-root-set'),
                'UNKNOWN producer scopes require conservative recovery-root holds')
        for edge in unknown:
            child=edge.get('child_snapshot')
            require(isinstance(child,str)and HEX.fullmatch(child)and child in rows
                    and authorized(rows[child],'hourly'),'UNKNOWN point outside reviewed hourly inventory')
            require(edge.get('kind')=='protected-unknown'and edge.get('source')=='reviewed-external-policy'
                    and edge.get('reason')=='ARCHIVE_CAPTURE_SCOPE_UNDECLARED'
                    and edge.get('hold_verified')is True and edge.get('restore_coverage')=='unknown'
                    and HEX.fullmatch(edge.get('evidence_sha256',''))is not None,
                    'UNKNOWN hold cannot claim legacy or verified recovery')
            require(not any(k in edge for k in('wal_snapshot','restore_point','wal_segment','postgres_recovery_included','verified')),
                    'UNKNOWN hold must not invent a recovery classification')
            override[child]=copy.deepcopy(edge)
        if policy.get('unknown_recovery_hold_mode')=='reviewed-as-of-immutable-root-set':
            holds=fixed_hold(inventory,policy)
        else:
            # Transitional read-only/no-op mode, not permanent 30/3 policy.
            holds={sid for sid,row in rows.items()if authorized(row,'daily')or authorized(row,'pitr')}
            for row in inventory:
                for scope in policy.get('configuration_scopes',[]):
                    if row.get('hostname')==scope['host']and scope['tag']in row.get('tags',[])and row.get('paths')==scope['paths']:
                        holds.add(row['id'])
        holds.update(unknown_ids)
    # A hold is applied before choosing retained children: a future age policy
    # must not silently remove UNKNOWN points instead of classifying them.
    working=copy.deepcopy(plans)
    for plan in working:
        for group in plan:
            moved=[r for r in group.get('remove')or[]if r['id']in holds]
            group['remove']=[r for r in group.get('remove')or[]if r['id']not in holds]
            group['keep']=list(group.get('keep')or[])+moved
    removed={r['id'] for plan in working for group in plan for r in group.get('remove') or []}
    retained=set(rows)-removed
    children=sorted(sid for sid in retained if authorized(rows[sid],'hourly'))
    edges=[];parents=set(holds);wal_checks={};base_hashes={}
    def data(sid,path,maximum=1024*1024):
        raw=dump(sid,path,maximum);require(isinstance(raw,bytes) and len(raw)<=maximum,'Oversize archive metadata')
        return raw,json.loads(raw)
    pitr=scopes['pitr']['paths'][0].rstrip('/')
    # One already accepted physical base can support many later WAL shipments.
    accepted_bases=set()
    for sid in restored:
        if sid in rows and authorized(rows[sid],'pitr'):
            raw,_=data(sid,pitr+'/base/backup_manifest',8*1024*1024)
            accepted_bases.add(hashlib.sha256(raw).hexdigest())
    for sid in children:
        if sid in override:
            edge=copy.deepcopy(override[sid])
            if edge.get('kind')=='protected-unknown':
                raw=dump(sid,scopes['hourly']['paths'][0].rstrip('/')+'/manifest.json',4*1024*1024)
                require(hashlib.sha256(raw).hexdigest()==edge['evidence_sha256'],'UNKNOWN immutable manifest fingerprint changed')
        else:
            root=scopes['hourly']['paths'][0].rstrip('/')
            capture_raw,capture=data(sid,root+'/capture-result.json')
            require(capture.get('scope')=='neo-hourly-write-fenced-capture' and capture.get('sqlite_verified')==6
                    and capture.get('postgres_marker_recorded') is True,'Unknown hourly format requires reviewed override')
            delivery_raw,delivery=data(sid,root+'/postgres-archive-delivery.json')
            marker_raw,marker=data(sid,root+'/postgres-point.private.json')
            if delivery.get('schema')==3:
                edge=derive_v3(sid,root,capture_raw,delivery_raw,marker_raw,accepted_bases,dump)
                edges.append(edge)
                continue
            parent=delivery.get('wal_snapshot');segment=delivery.get('wal_segment');name=delivery.get('marker_restore_point')
            require(isinstance(parent,str) and HEX.fullmatch(parent) and parent in rows and authorized(rows[parent],'pitr'),'Unknown hourly PITR parent')
            require(isinstance(segment,str) and re.fullmatch('[0-9A-F]{24}',segment) and isinstance(name,str)
                    and re.fullmatch('neo_hourly_[0-9]+_[0-9a-f]{8}',name),'Invalid exact hourly target')
            require(delivery.get('archive_delivery_verified') is True and marker.get('restore_point')==name
                    and marker.get('wal_segment')==segment,'Hourly delivery and capture target differ')
            checksum=delivery.get('wal_sha256');require(isinstance(checksum,str) and HEX.fullmatch(checksum),'Missing WAL content hash')
            if parent not in base_hashes:
                base_raw,_=data(parent,pitr+'/base/backup_manifest',8*1024*1024)
                base_hashes[parent]=hashlib.sha256(base_raw).hexdigest()
            require(base_hashes[parent] in accepted_bases,'PITR base lacks compatible full-restore evidence')
            key=(parent,segment)
            if key not in wal_checks:
                compressed=dump(parent,pitr+'/wal/'+segment+'.gz',20*1024*1024)
                require(hashlib.sha256(compressed).hexdigest()==checksum,'Archived WAL content hash differs')
                with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream: raw=stream.read(16*1024*1024+1)
                require(len(raw)==16*1024*1024,'Invalid archived WAL length')
                wal_checks[key]=(checksum,raw)
            actual_checksum,raw=wal_checks[key]
            require(actual_checksum==checksum and name.encode() in raw,'Archived WAL lacks exact named marker')
            # Keep no unbounded WAL cache: one segment is enough for nearby points.
            if len(wal_checks)>1:
                wal_checks={key:wal_checks[key]}
            edge=dict(child_snapshot=sid,kind='pitr-named-point',source='postgres-archive-delivery.json',verified=True,
                      evidence_sha256=hashlib.sha256(capture_raw+b'\0'+delivery_raw+b'\0'+marker_raw).hexdigest(),
                      wal_snapshot=parent,restore_point=name,wal_segment=segment,delivery_verified=True,
                      wal_sha256=checksum,base_manifest_sha256=base_hashes[parent])
        edges.append(edge)
        if edge.get('kind')=='pitr-named-point':
            parent=edge.get('wal_snapshot')
            require(parent in rows and authorized(rows[parent],'pitr'),'External hourly parent outside authorized PITR scope')
            parents.add(parent)
    updated=working
    for plan in updated:
        for group in plan:
            moved=[r for r in group.get('remove') or [] if r['id'] in parents]
            if moved:
                group['remove']=[r for r in group['remove'] if r['id'] not in parents]
                group['keep']=list(group.get('keep') or [])+moved
    return edges,parents,updated
