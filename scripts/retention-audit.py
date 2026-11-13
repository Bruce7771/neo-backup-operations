#!/usr/bin/env python3
"""Read-only restic retention audit. Private inventories never reach stdout."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from hourly_recovery import derive
from hourly_metadata_batch import HourlyMetadataBatch

ROOT=Path(__file__).resolve().parent

def run(args, env, timeout=45):
    return subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,check=True,timeout=timeout).stdout

def main():
    env=dict(os.environ)
    required=('RESTIC_REPOSITORY','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','NEO_RESTIC_PASSWORD',
              'NEO_POLICY_JSON','NEO_PROTECTED_JSON','NEO_RESTORED_JSON','NEO_DEPENDENCIES_JSON',
              'NEO_HOURLY_RECOVERY_JSON')
    if not all(env.get(k) for k in required):
        raise ValueError('Required independent audit credentials/policy are not provisioned')
    if not env['RESTIC_REPOSITORY'].startswith('s3:https://') or not env['RESTIC_REPOSITORY'].rstrip('/').endswith('/restic'):
        raise ValueError('Repository must be an explicit HTTPS S3 restic prefix')
    policy=json.loads(env['NEO_POLICY_JSON'])
    if policy.get('schema')!=1 or len(policy.get('scopes',[]))!=3:
        raise ValueError('Exactly three reviewed backup scopes required')
    # Keep private recovery password, inventory, scope paths and lease data ephemeral.
    with tempfile.TemporaryDirectory(prefix='neo-retention-audit-',dir=env.get('RUNNER_TEMP')) as directory:
        work=Path(directory);work.chmod(0o700)
        password=work/'password';password.write_text(env.pop('NEO_RESTIC_PASSWORD'));password.chmod(0o600)
        env['RESTIC_PASSWORD_FILE']=str(password)
        env['XDG_CACHE_HOME']=str(work/'cache')
        for dangerous in ('RESTIC_PASSWORD','RESTIC_PASSWORD_COMMAND','AWS_SESSION_TOKEN','AWS_PROFILE',
                          'AWS_CONFIG_FILE','AWS_SHARED_CREDENTIALS_FILE'):
            env.pop(dangerous,None)
        for source,target in (('NEO_POLICY_JSON','policy.json'),('NEO_PROTECTED_JSON','protected.json'),
                              ('NEO_RESTORED_JSON','restored.json'),('NEO_DEPENDENCIES_JSON','dependencies.json'),
                              ('NEO_HOURLY_RECOVERY_JSON','hourly-recovery.json')):
            (work/target).write_text(env.pop(source));(work/target).chmod(0o600)
        version=run(['restic','version'],env)
        if not version.startswith('restic 0.16.4 '):
            raise ValueError('Use the reviewed checksum-pinned restic version')
        inventory=run(['restic','--no-lock','snapshots','--json'],env)
        (work/'inventory.json').write_text(inventory)
        plans=[]
        for index,scope in enumerate(policy['scopes']):
            if not isinstance(scope.get('host'),str) or not scope['host'] or not isinstance(scope.get('tag'),str) or not scope['tag']:
                raise ValueError('Reviewed host/tag missing from scope policy')
            plan=run(['restic','--no-lock','forget','--dry-run','--json','--host',scope['host'],
                      '--tag',scope['tag'],'--group-by','host','--keep-within','30d',
                      '--keep-daily','30','--keep-monthly','3'],env)
            destination=work/f'plan-{index}.json';destination.write_text(plan);plans+=['--plan',str(destination)]
        # The protected secret contains reviewed legacy/external exceptions,
        # not an owner-maintained list of every new hourly point.
        deadline=time.monotonic()+180
        hourly_scopes=[scope for scope in policy['scopes']if scope.get('kind')=='hourly']
        if len(hourly_scopes)!=1:raise ValueError('Exactly one hourly metadata scope required')
        # Checkpoints outlive a failed audit subprocess within this runner job,
        # but never leave RUNNER_TEMP or become an uploaded Actions cache.
        cache_parent=Path(env['RUNNER_TEMP'])if env.get('RUNNER_TEMP')else work
        cache_namespace=hashlib.sha256((env['RESTIC_REPOSITORY']+json.dumps(hourly_scopes[0],sort_keys=True)).encode()).hexdigest()
        metadata_batch=HourlyMetadataBatch(cache_parent/('neo-hourly-json-'+cache_namespace),env,
                                          json.loads(inventory),hourly_scopes[0],deadline)
        def dump(snapshot,path,maximum):
            import resource
            if metadata_batch.handles(snapshot,path):
                return metadata_batch.get(snapshot,path,maximum)
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise TimeoutError('Hourly metadata audit exceeded its read-only deadline')
            def restrict_output():
                resource.setrlimit(resource.RLIMIT_FSIZE,(maximum,maximum))
            with tempfile.TemporaryFile(dir=work) as output:
                subprocess.run(['restic','--no-lock','dump',snapshot,path],env=env,
                    stdout=output,stderr=subprocess.DEVNULL,check=True,
                    timeout=min(25,remaining),preexec_fn=restrict_output)
                if output.tell()>maximum:
                    raise ValueError('Archive read exceeds reviewed size bound')
                output.seek(0)
                return output.read(maximum+1)
        plan_paths=[Path(plans[i]) for i in range(1,len(plans),2)]
        edge_inventory,parents,updated=derive(json.loads(inventory),
            [json.loads(p.read_text()) for p in plan_paths],policy,
            json.loads((work/'hourly-recovery.json').read_text()),
            json.loads((work/'restored.json').read_text()),dump)
        metadata_read_proof=dict(metadata_batch.stats,derivation_elapsed_seconds=round(time.monotonic()-(deadline-180),3),
                                derivation_deadline_seconds=180,payload_or_full_wal_selected_by_batch=False)
        (work/'hourly-recovery.json').write_text(json.dumps(edge_inventory))
        protected=json.loads((work/'protected.json').read_text())
        if not isinstance(protected,list):
            raise ValueError('Protected inventory must be an array')
        (work/'protected.json').write_text(json.dumps(sorted(set(protected)|parents)))
        for path,plan in zip(plan_paths,updated):
            path.write_text(json.dumps(plan))
        command=[sys.executable,str(ROOT/'retention-plan.py'),'--policy',str(work/'policy.json'),
                 '--inventory',str(work/'inventory.json'),'--protected',str(work/'protected.json'),
                 '--restore-evidence',str(work/'restored.json'),'--dependencies',str(work/'dependencies.json'),
                 '--hourly-recovery',str(work/'hourly-recovery.json'),
                 '--output',str(work/'candidate.json')]+plans
        run(command,env)
        # A parallel writer may change inventory: candidate must be regenerated, never applied.
        after=run(['restic','--no-lock','snapshots','--json'],env)
        normalize=lambda text:json.dumps(sorted(json.loads(text),key=lambda r:r['id']),sort_keys=True,separators=(',',':'))
        result=json.loads((work/'candidate.json').read_text())
        stable=normalize(inventory)==normalize(after)
        if not stable:
            before_rows={r['id']:r for r in json.loads(inventory)}
            after_rows={r['id']:r for r in json.loads(after)}
            append_only=all(sid in after_rows and row==after_rows[sid]for sid,row in before_rows.items())
            if result['remove_snapshot_ids']or not append_only:
                raise ValueError('Repository inventory changed during audit; retry candidate without deletion')
            # A read-only zero-removal observation may finish while working
            # backups append snapshots. No old or new point is modified.
        result['inventory_stable_for_admission']=stable
        result['append_only_new_snapshots_observed']=not stable
        result['hourly_metadata_read']=metadata_read_proof
        if result.get('apply_ready') is not False:
            raise ValueError('Read-only planner must never authorize apply')
        # Optional private handoff to the separate manual admission wrapper.
        # This exports a read-only candidate, never a deletion authorization.
        export=os.environ.get('NEO_RETENTION_CANDIDATE_OUTPUT')
        if export:
            destination=Path(export)
            runner=Path(os.environ['RUNNER_TEMP']).resolve()
            parent=destination.parent.resolve()
            if (not parent.is_relative_to(runner) or parent==runner
                or parent.stat().st_mode & 0o777 != 0o700 or destination.exists()
                or destination.is_symlink()):
                raise ValueError('Candidate export requires a new private runner-temporary file')
            destination.write_text(json.dumps(result))
            destination.chmod(0o600)
        bundle_output=os.environ.get('NEO_RETENTION_VALIDATION_BUNDLE_OUTPUT')
        if bundle_output:
            destination=Path(bundle_output);runner=Path(os.environ['RUNNER_TEMP']).resolve()
            parent=destination.parent.resolve()
            if (not parent.is_relative_to(runner)or parent==runner or parent.stat().st_mode&0o777!=0o700
                or destination.exists()or destination.is_symlink()):
                raise ValueError('Validation bundle requires a new private runner-temporary file')
            bundle={'schema':1,'validated_epoch':int(time.time()),'policy':policy,
                'inventory':json.loads(inventory),'plans':[json.loads(p.read_text())for p in plan_paths],
                'protected':json.loads((work/'protected.json').read_text()),
                'restored':json.loads((work/'restored.json').read_text()),
                'dependencies':json.loads((work/'dependencies.json').read_text()),
                'hourly_recovery':edge_inventory,'candidate':result}
            destination.write_text(json.dumps(bundle));destination.chmod(0o600)
        print(json.dumps({'candidate_only':True,'deletion_performed':False,
                          'hourly_metadata_batches':metadata_batch.stats['native_batches'],
                          'hourly_metadata_checkpoint_reads':metadata_batch.stats['checkpoint_reads'],
                          'hourly_selected_metadata_bytes':metadata_batch.stats['selected_json_bytes'],
                          'remove_candidates':len(result['remove_snapshot_ids']),
                          'retained':len(result['retained_snapshot_ids']),
                          'protected':len(result['protected_snapshot_ids']),
                          'protected_unknown_hourly_points':result.get('protected_unknown_hourly_points',0),
                          'inventory_stable_for_admission':stable,
                          'fresh_fenced_replan_required_before_apply':True}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Do not echo restic errors, private filenames, key values or inventory records.
        print('::error::Offsite retention audit failed closed ('+type(exc).__name__+'); no deletion performed',file=sys.stderr)
        raise SystemExit(1)
