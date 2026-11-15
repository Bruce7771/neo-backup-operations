#!/usr/bin/env python3
"""Inactive existing-engine optional same-job hooks; normal audit unchanged."""
import importlib.util,shutil
from pathlib import Path

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;out=load('tail_family_base',here/'build-unverified-base-family-retention-engine.proposed.py').build(original,destination);once=load('tail_once',here/'retention-safety-candidate.py').once
 shutil.copyfile(here/'same-job-fresh-tail.proposed.py',out/'same_job_fresh_tail.py')
 p=out/'hourly_recovery.py';s=p.read_text();s=once(s,'child_subset=None,child_observer=None):','child_subset=None,child_observer=None,same_job_cache=None):')
 old="""    accepted_bases=set()
    for sid in restored:
        if sid in rows and authorized(rows[sid],'pitr'):
            raw,_=data(sid,pitr+'/base/backup_manifest',8*1024*1024)
            accepted_bases.add(hashlib.sha256(raw).hexdigest())"""
 new="""    accepted_bases=set()
    if same_job_cache is not None:
        accepted_bases=same_job_cache.restore_bases(inventory,policy,restored)
    else:
        for sid in restored:
            if sid in rows and authorized(rows[sid],'pitr'):
                raw,_=data(sid,pitr+'/base/backup_manifest',8*1024*1024)
                accepted_bases.add(hashlib.sha256(raw).hexdigest())
    if hasattr(dump,'accepted_base_observer'):dump.accepted_base_observer(sorted(accepted_bases))"""
 s=once(s,old,new)
 s=once(s,'    for sid in children:\n        if sid in override:',"    for sid in children:\n        cached=same_job_cache.edge(sid)if same_job_cache is not None else None\n        if cached is not None:\n            edges.append(cached)\n            if cached.get('kind')=='pitr-named-point':parents.add(cached['wal_snapshot'])\n            continue\n        if sid in override:")
 s=once(s,'    unverified_families=',"    if hasattr(dump,'classified_edges_observer'):dump.classified_edges_observer(copy.deepcopy(edges))\n    unverified_families=")
 compile(s,str(p),'exec');p.write_text(s)
 p=out/'staged_derive.py';s=p.read_text();s=once(s,' recorded.native_pg_catalog=verify'," recorded.native_pg_catalog=verify\n for observer in('accepted_base_observer','classified_edges_observer'):\n  if hasattr(dump,observer):setattr(recorded,observer,getattr(dump,observer))");compile(s,str(p),'exec');p.write_text(s)
 p=out/'retention-audit.py';s=p.read_text();s=once(s,'        plan_paths=[Path(plans[i]) for i in range(1,len(plans),2)]',"        all_classified_edges={};accepted_restore_base_sha256=set()\n        dump.classified_edges_observer=lambda edges:all_classified_edges.update({e['child_snapshot']:e for e in edges})\n        dump.accepted_base_observer=lambda values:accepted_restore_base_sha256.update(values)\n        plan_paths=[Path(plans[i]) for i in range(1,len(plans),2)]")
 s=once(s,"bundle={'schema':1,'validated_epoch':int(time.time()),'policy':policy,","bundle={'schema':1,'validated_epoch':int(time.time()),'policy':policy,\n                'all_classified_hourly_recovery':list(all_classified_edges.values()),\n                'accepted_restore_base_sha256':sorted(accepted_restore_base_sha256),")
 compile(s,str(p),'exec');p.write_text(s);return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
