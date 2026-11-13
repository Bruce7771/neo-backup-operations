#!/usr/bin/env python3
"""Prepared manual-only maintenance. Current planner cannot authorize deletion.

All operational inventories stay in private runner-temporary files. No master
credential, B2 version-purge API, arbitrary SSH command or blind unlock is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

HEX=re.compile(r'^[0-9a-f]{64}$')
ROOT=Path(__file__).resolve().parent


class GateClosed(Exception):pass


def require(ok,reason):
    if not ok:raise GateClosed(reason)


def digest(candidate):
    # Exclude admission state; bind the actual immutable inventory/removal/DAG.
    keys=('inventory_sha256','remove_snapshot_ids','protected_snapshot_ids',
          'retained_snapshot_ids','protected_child_parent_dependencies',
          'hourly_recovery_dependencies')
    return hashlib.sha256(json.dumps({k:candidate[k]for k in keys},sort_keys=True,separators=(',',':')).encode()).hexdigest()


def bounded(argv,env,timeout,input=None):
    """Timeout kills the whole local subprocess group before lease release."""
    process=subprocess.Popen(argv,env=env,stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        out,_=process.communicate(input,timeout=timeout)
        require(process.returncode==0,'bounded-command-failed')
        return out
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.communicate(timeout=2)
        raise GateClosed('bounded-command-timeout-no-blind-unlock')


def fresh_writer_proof(status,now):
    # Current deployed status lacks these fields and therefore fails closed.
    inventory=status.get('writer_inventory',{})
    require(inventory.get('complete')is True and inventory.get('unknown_writers')==[],
            'fresh-real-writer-inventory-interface-not-available')
    require(0<=now-inventory.get('observed_epoch',0)<=30,'writer-inventory-stale')
    require(set(inventory.get('reviewed_sources',[]))=={'systemd','cron','manual_sessions','external_runners'},
            'writer-inventory-sources-incomplete')
    require(isinstance(inventory.get('repository_id'),str)and inventory['repository_id'],
            'writer-inventory-repository-not-bound')
    return inventory


def admission(candidate,expected,maximum,lease,now,proof):
    remove=candidate.get('remove_snapshot_ids',[])
    require(candidate.get('apply_ready')is True,'planner-is-read-only-no-apply-admission')
    require(HEX.fullmatch(expected or'')is not None and digest(candidate)==expected,'reviewed-candidate-digest-mismatch')
    require(0<len(remove)<=maximum<=10 and len(remove)==len(set(remove)), 'removal-count-outside-reviewed-bound')
    require(all(isinstance(x,str)and HEX.fullmatch(x)for x in remove),'invalid-removal-id')
    require(not set(remove)&set(candidate['protected_snapshot_ids']),'protected-snapshot-selected')
    require(set(remove).isdisjoint(candidate['retained_snapshot_ids']),'retained-snapshot-selected')
    require(lease.get('phase')=='held'and 90<=lease.get('expires_epoch',0)-now<=300,'lease-not-held-or-budget-too-small')
    binding=candidate.get('admission',{})
    require(binding.get('writer_inventory_repository_id')==proof['repository_id']
            and binding.get('writer_inventory_observed_epoch')==proof['observed_epoch']
            and binding.get('lease_expires_epoch')==lease['expires_epoch']
            and binding.get('retained_dependency_closure_verified')is True,
            'reviewed-lease-bound-admission-validator-missing')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('plan','apply'),default='plan')
    parser.add_argument('--expected-digest',default='')
    parser.add_argument('--maximum-removals',type=int,default=0)
    parser.add_argument('--prune',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    require(not any(value for key,value in os.environ.items()if 'MASTER' in key.upper()),'master-credentials-forbidden')
    env=dict(os.environ);policy=json.loads(env['NEO_POLICY_JSON'])
    with tempfile.TemporaryDirectory(prefix='neo-retention-manual-',dir=env['RUNNER_TEMP'])as tmp:
        work=Path(tmp);work.chmod(0o700)
        password=work/'repository-password'
        password.write_text(env['NEO_RESTIC_PASSWORD']);password.chmod(0o600)
        native=dict(env,RESTIC_PASSWORD_FILE=str(password),XDG_CACHE_HOME=str(work/'cache'))
        for key in list(native):
            if key.startswith('NEO_') or key in('RESTIC_PASSWORD','RESTIC_PASSWORD_COMMAND','AWS_SESSION_TOKEN',
                'AWS_SECURITY_TOKEN','AWS_PROFILE','AWS_CONFIG_FILE','AWS_SHARED_CREDENTIALS_FILE'):
                native.pop(key,None)
        def plan(name,limit=205):
            destination=work/name
            current={k:v for k,v in env.items()if k not in
                ('NEO_MAINTENANCE_SSH_KEY','NEO_MAINTENANCE_SSH_KNOWN_HOSTS')}
            current['NEO_RETENTION_CANDIDATE_OUTPUT']=str(destination)
            bounded([sys.executable,str(ROOT/'retention-audit.py')],current,limit)
            return json.loads(destination.read_text())
        first=plan('candidate-before.json')
        print(json.dumps({'candidate_digest':digest(first),'remove_candidates':len(first['remove_snapshot_ids']),
                          'candidate_only':True,'deletion_performed':False}))
        if args.mode=='plan':return
        # Honest no-op: do not fence, forget or prune merely to demonstrate work.
        if not first['remove_snapshot_ids']:
            print(json.dumps({'result':'no-op-zero-candidates','deletion_performed':False,'prune_performed':False}));return
        require(env.get('NEO_BACKUP_APPLY_ENABLED')=='true','manual-apply-kill-switch-closed')
        require(first.get('apply_ready')is True,'planner-is-read-only-no-apply-admission')
        # No false promotion of apply_ready:false, no secret can bypass this gate.
        ssh=policy.get('maintenance_ssh',{})
        target=ssh.get('target','')
        require(re.fullmatch(r'root@[A-Za-z0-9.:-]+',target)is not None,'explicit-private-ssh-target-missing')
        key=work/'ssh-key';key.write_text(env['NEO_MAINTENANCE_SSH_KEY']);key.chmod(0o600)
        hosts=work/'known-hosts';hosts.write_text(env['NEO_MAINTENANCE_SSH_KNOWN_HOSTS']);hosts.chmod(0o600)
        command=['ssh','-F','/dev/null','-T','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
                 '-o','ConnectTimeout=8','-o','UserKnownHostsFile='+str(hosts),'-i',str(key),target]
        ssh_env={k:env[k]for k in('PATH','HOME','LANG','LC_ALL','TMPDIR')if k in env}
        def remote(literal,input=None,limit=20):
            require(literal in('status','acquire 300','release'),'unreviewed-ssh-command')
            return json.loads(bounded(command+[literal],ssh_env,limit,input))
        proof=fresh_writer_proof(remote('status'),time.time())
        lease=None
        try:
            lease=remote('acquire 300',limit=200)
            require(HEX.fullmatch(lease.get('lease',''))is not None,'private-lease-token-missing')
            deadline=time.monotonic()+min(300,lease['expires_epoch']-time.time())
            def remaining(reserve=30):
                value=deadline-time.monotonic()-reserve
                require(value>0,'lease-budget-exhausted');return value
            second=plan('candidate-fenced.json',min(180,remaining(100)))
            admission(second,args.expected_digest,args.maximum_removals,lease,time.time(),proof)
            require(digest(second)==digest(first),'candidate-changed-inside-fence-reapproval-required')
            require(not args.prune or env.get('NEO_REPOSITORY_WIDE_PRUNE_REVIEWED')=='true',
                    'restic-prune-is-repository-wide-needs-explicit-review')
            validate_restore_contract(second,policy)
            # Existing native restic locks stay enabled. Exact IDs only; never
            # let forget re-evaluate a broad policy while deleting.
            remove=second['remove_snapshot_ids']
            bounded(['restic','forget','--json']+remove,native,min(25,remaining(90)))
            if args.prune:
                bounded(['restic','prune','--max-repack-size','16M'],native,min(60,remaining(80)))
            bounded(['restic','check'],native,min(35,remaining(45)))
            limited_restore(second,policy,work,native,min(30,remaining(15)))
            print(json.dumps({'result':'bounded-manual-maintenance-checked','forgotten':len(remove),
                              'prune_performed':args.prune,'full_database_or_media_restore_claimed':False}))
        finally:
            if lease and HEX.fullmatch(lease.get('lease','')):
                released=remote('release',(lease['lease']+'\n').encode(),limit=20)
                require(released.get('released')is True,'release-unconfirmed-owner-reconciliation-required')


def validate_restore_contract(candidate,policy):
    contract=policy.get('maintenance_postcheck',{})
    sid=contract.get('snapshot');path=contract.get('path','');checksum=contract.get('sha256','')
    require(sid in candidate['retained_snapshot_ids']and sid in candidate['protected_snapshot_ids']
            and HEX.fullmatch(sid or'')is not None,'postcheck-point-not-retained-and-protected')
    require(isinstance(path,str)and path.startswith('/')and'..'not in Path(path).parts
            and not any(character in path for character in '*?[]')
            and HEX.fullmatch(checksum or'')is not None,'reviewed-postcheck-file-missing')
    roots=[root.rstrip('/')for scope in policy['scopes']for root in scope['paths']]
    require(any(path.startswith(root+'/')for root in roots),'postcheck-path-outside-reviewed-roots')
    require(contract.get('kind')=='sqlite'and 0<contract.get('bytes',0)<=16*1024*1024,
            'postcheck-component-outside-16MiB-bound')
    return contract


def limited_restore(candidate,policy,work,env,timeout):
    """One bounded retained SQLite component, never a claimed full Neo restore."""
    contract=validate_restore_contract(candidate,policy)
    sid=contract['snapshot'];path=contract['path'];checksum=contract['sha256']
    target=work/'restore';target.mkdir(mode=0o700)
    bounded(['restic','restore','--verify','--include',path,'--target',str(target),sid],env,timeout)
    restored=target/path.lstrip('/')
    require(restored.is_file()and not restored.is_symlink()and restored.stat().st_size==contract['bytes'],
            'postcheck-file-not-restored')
    with restored.open('rb')as handle:require(hashlib.file_digest(handle,'sha256').hexdigest()==checksum,'postcheck-sha-mismatch')
    with sqlite3.connect(restored.as_uri()+'?mode=ro&immutable=1',uri=True)as db:
        require(db.execute('PRAGMA quick_check').fetchall()==[('ok',)],'postcheck-sqlite-corrupt')


if __name__=='__main__':
    try:main()
    except Exception as error:
        # Reason codes contain no inventories, tokens or subprocess stderr.
        reason=str(error)if isinstance(error,GateClosed)else type(error).__name__
        print('::error::Manual maintenance stopped: '+reason+'; inspect private lease/lock status before retry',file=sys.stderr)
        raise SystemExit(1)
