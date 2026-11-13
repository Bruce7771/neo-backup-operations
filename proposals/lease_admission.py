#!/usr/bin/env python3
"""Independent authority for a fresh exact manual plan; never flips planner flag.

Local <=300s admission lease is NOT a repository lock or backup-start fence.
Every native mutation still needs fresh writer/lock observations and native
exclusive restic locking; unknown/busy sources fail without stopping them.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets


class NotAdmitted(Exception):pass


def require(ok,reason):
    if not ok:raise NotAdmitted(reason)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def removal_review_digest(candidate,policy,executor_sha,static_inputs):
    # Concurrent append-only snapshots do not demand a different owner decision.
    # Exact fresh inventory is separately bound into each actual admission.
    return hashlib.sha256(canonical({'remove':sorted(candidate['remove_snapshot_ids']),
        'policy_sha256':hashlib.sha256(canonical(policy)).hexdigest(),
        'static_inputs_sha256':hashlib.sha256(canonical(static_inputs)).hexdigest(),'executor_sha':executor_sha,
        'protocol':'native-lock-manual-v1'})).hexdigest()


def observations(local,external,locks,repository_id,policy,now):
    require(local.get('schema')==2 and local.get('local_inventory_complete')is True
            and local.get('source_review_integrity')is True and local.get('native_restic_writer_protocol_only')is True,
            'Local writer inventory incomplete')
    require(local.get('repository_id')==repository_id
            and local.get('writer_policy_sha256')==policy.get('writer_policy_sha256'),
            'Source/repository policy binding differs')
    require(0<=now-local.get('observed_epoch',0)<=15,'Local writer observation stale')
    require(not local.get('unknown_writer_units')and local.get('unknown_repository_clients')==0,
            'Unclassified repository client')
    require(not local.get('active_known_writer_units')and local.get('active_known_repository_clients')==0,
            'Working backup busy; do not stop it')
    require(type(local.get('next_known_writer_start_epoch'))in(int,float)
            and local['next_known_writer_start_epoch']-now>=30,'No quiet interval before next scheduled writer')
    require(external.get('complete')is True and 0<=now-external.get('observed_epoch',0)<=15
            and external.get('repositories')==policy.get('credential_holder_repositories')
            and external.get('other_running_jobs')==0,'External writer observation incomplete/busy')
    require(locks.get('complete')is True and locks.get('repository_id')==repository_id
            and 0<=now-locks.get('observed_epoch',0)<=5 and locks.get('total_locks')==0,
            'Native repository lock busy/unknown; never unlock automatically')


def revalidate_bundle(bundle,policy,static_inputs,now):
    require(bundle.get('schema')==1 and 0<=now-bundle.get('validated_epoch',0)<=30,'Fresh validation bundle required')
    require(bundle.get('policy')==policy,'Protected policy changed')
    require(set(static_inputs['protected'])<=set(bundle['protected'])
            and bundle['restored']==static_inputs['restored']
            and bundle['dependencies']==static_inputs['dependencies'],'Protected recovery evidence changed')
    for edge in static_inputs['hourly_overrides']:
        require(edge in bundle['hourly_recovery'],'Reviewed external recovery edge absent/changed')
    for edge in policy.get('protected_unknown_hourly',[]):
        require(edge in bundle['hourly_recovery'],'Immutable UNKNOWN evidence differs from protected policy')
    scripts=Path(__file__).resolve().parents[1]/'scripts'
    spec=importlib.util.spec_from_file_location('fresh_retention_validator',scripts/'retention-plan.py')
    planner=importlib.util.module_from_spec(spec);spec.loader.exec_module(planner)
    scopes=policy.get('scopes',[]);configs=policy.get('configuration_scopes',[])
    require(policy.get('schema')==1 and len(scopes)==3
            and {row['kind']for row in scopes}=={'daily','pitr','hourly'},'Exact reviewed scope policy required')
    planner.SCOPES={row['host']:(row['tag'],frozenset(row['paths']))for row in scopes}
    planner.CONFIG_SCOPES={(row['host'],row['tag']):row['paths'][0]for row in configs}
    planner.FULL_MAIN_HOST=next(row['host']for row in scopes if row['kind']=='daily')
    holds=None
    if policy.get('unknown_recovery_hold_mode')=='reviewed-as-of-immutable-root-set':
        spec=importlib.util.spec_from_file_location('fresh_asof_validator',scripts/'asof_recovery_hold.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        holds=module.fixed_hold(bundle['inventory'],policy)
    rebuilt=planner.build(bundle['inventory'],bundle['plans'],bundle['protected'],bundle['restored'],
        bundle['dependencies'],bundle['hourly_recovery'],holds)
    require(all(bundle['candidate'].get(key)==value for key,value in rebuilt.items()),'Exact plan/closure revalidation changed')
    return dict(rebuilt,inventory_stable_for_admission=bundle['candidate'].get('inventory_stable_for_admission')is True)


def admit(bundle,policy,static_inputs,expected_digest,executor_sha,maximum,repository_id,local,external,locks,now,*,prune=False,lease_start_epoch=None):
    candidate=revalidate_bundle(bundle,policy,static_inputs,now)
    require(candidate.get('schema')==1 and candidate.get('apply_ready')is False,
            'Expected original read-only planner candidate')
    require(candidate.get('inventory_stable_for_admission')is True,'Fresh stable replan required')
    remove=candidate.get('remove_snapshot_ids',[])
    require(0<len(remove)<=maximum<=10 and len(remove)==len(set(remove)),'Exact nonzero removal bound required')
    require(all(isinstance(sid,str)and re.fullmatch('[0-9a-f]{64}',sid)for sid in remove),'Invalid snapshot identity')
    require(not set(remove)&set(candidate['protected_snapshot_ids'])
            and not set(remove)&set(candidate['retained_snapshot_ids']),'Protected/retained point selected')
    require(removal_review_digest(candidate,policy,executor_sha,static_inputs)==expected_digest,'Owner-reviewed removals/config changed')
    if candidate.get('protected_unknown_hourly_points',0):
        require(policy.get('unknown_recovery_hold_mode')=='reviewed-as-of-immutable-root-set'
                and policy.get('as_of_unknown_hold',{}).get('reviewed')is True,
                'Temporary growing hold is not permanent retention admission')
    require(not prune or policy.get('shared_repository_gc_reviewed')is True,'Repository-wide shared GC not reviewed')
    observations(local,external,locks,repository_id,policy,now)
    start=now if lease_start_epoch is None else lease_start_epoch
    require(0<=now-start<=240,'Fenced replan exceeded local admission budget')
    # The current plan already passed the real dependency planner/derive. Bind
    # the entire exact content, not a caller-selected list of IDs alone.
    return {'schema':1,'admitted':True,'lease_kind':'offsite-logical-native-lock-required',
        'nonce':secrets.token_hex(32),'created_epoch':start,'admitted_epoch':now,'expires_epoch':start+300,
        'repository_id':repository_id,'candidate_sha256':hashlib.sha256(canonical(candidate)).hexdigest(),
        'review_digest':expected_digest,'source_policy_sha256':local['writer_policy_sha256'],
        'executor_sha':executor_sha,'maximum_removals':maximum,'prune_reviewed':prune,
        'backup_starts_blocked':False,'native_exclusive_lock_required':True}


def before_native_mutation(lease,repository_id,policy,local,external,locks,now,remaining_seconds):
    require(lease.get('admitted')is True and lease.get('repository_id')==repository_id,
            'Missing repository-bound admission')
    require(lease['created_epoch']<=now and now+remaining_seconds+15<=lease['expires_epoch'],
            'Insufficient bounded lease/cleanup budget')
    observations(local,external,locks,repository_id,policy,now)
    require(local['next_known_writer_start_epoch']-now>=remaining_seconds+15,
            'Scheduled writer starts inside requested command budget; wait later')
