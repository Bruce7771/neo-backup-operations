#!/usr/bin/env python3
"""Real off-VPS read-only plan, native integrity check and limited restore.

Zero candidates is an honest no-op. UNKNOWN holds remain explicitly unknown.
No fence, schedule pause, mutation key, forget/prune or raw B2 API is used.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from retention_postcheck import validate,restore

ROOT=Path(__file__).resolve().parent


def main():
    os.umask(0o077);env=dict(os.environ)
    if any(value for key,value in env.items()if'MASTER'in key.upper()):raise ValueError('Master credentials forbidden')
    policy=json.loads(env['NEO_POLICY_JSON'])
    with tempfile.TemporaryDirectory(prefix='neo-retention-readonly-',dir=env['RUNNER_TEMP'])as tmp:
        work=Path(tmp);work.chmod(0o700);candidate_path=work/'candidate.json'
        audit=dict(env,NEO_RETENTION_CANDIDATE_OUTPUT=str(candidate_path))
        with tempfile.TemporaryFile(dir=work)as out,tempfile.TemporaryFile(dir=work)as errors:
            subprocess.run([sys.executable,str(ROOT/'retention-audit.py')],env=audit,stdin=subprocess.DEVNULL,
                stdout=out,stderr=errors,check=True,timeout=240)
        candidate=json.loads(candidate_path.read_text())
        if candidate.get('apply_ready')is not False:raise ValueError('Read-only candidate unexpectedly authorizes mutation')
        validate(candidate,policy)
        password=work/'password';password.write_text(env['NEO_RESTIC_PASSWORD']);password.chmod(0o600)
        spec=importlib.util.spec_from_file_location('readonly_restic',ROOT/'maintenance-access-check.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.repository_target(env['RESTIC_REPOSITORY'])
        native={k:v for k,v in env.items()if not k.startswith(('NEO_','AWS_','RESTIC_'))}
        native.update(RESTIC_REPOSITORY=env['RESTIC_REPOSITORY'],RESTIC_PASSWORD_FILE=str(password),
            AWS_ACCESS_KEY_ID=env['AWS_ACCESS_KEY_ID'],AWS_SECRET_ACCESS_KEY=env['AWS_SECRET_ACCESS_KEY'])
        if env.get('AWS_DEFAULT_REGION'):native['AWS_DEFAULT_REGION']=env['AWS_DEFAULT_REGION']
        def call(arguments):return module.restic_output(arguments,native,work,maximum=2*1024*1024,
            timeout=180 if arguments[-1]=='check'else 90)
        if not call(['version']).decode().startswith('restic 0.16.4 '):raise ValueError('Unexpected restic version')
        # Read-only native check: no new repo lock and no full data reread.
        call(['--no-cache','--no-lock','check'])
        result=restore(candidate,policy,work,call)
        print(json.dumps({'scope':'independent-retention-readonly-check',
            'hourly_metadata_read':candidate.get('hourly_metadata_read'),
            'retained_snapshots':len(candidate['retained_snapshot_ids']),
            'protected_snapshots':len(candidate['protected_snapshot_ids']),
            'protected_unknown_hourly_points':candidate.get('protected_unknown_hourly_points',0),
            'removal_candidates':len(candidate['remove_snapshot_ids']),
            'zero_candidate_noop':not candidate['remove_snapshot_ids'],
            'inventory_stable_for_admission':candidate.get('inventory_stable_for_admission',False),
            'repository_integrity_check':True,**result,'fence_acquired':False,
            'backup_schedules_changed':False,'deleted_snapshots':0,'prune_performed':False,
            'expiration_path_exercised':False}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('::error::Read-only retention check failed closed ('+type(error).__name__+'); no deletion or fence',file=sys.stderr)
        raise SystemExit(1)
