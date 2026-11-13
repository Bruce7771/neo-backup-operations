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

def safe_audit_failure(raw):
    """Forward only reviewed structured diagnostics, never raw child stderr."""
    prefix='NEO_RETENTION_SAFE_FAILURE '
    for line in raw.decode('utf8',errors='replace').splitlines():
        if not line.startswith(prefix):continue
        try:value=json.loads(line[len(prefix):])
        except ValueError:continue
        allowed={'failure_type','phase','source_module','source_line','metadata_stats','derive_elapsed_seconds'}
        if not isinstance(value,dict)or set(value)-allowed:continue
        if value.get('phase')not in('initialize','inventory','native-plans','derive-metadata','validate-candidate','final-inventory'):continue
        if value.get('source_module')not in('retention-audit.py','hourly_metadata_batch.py','hourly_recovery.py','hourly_selfcontained_v3.py','asof_recovery_hold.py',None):continue
        if value.get('failure_type')not in('ValueError','TimeoutError','TimeoutExpired','CalledProcessError',
                'FileNotFoundError','KeyError','AssertionError','TypeError','JSONDecodeError','OSError'):continue
        if value.get('source_line')is not None and not(type(value['source_line'])is int and 0<value['source_line']<10000):continue
        stats=value.get('metadata_stats',{})
        if not isinstance(stats,dict)or set(stats)-{'native_batches','checkpoint_reads','selected_json_bytes','v3_points_authenticated'}:continue
        if any(type(n)is not int or n<0 for n in stats.values()):continue
        if 'derive_elapsed_seconds'in value and not(type(value['derive_elapsed_seconds'])in(int,float)and 0<=value['derive_elapsed_seconds']<3600):continue
        return value
    return None


def main():
    os.umask(0o077);env=dict(os.environ)
    if any(value for key,value in env.items()if'MASTER'in key.upper()):raise ValueError('Master credentials forbidden')
    policy=json.loads(env['NEO_POLICY_JSON'])
    with tempfile.TemporaryDirectory(prefix='neo-retention-readonly-',dir=env['RUNNER_TEMP'])as tmp:
        work=Path(tmp);work.chmod(0o700);candidate_path=work/'candidate.json'
        audit=dict(env,NEO_RETENTION_CANDIDATE_OUTPUT=str(candidate_path))
        with tempfile.TemporaryFile(dir=work)as out,tempfile.TemporaryFile(dir=work)as errors:
            try:
                subprocess.run([sys.executable,str(ROOT/'retention-audit.py')],env=audit,stdin=subprocess.DEVNULL,
                    stdout=out,stderr=errors,check=True,timeout=240)
            except subprocess.CalledProcessError:
                errors.seek(0);diagnostic=safe_audit_failure(errors.read(16384))
                if diagnostic is not None:print(json.dumps({'audit_safe_failure':diagnostic}),file=sys.stderr)
                raise
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
