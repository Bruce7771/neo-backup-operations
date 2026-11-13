#!/usr/bin/env python3
"""Synthetic gates only; no B2, SSH, credentials or real snapshots used."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('manual',Path(__file__).with_name('retention-manual.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Manual(unittest.TestCase):
    def candidate(self):
        return {'apply_ready':False,'inventory_sha256':'a'*64,'remove_snapshot_ids':['b'*64],
            'protected_snapshot_ids':['c'*64],'retained_snapshot_ids':['c'*64],
            'protected_child_parent_dependencies':[],'hourly_recovery_dependencies':[]}
    def proof(self):return {'complete':True,'unknown_writers':[],'observed_epoch':1000,
        'repository_id':'synthetic-repository','reviewed_sources':['systemd','cron','manual_sessions','external_runners']}
    def ready(self):
        candidate=self.candidate();candidate['apply_ready']=True
        candidate['admission']={'writer_inventory_repository_id':'synthetic-repository',
            'writer_inventory_observed_epoch':1000,'lease_expires_epoch':1300,
            'retained_dependency_closure_verified':True}
        return candidate
    def contract(self):
        return {'scopes':[{'paths':['/fixture/hourly']}],
            'maintenance_postcheck':{'snapshot':'c'*64,'path':'/fixture/hourly/sqlite/index.sqlite3',
                'sha256':'d'*64,'bytes':12345,'kind':'sqlite'}}
    def admit(self,candidate,lease=None):
        m.admission(candidate,m.digest(candidate),1,lease or{'phase':'held','expires_epoch':1300},1000,self.proof())
    def test_readonly_planner_cannot_authorize(self):
        with self.assertRaisesRegex(m.GateClosed,'read-only'):self.admit(self.candidate())
    def test_synthetic_reviewed_admission(self):self.admit(self.ready())
    def test_protected_cannot_be_removed(self):
        c=self.ready();c['remove_snapshot_ids']=['c'*64]
        with self.assertRaisesRegex(m.GateClosed,'protected'):self.admit(c)
    def test_expiring_lease_rejected(self):
        with self.assertRaisesRegex(m.GateClosed,'lease'):self.admit(self.ready(),{'phase':'held','expires_epoch':1080})
    def test_missing_closure_rejected(self):
        c=self.ready();c['admission']['retained_dependency_closure_verified']=False
        with self.assertRaisesRegex(m.GateClosed,'admission'):self.admit(c)
    def test_changed_reviewed_digest_rejected(self):
        with self.assertRaisesRegex(m.GateClosed,'digest'):
            m.admission(self.ready(),'f'*64,1,{'phase':'held','expires_epoch':1300},1000,self.proof())
    def test_current_status_interface_fails_closed(self):
        with self.assertRaisesRegex(m.GateClosed,'interface'):
            m.fresh_writer_proof({'phase':'released','units':[]},1000)
    def test_stale_writer_inventory_rejected(self):
        with self.assertRaisesRegex(m.GateClosed,'stale'):
            m.fresh_writer_proof({'writer_inventory':self.proof()},1031)
    def test_actual_fixture_fresh_writer_inventory(self):
        self.assertEqual(m.fresh_writer_proof({'writer_inventory':self.proof()},1001),self.proof())
    def test_limited_protected_sqlite_contract(self):m.validate_restore_contract(self.candidate(),self.contract())
    def test_postcheck_glob_rejected(self):
        p=self.contract();p['maintenance_postcheck']['path']='/fixture/hourly/**'
        with self.assertRaises(m.GateClosed):m.validate_restore_contract(self.candidate(),p)
    def test_postcheck_unrelated_path_rejected(self):
        p=self.contract();p['maintenance_postcheck']['path']='/unrelated/file.db'
        with self.assertRaises(m.GateClosed):m.validate_restore_contract(self.candidate(),p)
    def test_postcheck_oversize_rejected(self):
        p=self.contract();p['maintenance_postcheck']['bytes']=17*1024*1024
        with self.assertRaises(m.GateClosed):m.validate_restore_contract(self.candidate(),p)
    def test_zero_candidates_no_fence_or_writes(self):
        with tempfile.TemporaryDirectory(prefix='manual-noop-')as tmp:
            candidate=self.candidate();candidate['remove_snapshot_ids']=[]
            def fake(argv,env,timeout,input=None):
                self.assertTrue(argv[1].endswith('retention-audit.py'))
                Path(env['NEO_RETENTION_CANDIDATE_OUTPUT']).write_text(json.dumps(candidate));return b''
            env={'RUNNER_TEMP':tmp,'NEO_RESTIC_PASSWORD':'synthetic-password','NEO_POLICY_JSON':'{}'}
            with patch.dict(os.environ,env,clear=True),patch.object(sys,'argv',['manual','--mode','apply']),patch.object(m,'bounded',fake):m.main()
    def test_nonzero_readonly_candidate_stops_before_fence(self):
        with tempfile.TemporaryDirectory(prefix='manual-no-admission-')as tmp:
            calls=[]
            def fake(argv,env,timeout,input=None):
                calls.append(argv);Path(env['NEO_RETENTION_CANDIDATE_OUTPUT']).write_text(json.dumps(self.candidate()));return b''
            env={'RUNNER_TEMP':tmp,'NEO_RESTIC_PASSWORD':'synthetic-password','NEO_POLICY_JSON':'{}','NEO_BACKUP_APPLY_ENABLED':'true'}
            with patch.dict(os.environ,env,clear=True),patch.object(sys,'argv',['manual','--mode','apply']),patch.object(m,'bounded',fake):
                with self.assertRaisesRegex(m.GateClosed,'read-only'):m.main()
            self.assertEqual(len(calls),1)
    def test_simulated_postmaintenance_failure_releases_matching_lease(self):
        with tempfile.TemporaryDirectory(prefix='manual-lease-finally-')as tmp:
            ready=self.ready();operations=[];released=[]
            def fake(argv,env,timeout,input=None):
                if argv[0]==sys.executable:
                    Path(env['NEO_RETENTION_CANDIDATE_OUTPUT']).write_text(json.dumps(ready));return b''
                if argv[0]=='ssh':
                    self.assertFalse(any(key.startswith(('NEO_','AWS_','RESTIC_'))for key in env))
                    literal=argv[-1]
                    if literal=='status':return json.dumps({'writer_inventory':self.proof()}).encode()
                    if literal=='acquire 300':return json.dumps({'phase':'held','expires_epoch':1300,'lease':'e'*64}).encode()
                    self.assertEqual(literal,'release');released.append(input);return b'{"released":true}'
                self.assertEqual(argv[0],'restic');operations.append(argv[1])
                self.assertNotIn('NEO_RESTIC_PASSWORD',env)
                self.assertTrue(Path(env['RESTIC_PASSWORD_FILE']).is_file())
                if argv[1]=='check':raise m.GateClosed('synthetic-check-failed')
                self.assertEqual(argv[1],'forget');self.assertEqual(argv[3:],['b'*64]);return b'[]'
            policy=self.contract();policy['maintenance_ssh']={'target':'root@fixture.invalid'}
            env={'RUNNER_TEMP':tmp,'NEO_RESTIC_PASSWORD':'synthetic-password','NEO_POLICY_JSON':json.dumps(policy),
                 'NEO_BACKUP_APPLY_ENABLED':'true','NEO_MAINTENANCE_SSH_KEY':'synthetic-key',
                 'NEO_MAINTENANCE_SSH_KNOWN_HOSTS':'fixture.invalid synthetic-pin'}
            argv=['manual','--mode','apply','--expected-digest',m.digest(ready),'--maximum-removals','1']
            with patch.dict(os.environ,env,clear=True),patch.object(sys,'argv',argv),patch.object(m,'bounded',fake),patch.object(m.time,'time',lambda:1000):
                with self.assertRaisesRegex(m.GateClosed,'synthetic-check'):m.main()
            self.assertEqual(operations,['forget','check']);self.assertEqual(released,[('e'*64+'\n').encode()])
    def test_command_timeout_is_bounded(self):
        with self.assertRaisesRegex(m.GateClosed,'timeout'):
            m.bounded([sys.executable,'-c','import time; time.sleep(5)'],dict(os.environ),.02)
    def test_actual_audit_export_only_new_private_runner_file(self):
        tree=ast.parse(Path(__file__).with_name('retention-audit.py').read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main')
        assignment=next(n for n in ast.walk(main)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='export'for t in n.targets))
        gate=next(n for n in ast.walk(main)if isinstance(n,ast.If)and isinstance(n.test,ast.Name)and n.test.id=='export')
        code=compile(ast.fix_missing_locations(ast.Module(body=[assignment,gate],type_ignores=[])),'actual-private-export','exec')
        with tempfile.TemporaryDirectory(prefix='private-export-')as tmp:
            runner=Path(tmp);private=runner/'private';private.mkdir(mode=0o700)
            destination=private/'candidate.json';env={'RUNNER_TEMP':str(runner),'NEO_RETENTION_CANDIDATE_OUTPUT':str(destination)}
            def execute():exec(code,{'os':os,'Path':Path,'json':json,'result':self.candidate()})
            with patch.dict(os.environ,env,clear=True):
                execute();self.assertEqual(destination.stat().st_mode&0o777,0o600)
                with self.assertRaisesRegex(ValueError,'private'):execute()
                destination.unlink();private.chmod(0o755)
                with self.assertRaisesRegex(ValueError,'private'):execute()


if __name__=='__main__':unittest.main()
