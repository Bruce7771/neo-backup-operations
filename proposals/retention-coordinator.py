#!/usr/bin/env python3
"""Proposed real manual coordinator: native locks, no backup-start/service fence.

The readonly planner remains readonly. A separately rebuilt, fresh plan receives
bounded local admission after owner digest + actual writer/lock observations.
Not registered by GitHub while this file/workflow remain in proposals/.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'proposals'))
from lease_admission import admit,before_native_mutation,observations,removal_review_digest,revalidate_bundle
from external_writer_observation import observe
from retention_postcheck import validate,restore


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def require(ok,reason):
    if not ok:raise ValueError(reason)


def mutation_transition(before,after,approved):
    """No unapproved disappearance or changed immutable old record is allowed."""
    old={row['id']:row for row in before};new={row['id']:row for row in after}
    require(set(old)-set(new)==set(approved),'Native forget did not remove exactly the approved IDs')
    require(all(new[sid]==row for sid,row in old.items()if sid in new),'Immutable snapshot metadata changed')
    return set(new)-set(old)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('plan','apply'),default='plan')
    parser.add_argument('--expected-digest',default='');parser.add_argument('--maximum-removals',type=int,default=0)
    parser.add_argument('--prune',action='store_true');args=parser.parse_args()
    os.umask(0o077);env=dict(os.environ)
    require(not any(v for k,v in env.items()if'MASTER'in k.upper()),'Master credentials forbidden')
    policy=json.loads(env['NEO_POLICY_JSON'])
    static={'protected':json.loads(env['NEO_PROTECTED_JSON']),'restored':json.loads(env['NEO_RESTORED_JSON']),
        'dependencies':json.loads(env['NEO_DEPENDENCIES_JSON']),'hourly_overrides':json.loads(env['NEO_HOURLY_RECOVERY_JSON'])}
    executor=env['GITHUB_SHA'];require(re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',executor)is not None,'Exact executor commit required')
    legacy=load('bounded_private_process',ROOT/'scripts/retention-manual.py')
    access=load('private_scoped_access',ROOT/'scripts/maintenance-access-check.py')
    phase='prepare';mutation_started=False;forgotten=False;pruned=False
    with tempfile.TemporaryDirectory(prefix='neo-native-maintenance-',dir=env['RUNNER_TEMP'])as tmp:
        work=Path(tmp);work.chmod(0o700);password=work/'password';password.write_text(env['NEO_RESTIC_PASSWORD']);password.chmod(0o600)
        native={k:v for k,v in env.items()if not k.startswith(('NEO_','AWS_','RESTIC_'))}
        native.update(RESTIC_REPOSITORY=env['RESTIC_REPOSITORY'],RESTIC_PASSWORD_FILE=str(password),
            AWS_ACCESS_KEY_ID=env['AWS_ACCESS_KEY_ID'],AWS_SECRET_ACCESS_KEY=env['AWS_SECRET_ACCESS_KEY'],
            XDG_CACHE_HOME=str(work/'cache'))
        if env.get('AWS_DEFAULT_REGION'):native['AWS_DEFAULT_REGION']=env['AWS_DEFAULT_REGION']
        def native_call(arguments,timeout=60):return legacy.bounded(['restic']+arguments,native,timeout)
        version=native_call(['version'],10).decode();require(version.startswith('restic 0.16.4 '),'Pinned restic required')
        bucket,endpoint,prefix=access.repository_target(env['RESTIC_REPOSITORY'])
        access.authorize_pair(env['AWS_ACCESS_KEY_ID'],env['AWS_SECRET_ACCESS_KEY'],
            access.MAINTENANCE if args.mode=='apply'else access.AUDIT,bucket,endpoint,prefix)
        repository=json.loads(native_call(['--no-cache','--no-lock','cat','config']))['id']
        def plan(label,timeout=240):
            destination=work/(label+'.json')
            audit={k:v for k,v in env.items()if k not in('NEO_MAINTENANCE_SSH_KEY','NEO_MAINTENANCE_OBSERVER_SSH_KEY','NEO_MAINTENANCE_SSH_KNOWN_HOSTS')}
            audit['NEO_RETENTION_VALIDATION_BUNDLE_OUTPUT']=str(destination)
            legacy.bounded([sys.executable,str(ROOT/'scripts/retention-audit.py')],audit,timeout)
            return json.loads(destination.read_text())
        phase='read-only-plan';first=plan('first')
        candidate=revalidate_bundle(first,policy,static,time.time())
        review=removal_review_digest(candidate,policy,executor,static)
        print(json.dumps({'scope':'manual-native-retention-review','review_digest':review,
            'removal_candidates':len(candidate['remove_snapshot_ids']),'writer_pause_performed':False}))
        def postcheck(candidate):
            validate(candidate,policy)
            native_call(['--no-cache','--no-lock','check'],150)
            destination=work/('check-'+secrets.token_hex(4));destination.mkdir(mode=0o700)
            return restore(candidate,policy,destination,lambda arguments:native_call(arguments,90))
        if not candidate['remove_snapshot_ids']:
            checks=postcheck(candidate)
            print(json.dumps({'result':'no-op-zero-candidates','deleted_snapshots':0,'prune_performed':False,
                'writer_pause_performed':False,'repository_integrity_check':True,**checks}));return
        if args.mode=='plan':return
        require(env.get('NEO_BACKUP_APPLY_ENABLED')=='true','Manual apply switch closed')
        require(review==args.expected_digest,'Exact owner-reviewed removal/config digest required')
        require(0<len(candidate['remove_snapshot_ids'])<=args.maximum_removals<=10,'Explicit exact removal bound required')
        validate(candidate,policy)
        # New SSH permission is READ ONLY. Never invoke old acquire/release or
        # a service/timer stop, mask, pause, restart or general shell.
        target=policy.get('maintenance_ssh',{}).get('target','')
        require(re.fullmatch('root@[A-Za-z0-9.:-]+',target)is not None,'Reviewed SSH destination missing')
        key=work/'ssh-key';key.write_text(env['NEO_MAINTENANCE_OBSERVER_SSH_KEY']);key.chmod(0o600)
        hosts=work/'known-hosts';hosts.write_text(env['NEO_MAINTENANCE_SSH_KNOWN_HOSTS']);hosts.chmod(0o600)
        ssh=['ssh','-F','/dev/null','-T','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
            '-o','ConnectTimeout=8','-o','UserKnownHostsFile='+str(hosts),'-i',str(key),target,'writer-status']
        ssh_env={k:env[k]for k in('PATH','HOME','LANG','LC_ALL','TMPDIR')if k in env}
        def fresh():
            local=json.loads(legacy.bounded(ssh,ssh_env,15))
            external=observe(policy['credential_holder_repositories'],env['GITHUB_REPOSITORY'],env['GITHUB_RUN_ID'])
            lock_ids=native_call(['--no-cache','--no-lock','list','locks'],15).decode().splitlines()
            require(all(re.fullmatch('[0-9a-f]{64}',sid)for sid in lock_ids),'Unknown native lock inventory')
            locks={'complete':True,'repository_id':repository,'observed_epoch':time.time(),'total_locks':len(lock_ids)}
            return local,external,locks
        phase='fresh-writer-observation';initial=fresh();observations(*initial,repository,policy,time.time())
        start=time.time();deadline=time.monotonic()+300
        phase='bounded-fresh-replan';second=plan('second',min(200,deadline-time.monotonic()-75))
        current=revalidate_bundle(second,policy,static,time.time())
        require(removal_review_digest(current,policy,executor,static)==review,'Removal/config set changed; reapprove')
        source,external,locks=fresh()
        lease=admit(second,policy,static,review,executor,args.maximum_removals,repository,
            source,external,locks,time.time(),prune=args.prune,lease_start_epoch=start)
        (work/'admission.json').write_text(json.dumps(lease))
        try:
            phase='exact-native-forget'
            source,external,locks=fresh();before_native_mutation(lease,repository,policy,source,external,locks,time.time(),25)
            mutation_started=True
            # These commands retain native exclusive locks and do not wait on a
            # working backup. Failure is a later retry, never a service pause.
            native_call(['--retry-lock','0s','forget','--json']+current['remove_snapshot_ids'],25);forgotten=True
            after=json.loads(native_call(['--no-cache','--no-lock','snapshots','--json']))
            additions=mutation_transition(second['inventory'],after,current['remove_snapshot_ids'])
            require(set(current['protected_snapshot_ids'])<=set(row['id']for row in after),'Protected point absent after forget')
            if args.prune:
                phase='reviewed-native-shared-gc'
                require(not additions,'New point appeared; shared GC needs a fresh dependency replan')
                source,external,locks=fresh();before_native_mutation(lease,repository,policy,source,external,locks,time.time(),60)
                native_call(['--retry-lock','0s','prune','--max-repack-size','16M'],60);pruned=True
            # The local WRITE admission is no longer used. Read-only check and
            # small restore may overlap a later working backup without a fence.
            phase='post-maintenance-readonly-check';checks=postcheck(current)
            print(json.dumps({'result':'exact-manual-retention-verified','forgotten_snapshots':len(current['remove_snapshot_ids']),
                'prune_performed':pruned,'writer_pause_performed':False,'repository_integrity_check':True,**checks}))
        except Exception:
            post_failure_checked=False
            if mutation_started and phase!='post-maintenance-readonly-check':
                try:postcheck(current);post_failure_checked=True
                except Exception:pass
            print(json.dumps({'result':'manual-maintenance-needs-review','phase':phase,'mutation_started':mutation_started,
                'forget_completed':forgotten,'prune_completed':pruned,'services_or_backup_schedules_changed':False,
                'post_failure_readonly_integrity_and_component_restore_passed':post_failure_checked,
                'unknown_locks_never_unlocked':True}));raise
        finally:
            # No server fence exists to release: no starts were blocked. Local
            # descriptor and credentials are destroyed with the private context.
            (work/'admission.json').unlink(missing_ok=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('::error::Manual native maintenance stopped safely ('+type(error).__name__+'); inspect private phase/locks',file=sys.stderr)
        raise SystemExit(1)
