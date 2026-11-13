#!/usr/bin/env python3
"""Reviewed fixed historical UNKNOWN hold; no perpetual future-root hold."""
import datetime
import hashlib
import json
import re


def require(ok,reason):
    if not ok:raise ValueError(reason)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def projection(row):
    return {key:row[key]for key in('id','hostname','tags','paths','time')}


def utc(value):
    timestamp=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
    require(timestamp.tzinfo is not None,'Timezone required')
    return timestamp.astimezone(datetime.timezone.utc)


def fixed_hold(inventory,policy):
    contract=policy.get('as_of_unknown_hold',{})
    require(contract.get('schema')==2 and contract.get('reviewed')is True,'AS-OF schema2 hold not reviewed')
    baseline=contract.get('inventory_projection');require(isinstance(baseline,list)and baseline,'Missing AS-OF inventory')
    baseline=sorted(baseline,key=lambda row:row['id'])
    require(hashlib.sha256(canonical(baseline)).hexdigest()==contract.get('inventory_projection_sha256'),
            'AS-OF inventory fingerprint changed')
    rows={row['id']:row for row in inventory};past={row['id']:row for row in baseline}
    require(len(rows)==len(inventory)and len(past)==len(baseline),'Duplicate snapshot')
    require(all(re.fullmatch('[0-9a-f]{64}',sid)is not None for sid in past),'Invalid baseline identity')
    require(all(projection(rows[sid])==row for sid,row in past.items()if sid in rows),
            'Immutable AS-OF snapshot metadata changed')
    as_of=utc(contract['as_of_utc'])
    roots=[]
    def recovery_root(row):
        for scope in policy['scopes']+policy.get('configuration_scopes',[]):
            if scope.get('kind')=='hourly':continue
            if row['hostname']==scope['host']and scope['tag']in row['tags']and set(row['paths'])==set(scope['paths']):return True
        return False
    for sid,row in past.items():
        require(utc(row['time'])<=as_of,'Baseline exceeds AS-OF observation')
        if recovery_root(row):roots.append(sid)
    unknown=policy.get('protected_unknown_hourly',[])
    require(contract.get('unknown_evidence_count')==13 and len(unknown)==13
            and len({edge['child_snapshot']for edge in unknown})==13,'UNKNOWN exact count/coverage differs')
    evidence=sorted([{key:edge[key]for key in('child_snapshot','evidence_sha256','restore_coverage')}
                     for edge in unknown],key=lambda row:row['child_snapshot'])
    require(hashlib.sha256(canonical(evidence)).hexdigest()==contract.get('unknown_evidence_sha256'),
            'UNKNOWN exact evidence fingerprint differs')
    for edge in unknown:
        child=edge['child_snapshot']
        require(child in past and re.fullmatch('[0-9a-f]{64}',edge['evidence_sha256'])is not None
                and edge['restore_coverage']=='unknown',
                'UNKNOWN evidence differs from immutable baseline')
        roots.append(child)
    require(set(roots)<=set(rows),'Historical recovery root absent; never shrink protection automatically')
    for sid,row in rows.items():
        if sid not in past and recovery_root(row):
            require(utc(row['time'])>as_of,'New backdated root requires explicit review')
    # New future roots are deliberately NOT added to this historical hold.
    # Normal retained hourly/WAL/config ancestry still adds its own dependencies.
    return set(roots)
