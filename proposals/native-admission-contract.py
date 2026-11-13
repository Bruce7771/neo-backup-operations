#!/usr/bin/env python3
"""PROPOSAL: pure read-only checks before any native-GC admission.

Input must come from fresh reviewed collectors, never caller assertions alone.
This module does not acquire locks, grant mutation authority, or run restic.
"""
import re

GROUP='backup-repository-maintenance'
WORKFLOWS={'maintenance-access-check.yml','retention-audit.yml','retention-readonly-check.yml'}
# restic0.16.4 ls does NOT acquire a native lock even by default.
DATA_READERS={'dump','cat','restore','stats','snapshots','check'}

def validate_reader_contract(value):
    if value.get('repository')!='Bruce7771/neo-backup-operations':raise ValueError('Unsupported credential holder')
    rows=value.get('gha_b2_workflows',[])
    if {x.get('name')for x in rows}!=WORKFLOWS or len(rows)!=len(WORKFLOWS):raise ValueError('Incomplete external reader roster')
    if any(x.get('group')!=GROUP or x.get('cancel_in_progress')is not False for x in rows):raise ValueError('External reader isolation missing')
    if value.get('mutator_group')!=GROUP or value.get('mutator_cancel_in_progress')is not False:raise ValueError('Mutation group mismatch')
    if value.get('vm_roster_reviewed_complete')is not True:raise ValueError('VM reader roster incomplete')
    sites=value.get('vm_data_read_sites',[])
    if not sites:raise ValueError('VM reader sites missing')
    for site in sites:
        if site.get('command')not in DATA_READERS or site.get('explicit_no_lock')is not False:
            raise ValueError('Unenrolled native data reader')
        if re.fullmatch('[0-9a-f]{64}',site.get('installed_sha256',''))is None:raise ValueError('Installed reader not pinned')
        if site.get('multi_command')is True and site.get('selected_snapshot_protected')is not True:
            raise ValueError('Multi-command snapshot may disappear between native locks')
    parents=value.get('late_v2_parent_snapshots',[])
    if len(parents)!=3 or len(set(parents))!=3 or any(re.fullmatch('[0-9a-f]{64}',x)is None for x in parents):
        raise ValueError('Three authenticated late-v2 parents required')
    if not set(parents)<=set(value.get('protected_snapshots',[])):raise ValueError('Late-v2 parent protection missing')
    return {'native_reader_contract_valid':True,'external_reader_workflows':len(rows),'late_parents_protected':3,
            'nonzero_authority_granted':False}

def validate_gc_window(value):
    if value.get('actual_active_backup_or_accept_jobs')!=0:raise ValueError('Existing operation active')
    if value.get('observed_native_locks')!=0:raise ValueError('Native repository busy')
    timers=value.get('seconds_to_next',{})
    if set(timers)!={'pitr','hourly','daily'} or any(type(x)not in(int,float)or x<=120 for x in timers.values()):
        raise ValueError('Insufficient quiet window')
    if value.get('native_gc_max_seconds')!=90:raise ValueError('Unreviewed GC budget')
    if value.get('native_timeout_cleanup_proved')is not True:raise ValueError('Interrupted GC cleanup unproved')
    if value.get('fresh_inventory_digest')!=value.get('reviewed_plan_inventory_digest'):raise ValueError('Inventory changed')
    if re.fullmatch('[0-9a-f]{64}',value.get('fresh_inventory_digest',''))is None:raise ValueError('Unbound inventory')
    return {'quiet_window_valid':True,'nonzero_authority_granted':False}

def own_dead_lock_cleanup_allowed(before_ids,after_records,*,reaped,pid,hostname):
    """Never call native unlock with any unknown additional lock present."""
    return bool(reaped and len(before_ids)==1 and len(after_records)==1 and
        after_records[0].get('id')==before_ids[0] and after_records[0].get('pid')==pid and
        after_records[0].get('hostname')==hostname and after_records[0].get('exclusive')is True)
