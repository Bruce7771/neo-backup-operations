"""Offline candidate contract tests. No network, credentials, B2 or live process."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


c = load('candidate_test', HERE / 'publication-retention-coordinator.candidate.py')
core = load('actual_core_test', HERE / 'publication-coordinator-core.proposed.py')


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        workflow = self.root / '.github/workflows/retention-manual.yml'
        workflow.parent.mkdir(parents=True)
        workflow.write_bytes(b'concurrency:\n  group: backup-repository-maintenance\n  cancel-in-progress: false\nenvironment: NEO_BACKUP_MAINTENANCE\n')
        self.policy = {'schema': 1}; self.static = {'protected': [], 'restored': [], 'dependencies': [], 'hourly_overrides': []}
        self.approval = dict(schema=1, reviewed=True, executor_sha='a'*40,
            policy_sha256=c.sha(self.policy), static_sha256=c.sha(self.static), maximum_removals=10,
            workflow_sha256=hashlib.sha256(workflow.read_bytes()).hexdigest(), producer_policy_sha256='b'*64)
        self.env = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY='Bruce7771/neo-backup-operations',
            GITHUB_REF='refs/heads/main', GITHUB_JOB='manual', GITHUB_EVENT_NAME='workflow_dispatch',
            GITHUB_WORKFLOW_REF='Bruce7771/neo-backup-operations/.github/workflows/retention-manual.yml@refs/heads/main',
            GITHUB_SHA='a'*40, GITHUB_WORKSPACE=str(self.root), NEO_RETENTION_APPLY_CONTRACT_JSON=json.dumps(self.approval))
        self.protection = dict(name='NEO_BACKUP_MAINTENANCE', can_admins_bypass=False,
                               deployment_branch_policy={'custom_branch_policies': True})
        self.branches = dict(total_count=1, branch_policies=[{'name': 'main', 'type': 'branch'}])

    def tearDown(self): self.tmp.cleanup()
    def fetch(self, url): return self.branches if '/deployment-branch-policies?' in url else self.protection
    def contract(self): return c.execution_contract(self.env, self.policy, self.static, self.fetch)
    def test_reviewed_contract(self): self.assertEqual(self.contract(), self.approval)
    def test_audit_job_cannot_receive_authority(self):
        self.env['GITHUB_JOB'] = 'audit'
        with self.assertRaises(ValueError): self.contract()
    def test_source_drift(self):
        self.env['GITHUB_SHA'] = 'c'*40
        with self.assertRaises(ValueError): self.contract()
    def test_policy_drift(self):
        self.policy['changed'] = True
        with self.assertRaises(ValueError): self.contract()
    def test_static_drift(self):
        self.static['protected'] = ['d'*64]
        with self.assertRaises(ValueError): self.contract()
    def test_workflow_drift(self):
        (self.root / '.github/workflows/retention-manual.yml').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.contract()
    def test_admin_bypass(self):
        self.protection['can_admins_bypass'] = True
        with self.assertRaises(ValueError): self.contract()
    def test_wildcard_branch(self):
        self.branches['branch_policies'][0]['name'] = '*'
        with self.assertRaises(ValueError): self.contract()
    def test_no_auto_chunk(self):
        with self.assertRaises(ValueError): c.admit_mode('policy-apply', {'remove_snapshot_ids': ['x']*11}, self.approval,
            {'NEO_BACKUP_APPLY_ENABLED': 'true'}, 'digest', '')
    def test_policy_apply_no_repeated_human_digest(self):
        c.admit_mode('policy-apply', {'remove_snapshot_ids': ['x']}, self.approval,
            {'NEO_BACKUP_APPLY_ENABLED': 'true'}, 'fresh-reviewed-policy-result', '')
    def test_manual_exact_review(self):
        with self.assertRaises(ValueError): c.admit_mode('apply', {'remove_snapshot_ids': ['x']}, self.approval,
            {'NEO_BACKUP_APPLY_ENABLED': 'true'}, 'correct', 'wrong')
    def test_disabled_apply(self):
        with self.assertRaises(ValueError): c.admit_mode('policy-apply', {'remove_snapshot_ids': ['x']}, self.approval, {}, 'd', '')
    def test_plan_and_zero_do_not_require_switch(self):
        c.admit_mode('plan', {'remove_snapshot_ids': ['x']}, self.approval, {}, 'd', '')
        c.admit_mode('policy-apply', {'remove_snapshot_ids': []}, self.approval, {}, 'd', '')
    def test_ssh_env_has_no_b2_or_policy_or_master(self):
        env = {'PATH': '/bin', 'AWS_ACCESS_KEY_ID': 'fixture', 'NEO_MAINTENANCE_SSH_KEY': 'fixture',
               'RESTIC_REPOSITORY': 'fixture', 'NEO_POLICY_JSON': 'fixture', 'MASTER': 'fixture'}
        self.assertEqual(c.subprocess_environment(env), {'PATH': '/bin'})
    def test_hourly_thirty_days_unchanged(self):
        safety = load('actual_safety_test', HERE / 'retention-safety-candidate.py')
        self.assertEqual(safety.scoped_rule_suffix({'kind': 'hourly'}),
            ['--keep-within', '30d', '--keep-daily', '30', '--keep-monthly', '3'])
    def test_default_plan_no_prune_parser(self):
        source = (HERE / 'publication-retention-coordinator.candidate.py').read_text(encoding='utf-8')
        self.assertIn("default='plan'", source)
        self.assertNotIn("add_argument('--prune'", source)
        self.assertIn("call(['check'], 150)", source)
    def test_launcher_uses_actual_family_same_job_builder(self):
        source = (HERE / 'run-publication-retention.candidate.py').read_text(encoding='utf-8')
        self.assertIn('build-same-job-tail-retention-engine.proposed.py', source)
        builder = (HERE / 'build-same-job-tail-retention-engine.proposed.py').read_text(encoding='utf-8')
        self.assertIn('build-unverified-base-family-retention-engine.proposed.py', builder)
    def test_fresh_external_aggregate_deadline(self):
        self.assertEqual(c.external_seconds(0, None), 25)
        self.assertEqual(c.external_seconds(40, 0), 4)
        with self.assertRaises(ValueError): c.external_seconds(45, 0)
    def test_checkout_untracked_executable_refused(self):
        def bounded(argv, env, timeout):
            if 'rev-parse' in argv: return ('a'*40+'\n').encode()
            if 'ls-files' in argv: return b'proposals/unreviewed.py\n'
            return b''
        with self.assertRaises(ValueError): c.verify_checkout(self.env, bounded)
    def test_checkout_exact_and_clean(self):
        calls = []
        def bounded(argv, env, timeout):
            calls.append(argv)
            return ('a'*40+'\n').encode() if 'rev-parse' in argv else b''
        c.verify_checkout(self.env, bounded)
        self.assertEqual(len(calls), 3)
    def test_actual_staged_engine_native_defaults_and_thirty_compiled_modules(self):
        launcher = load('actual_candidate_launcher', HERE / 'run-publication-retention.candidate.py')
        with tempfile.TemporaryDirectory() as tmp:
            engine = launcher.build_engine(HERE, Path(tmp) / 'engine')
            modules = list(engine.glob('*.py'))
            self.assertEqual(len(modules), 30)
            for module in modules: compile(module.read_text(encoding='utf-8'), str(module), 'exec')
            audit = (engine / 'retention-audit.py').read_text(encoding='utf-8')
            self.assertNotIn('--no-lock', audit)
            self.assertIn('all_classified_hourly_recovery', audit)
            self.assertIn('accepted_restore_base_sha256', audit)


class ActualCoreBoundaryTests(unittest.TestCase):
    def exercise(self, *, zero=False, fail_native=False, changed=False):
        events = []; sid = 'a'*64
        candidate = dict(remove_snapshot_ids=[sid], apply_ready=False, retained_snapshot_ids=[],
                         protected_snapshot_ids=[], inventory_stable_for_admission=True)
        class RPC:
            def acquire(self, *a, **kw): events.append('hold')
            def release(self, *a, **kw): events.append('release')
            def begin_forget(self, *a, **kw): events.append('begin')
            def acknowledge(self, *a, **kw): events.append('ack-ok' if kw['native_exit_zero'] else 'ack-unknown')
        def fresh(deadline):
            events.append('fresh')
            result = dict(candidate, remove_snapshot_ids=[] if zero else [sid])
            if changed: result['remove_snapshot_ids'] = ['b'*64]
            return result, [{'id': sid}]
        def native(ids, timeout):
            events.append('forget')
            self.assertEqual(ids, [sid]); self.assertLessEqual(timeout, 60)
            if fail_native: raise RuntimeError('fixture uncertain native outcome')
        def post(c): events.append('check'); return {'checked': True}
        try:
            result = core.execute(candidate, sid, lambda c: c['remove_snapshot_ids'][0] if c['remove_snapshot_ids'] else '',
                'c'*64, RPC(), fresh, native, lambda timeout: [], post, now=lambda: 0)
            return result, events
        except (RuntimeError, ValueError): return None, events
    def test_native_only_after_fresh_hold_and_check_after_release(self):
        result, events = self.exercise()
        self.assertEqual(events, ['hold', 'fresh', 'begin', 'forget', 'ack-ok', 'release', 'check'])
        self.assertEqual(result['deleted_snapshots'], 1); self.assertFalse(result['prune'])
    def test_uncertain_native_never_blind_release(self):
        result, events = self.exercise(fail_native=True)
        self.assertIsNone(result); self.assertEqual(events[-1], 'ack-unknown')
        self.assertNotIn('release', events); self.assertNotIn('check', events)
    def test_changed_removal_set_release_without_native(self):
        result, events = self.exercise(changed=True)
        self.assertIsNone(result); self.assertEqual(events, ['hold', 'fresh', 'release'])
    def test_fresh_zero_no_native(self):
        result, events = self.exercise(zero=True)
        self.assertEqual(events, ['hold', 'fresh', 'release']); self.assertEqual(result['deleted_snapshots'], 0)


if __name__ == '__main__': unittest.main()
