#!/usr/bin/env python3
"""SOURCE ONLY: existing maintenance job + native family engine + restricted RPC.

Default PLAN. No prune, scheduler, service, key creation or workflow registration.
Policy-apply is admission of an unchanged reviewed policy, not a planner flag flip.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Refused(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def require(value, reason):
    if not value:
        raise Refused(reason)


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def static_inputs(env):
    return {name: json.loads(env[key]) for name, key in (
        ('protected', 'NEO_PROTECTED_JSON'), ('restored', 'NEO_RESTORED_JSON'),
        ('dependencies', 'NEO_DEPENDENCIES_JSON'), ('hourly_overrides', 'NEO_HOURLY_RECOVERY_JSON'))}


def execution_contract(env, policy, static, fetch):
    """Actual dedicated job and public protection metadata, never caller booleans."""
    approval = json.loads(env['NEO_RETENTION_APPLY_CONTRACT_JSON'])
    expected = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'Bruce7771/neo-backup-operations',
                'GITHUB_REF': 'refs/heads/main', 'GITHUB_JOB': 'manual',
                'GITHUB_WORKFLOW_REF': 'Bruce7771/neo-backup-operations/.github/workflows/retention-manual.yml@refs/heads/main'}
    require(all(env.get(k) == v for k, v in expected.items()), 'Dedicated protected maintenance job required')
    require(env.get('GITHUB_EVENT_NAME') in ('workflow_dispatch', 'schedule'), 'Reviewed maintenance event required')
    commit = env.get('GITHUB_SHA', '')
    require(re.fullmatch('[0-9a-f]{40}', commit) and approval.get('executor_sha') == commit,
            'Exact reviewed executor required')
    require(approval.get('schema') == 1 and approval.get('reviewed') is True
            and approval.get('policy_sha256') == sha(policy) and approval.get('static_sha256') == sha(static)
            and type(approval.get('maximum_removals')) is int and 1 <= approval['maximum_removals'] <= 10,
            'Policy/static review drift or removal bound')
    root = Path(env['GITHUB_WORKSPACE']).resolve()
    workflow = root / '.github/workflows/retention-manual.yml'
    require(not workflow.is_symlink() and workflow.is_file(), 'Registered maintenance workflow required')
    raw = workflow.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == approval.get('workflow_sha256'), 'Reviewed workflow bytes changed')
    # These are required in addition to the exact reviewed complete-file digest.
    text = raw.decode('utf-8')
    require('group: backup-repository-maintenance' in text and 'cancel-in-progress: false' in text
            and 'environment: NEO_BACKUP_MAINTENANCE' in text, 'Serialized protected job required')
    base = 'https://api.github.com/repos/Bruce7771/neo-backup-operations/environments/NEO_BACKUP_MAINTENANCE'
    protection = fetch(base)
    require(protection.get('name') == 'NEO_BACKUP_MAINTENANCE'
            and protection.get('can_admins_bypass') is False
            and protection.get('deployment_branch_policy', {}).get('custom_branch_policies') is True,
            'Environment bypass/branch protection differs')
    branches = fetch(base + '/deployment-branch-policies?per_page=100')
    rows = branches.get('branch_policies')
    require(branches.get('total_count') == 1 and isinstance(rows, list) and len(rows) == 1
            and rows[0].get('name') == 'main' and rows[0].get('type', 'branch') == 'branch',
            'Exact main-only environment required')
    return approval


def admit_mode(mode, candidate, approval, env, review, expected):
    require(mode in ('plan', 'apply', 'policy-apply'), 'Unknown mode')
    if mode == 'plan' or not candidate['remove_snapshot_ids']:
        return
    require(env.get('NEO_BACKUP_APPLY_ENABLED') == 'true', 'Apply remains disabled')
    require(0 < len(candidate['remove_snapshot_ids']) <= approval['maximum_removals'],
            'More than reviewed bounded batch: HOLD, no automatic chunking')
    if mode == 'apply':
        require(expected == review, 'Exact removal review differs')
    # policy-apply uses the fixed reviewed policy/static/executor/workflow tuple.
    # Existing core still compares this actual removal digest after fresh replan.


def subprocess_environment(env, native=False):
    allowed = ('PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'RUNNER_TEMP', 'SSL_CERT_FILE', 'SSL_CERT_DIR')
    result = {k: env[k] for k in allowed if k in env}
    if native:
        result.update({k: env[k] for k in ('RESTIC_REPOSITORY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
                                         'RESTIC_PASSWORD_FILE', 'XDG_CACHE_HOME')})
        if env.get('AWS_DEFAULT_REGION'):
            result['AWS_DEFAULT_REGION'] = env['AWS_DEFAULT_REGION']
    return result


def verify_checkout(env, bounded):
    process_env = subprocess_environment(env)
    prefix = ['git', '-C', env['GITHUB_WORKSPACE']]
    require(bounded(prefix + ['rev-parse', 'HEAD'], process_env, 10).decode().strip() == env['GITHUB_SHA'],
            'Checkout commit differs from reviewed executor')
    bounded(prefix + ['diff', '--exit-code', 'HEAD', '--', 'scripts', 'proposals', '.github/workflows'], process_env, 10)
    require(not bounded(prefix + ['ls-files', '--others', '--exclude-standard', '--', 'scripts', 'proposals', '.github/workflows'], process_env, 10).strip(),
            'Untracked executable source in reviewed checkout')


def external_seconds(now, hold_started):
    left = 25 if hold_started is None else min(25, hold_started + 44 - now)
    require(left > 0, 'Fresh external admission deadline exhausted')
    return left


def timed_external(action, seconds):
    """GHA Linux main thread: one aggregate bound across public metadata calls."""
    require(hasattr(signal, 'setitimer'), 'Bounded Linux external observer required')
    def expired(signum, frame):
        raise Refused('External admission time budget exhausted')
    previous = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, expired)
    old_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return action()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if old_timer[0]: signal.setitimer(signal.ITIMER_REAL, *old_timer)


def main(engine, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('plan', 'apply', 'policy-apply'), default='plan')
    parser.add_argument('--expected-digest', default='')
    args = parser.parse_args(argv)
    os.umask(0o077)
    env = dict(os.environ)
    require(not any(v for k, v in env.items() if 'MASTER' in k.upper()), 'Master credentials forbidden')
    require(not env.get('NEO_EXTERNAL_READER_MODE'), 'Dedicated maintenance job uses default native locks')
    policy = json.loads(env['NEO_POLICY_JSON']); static = static_inputs(env)
    observer = load('candidate_external_observer', HERE / 'external_writer_observation.py')
    approval = execution_contract(env, policy, static, observer.get)
    bounded = load('candidate_bounded', ROOT / 'scripts/retention-manual.py').bounded
    verify_checkout(env, bounded)
    access = load('candidate_access', ROOT / 'scripts/maintenance-access-check.py')
    wiring = load('candidate_wiring', HERE / 'publication-existing-coordinator.proposed.py')
    review_fn = load('candidate_review', HERE / 'lease_admission.py').removal_review_digest
    post = load('candidate_postcheck', ROOT / 'scripts/retention_postcheck.py')
    with tempfile.TemporaryDirectory(prefix='neo-publication-maintenance-', dir=env['RUNNER_TEMP']) as tmp:
        work = Path(tmp); work.chmod(0o700)
        password = work / 'password'; password.write_text(env['NEO_RESTIC_PASSWORD']); password.chmod(0o600)
        env.update(RESTIC_PASSWORD_FILE=str(password), XDG_CACHE_HOME=str(work / 'cache'))
        native = subprocess_environment(env, native=True)
        def call(arguments, timeout=60):
            # Mutation never accepts --no-lock. All ordinary reads keep default SH.
            require('--no-lock' not in arguments, 'Native maintenance locks cannot be disabled')
            return bounded(['restic'] + arguments, native, timeout)
        require(call(['version'], 10).decode().startswith('restic 0.16.4 '), 'Pinned native restic required')
        bucket, endpoint, prefix = access.repository_target(env['RESTIC_REPOSITORY'])
        access.authorize_pair(env['AWS_ACCESS_KEY_ID'], env['AWS_SECRET_ACCESS_KEY'],
                              access.MAINTENANCE, bucket, endpoint, prefix)
        repository = json.loads(call(['cat', 'config']))['id']
        audit = dict(native, NEO_RESTIC_PASSWORD=env['NEO_RESTIC_PASSWORD'])
        for key in ('NEO_POLICY_JSON', 'NEO_PROTECTED_JSON', 'NEO_RESTORED_JSON', 'NEO_DEPENDENCIES_JSON', 'NEO_HOURLY_RECOVERY_JSON'):
            audit[key] = env[key]
        bundle_path = work / 'preplan.json'
        audit['NEO_RETENTION_VALIDATION_BUNDLE_OUTPUT'] = str(bundle_path)
        # Engine is built by the same-job FAMILY builder. No SSH credential enters preplan.
        bounded([sys.executable, str(Path(engine) / 'retention-audit.py')], audit, 4500)
        bundle = json.loads(bundle_path.read_text())
        planner = wiring.load('candidate_planner', Path(engine) / 'retention-plan.py')
        planner.SCOPES = {s['host']: (s['tag'], frozenset(s['paths'])) for s in policy['scopes']}
        planner.CONFIG_SCOPES = {(s['host'], s['tag']): s['paths'][0] for s in policy.get('configuration_scopes', [])}
        planner.FULL_MAIN_HOST = next(s['host'] for s in policy['scopes'] if s['kind'] == 'daily')
        fixed = wiring.load('candidate_asof', Path(engine) / 'asof_recovery_hold.py').fixed_hold
        candidate = wiring.revalidate(bundle, policy, static, planner, fixed)
        review = lambda c: review_fn(c, policy, env['GITHUB_SHA'], static)
        digest = review(candidate)
        checked = []
        def postcheck(current):
            post.validate(current, policy)
            call(['check'], 150)
            folder = work / ('post-' + secrets.token_hex(4)); folder.mkdir(mode=0o700)
            result = post.restore(current, policy, folder,
                lambda arguments: call([a for a in arguments if a != '--no-lock'], 90))
            checked.append(True)
            return dict(repository_integrity_check=True, **result)
        admit_mode(args.mode, candidate, approval, env, digest, args.expected_digest)
        if args.mode == 'plan':
            return dict(result='plan-only', removal_candidates=len(candidate['remove_snapshot_ids']),
                        review_digest=digest, deleted_snapshots=0, prune=False, **postcheck(candidate))
        # Zero candidates do not need SSH keys or a publication transition.
        if not candidate['remove_snapshot_ids']:
            return dict(result='zero-candidate-noop', deleted_snapshots=0, prune=False, **postcheck(candidate))
        target = policy.get('maintenance_ssh', {}).get('target', '')
        require(re.fullmatch(r'root@[A-Za-z0-9.:-]+', target), 'Reviewed restricted SSH target required')
        key = work / 'ssh-key'; key.write_text(env['NEO_MAINTENANCE_SSH_KEY']); key.chmod(0o600)
        hosts = work / 'known-hosts'; hosts.write_text(env['NEO_MAINTENANCE_SSH_KNOWN_HOSTS']); hosts.chmod(0o600)
        ssh = ['ssh', '-F', '/dev/null', '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
               '-o', 'ClearAllForwardings=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=8',
               '-o', 'UserKnownHostsFile=' + str(hosts), '-i', str(key), target]
        class TimedSSH(wiring.ExistingSSH):
            hold_started = None
            def acquire(self, *values, **budget):
                self.hold_started = time.monotonic()
                return super().acquire(*values, **budget)
        rpc = TimedSSH(ssh, subprocess_environment(env), bounded)
        def observe_external():
            execution_contract(env, policy, static, observer.get)
            status = rpc.status()
            require(status.get('schema') == 2 and status.get('repository_id') == repository
                    and status.get('writer_policy_sha256') == approval.get('producer_policy_sha256')
                    and status.get('local_inventory_complete') is True
                    and status.get('source_review_integrity') is True
                    and status.get('publication_producers_enrolled') is True
                    and not status.get('unknown_writer_units') and status.get('unknown_repository_clients') == 0,
                    'Actual publication producer/source inventory mismatch')
            evidence = observer.observe(policy['credential_holder_repositories'], env['GITHUB_REPOSITORY'], env['GITHUB_RUN_ID'])
            require(evidence['complete'] is True and evidence['other_running_jobs'] == 0,
                    'Other credential-holder job active or unknown')
        def external_admission():
            return timed_external(observe_external, external_seconds(time.monotonic(), rpc.hold_started))
        result = wiring.coordinate(bundle, engine, native, work, call, policy, static, rpc,
            approval['producer_policy_sha256'], digest, review, external_admission, postcheck)
        # Existing core fresh-zero releases cleanly but does not call postcheck.
        if result.get('result') == 'fresh-zero-noop' and not checked:
            result.update(postcheck(candidate))
        return result


if __name__ == '__main__':
    raise SystemExit('Use the separate reviewed launcher; no direct mutation entrypoint')
