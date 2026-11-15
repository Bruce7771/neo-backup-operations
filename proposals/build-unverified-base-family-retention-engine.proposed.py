#!/usr/bin/env python3
"""Inactive metadata-authenticated UNVERIFIED-base family quarantine, no restore."""
import importlib.util
from pathlib import Path

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;out=load('family_base',here/'build-complete-config-retention-engine.proposed.py').build(original,destination);once=load('family_once',here/'retention-safety-candidate.py').once
 p=out/'hourly_selfcontained_v3.py';s=p.read_text()
 s=once(s,"    require(base_sha in accepted_bases,'V3 physical base needs compatible actual restore evidence')","    base_restore_compatible=base_sha in accepted_bases")
 s=once(s,"kind='selfcontained-pg-named-point',source='postgres-archive-delivery.json'","kind=('selfcontained-pg-named-point'if base_restore_compatible else'protected-unverified-base-family'),source='postgres-archive-delivery.json'")
 s=once(s,'verified=True,evidence_sha256=','verified=base_restore_compatible,base_restore_coverage=(\'compatible-actual-restore-evidence\'if base_restore_compatible else\'unverified\'),evidence_sha256=')
 compile(s,str(p),'exec');p.write_text(s)
 p=out/'hourly_recovery.py';s=p.read_text()
 s=once(s,"    children=sorted(sid for sid in retained if authorized(rows[sid],'hourly'))","    # Classify every authorized hourly before expiry: an expired but\n    # untested family cannot disappear merely because its age rule selected it.\n    children=sorted(sid for sid in rows if authorized(rows[sid],'hourly'))")
 s=once(s,'    updated=working',"    unverified_families={e['base_manifest_sha256']for e in edges if e.get('kind')=='protected-unverified-base-family'}\n    if unverified_families:\n        parents.update(e['child_snapshot']for e in edges if e.get('base_manifest_sha256')in unverified_families)\n        # Conservatively hold all authorized PITR while a family is untested.\n        # This contains every possible WAL family without guessing memberships.\n        parents.update(sid for sid,row in rows.items()if authorized(row,'pitr'))\n    updated=working")
 s=once(s,'    return edges,parents,updated',"    if child_subset is None:\n        removed_after_holds={r['id']for plan in updated for group in plan for r in group.get('remove')or[]}\n        edges=[edge for edge in edges if edge['child_snapshot']not in removed_after_holds]\n    return edges,parents,updated")
 compile(s,str(p),'exec');p.write_text(s)
 p=out/'retention-plan.py';s=p.read_text()
 anchor="        require(isinstance(edge.get('evidence_sha256'),str) and HEX.fullmatch(edge['evidence_sha256']) and"
 branch="""        if edge.get('kind')=='protected-unverified-base-family':
            require(edge['child_snapshot']in protected and edge.get('verified')is False
                    and edge.get('metadata_verified')is True and edge.get('base_restore_coverage')=='unverified'
                    and edge.get('postgres_named_target_restore_verified')is False
                    and edge.get('external_parent_dependency')is None and 'wal_snapshot'not in edge
                    and edge.get('postgres_recovery_included')is True
                    and isinstance(edge.get('base_manifest_sha256'),str)and HEX.fullmatch(edge['base_manifest_sha256'])
                    and isinstance(edge.get('evidence_sha256'),str)and HEX.fullmatch(edge['evidence_sha256']),
                    'Unverified base family requires authenticated metadata and protected hold, not restored claim')
            require({sid for sid,host in eligible.items()if host==pitr_host}<=protected,
                    'Unverified base family must preserve every possible authorized PITR/WAL reference')
            continue
"""
 s=once(s,anchor,branch+anchor)
 s=once(s,'"protected_unknown_hourly_points":sum(edge.get(\'kind\')==\'protected-unknown\'for edge in hourly_recovery),', '"protected_unknown_hourly_points":sum(edge.get(\'kind\')==\'protected-unknown\'for edge in hourly_recovery),\n        "protected_unverified_base_family_count":len({e[\'base_manifest_sha256\']for e in hourly_recovery if e.get(\'kind\')==\'protected-unverified-base-family\'}),\n        "protected_unverified_base_hourly_points":sum(e.get(\'kind\')==\'protected-unverified-base-family\'for e in hourly_recovery),')
 compile(s,str(p),'exec');p.write_text(s)
 p=out/'retention-readonly-check.py';s=p.read_text();s=once(s,"'protected_unknown_hourly_points':candidate.get('protected_unknown_hourly_points',0),","'protected_unknown_hourly_points':candidate.get('protected_unknown_hourly_points',0),\n            'protected_unverified_base_family_count':candidate.get('protected_unverified_base_family_count',0),\n            'protected_unverified_base_hourly_points':candidate.get('protected_unverified_base_hourly_points',0),")
 compile(s,str(p),'exec');p.write_text(s);return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
