#!/usr/bin/env python3
"""Execute readonly/no-op orchestration with an actual synthetic SQLite file."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('readonly_check',Path(__file__).with_name('retention-readonly-check.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Readonly(unittest.TestCase):
    def test_diagnostic_forwards_only_structured_fixed_fields(self):
        value={'failure_type':'ValueError','phase':'derive-metadata','source_module':'hourly_metadata_batch.py',
               'source_line':75,'metadata_stats':{'native_batches':2},'derive_elapsed_seconds':12.5}
        raw=('untrusted ignored stderr\nNEO_RETENTION_SAFE_FAILURE '+json.dumps(value)).encode()
        self.assertEqual(m.safe_audit_failure(raw),value)
        nested=dict(value,nested_failure_code='CONFIG_RESTORE_EVIDENCE_MISSING',
                    nested_source_module='retention-plan.py',nested_source_line=160)
        self.assertEqual(m.safe_audit_failure(('NEO_RETENTION_SAFE_FAILURE '+json.dumps(nested)).encode()),nested)
        self.assertIsNone(m.safe_audit_failure(b'untrusted only'))
    def test_diagnostic_rejects_private_fields_paths_or_values(self):
        value={'failure_type':'ValueError','phase':'derive-metadata','source_module':'hourly_metadata_batch.py',
               'source_line':75,'metadata_stats':{}}
        for changed in(dict(value,secret='synthetic'),dict(value,source_module='/private/path'),
                       dict(value,metadata_stats={'snapshot':'synthetic'}),dict(value,failure_type='unreviewedClass')):
            self.assertIsNone(m.safe_audit_failure(('NEO_RETENTION_SAFE_FAILURE '+json.dumps(changed)).encode()))
    def test_zero_noop_still_checks_and_restores_without_mutation(self):
        with tempfile.TemporaryDirectory(prefix='readonly-noop.')as tmp:
            root=Path(tmp);source=root/'fixture.db'
            with sqlite3.connect(source)as db:db.execute('CREATE TABLE current_objects(key TEXT)')
            path='/fixture/hourly/files/object-overlay/overlay.sqlite3'
            policy={'scopes':[{'paths':['/fixture/hourly']}],'maintenance_postcheck':{
                'snapshot':'a'*64,'path':path,'kind':'sqlite','bytes':source.stat().st_size,
                'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}}
            candidate={'apply_ready':False,'retained_snapshot_ids':['a'*64],'protected_snapshot_ids':['a'*64],
                'remove_snapshot_ids':[],'protected_unknown_hourly_points':13,'inventory_stable_for_admission':False,
                'hourly_metadata_read':{'native_batches':2,'v3_points_authenticated':1,
                    'derivation_elapsed_seconds':12.5,'derivation_deadline_seconds':180}}
            def audit(args,**kwargs):
                self.assertTrue(args[1].endswith('retention-audit.py'))
                Path(kwargs['env']['NEO_RETENTION_CANDIDATE_OUTPUT']).write_text(json.dumps(candidate))
            calls=[]
            def restic(args,env,work,**kwargs):
                self.assertNotIn('NEO_RESTIC_PASSWORD',env);calls.append(args)
                if args==['version']:return b'restic 0.16.4 fixture\n'
                self.assertIn('--no-lock',args)
                if args[-1]=='check':return b'no errors'
                self.assertIn('restore',args)
                target=Path(args[args.index('--target')+1])/path.lstrip('/')
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);return b''
            fake=types.SimpleNamespace(repository_target=lambda _:None,restic_output=restic)
            fake_spec=types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda _:None))
            env={'RUNNER_TEMP':str(root),'NEO_POLICY_JSON':json.dumps(policy),'NEO_RESTIC_PASSWORD':'synthetic-password',
                'RESTIC_REPOSITORY':'synthetic-private-repo','AWS_ACCESS_KEY_ID':'synthetic-readonly-id','AWS_SECRET_ACCESS_KEY':'synthetic-readonly-key'}
            output=io.StringIO()
            with patch.dict(os.environ,env,clear=True),patch.object(m.subprocess,'run',audit),\
                 patch.object(m.importlib.util,'spec_from_file_location',lambda *_:fake_spec),\
                 patch.object(m.importlib.util,'module_from_spec',lambda _:fake),contextlib.redirect_stdout(output):m.main()
            result=json.loads(output.getvalue())
            self.assertTrue(result['zero_candidate_noop']);self.assertTrue(result['component_restore_verified'])
            self.assertEqual(result['protected_unknown_hourly_points'],13)
            self.assertEqual(result['hourly_metadata_read'],candidate['hourly_metadata_read'])
            self.assertFalse(result['expiration_path_exercised']);self.assertFalse(result['fence_acquired'])
            self.assertFalse(any(any(x in args for x in('forget','prune','backup','unlock'))for args in calls))


if __name__=='__main__':unittest.main()
