#!/usr/bin/env python3
"""Synthetic read-only authorization and output tests; no B2 requests."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('access',Path(__file__).with_name('maintenance-access-check.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Access(unittest.TestCase):
    def auth(self,caps=None):
        return {'accountId':'synthetic-account','authorizationToken':'synthetic-token',
            'applicationKeyExpirationTimestamp':None,
            'apiInfo':{'storageApi':{'apiUrl':'https://api001.backblazeb2.com',
                's3ApiUrl':'https://s3.fixture-001.backblazeb2.com',
                'allowed':{'capabilities':list(caps or m.AUDIT),'buckets':[{'id':'synthetic-id','name':'fixture-bucket'}],
                           'namePrefix':'restic/'}}}}
    def verify(self,auth,caps=None):
        return m.verify_authorization(auth,caps or m.AUDIT,'fixture-bucket','s3.fixture-001.backblazeb2.com','restic/')
    def test_exact_audit_three(self):self.assertEqual(self.verify(self.auth()),'synthetic-id')
    def test_exact_maintenance_five(self):self.verify(self.auth(m.MAINTENANCE),m.MAINTENANCE)
    def test_master_or_key_administration_rejected(self):
        auth=self.auth();auth['apiInfo']['storageApi']['allowed']['capabilities'].append('writeKeys')
        with self.assertRaises(m.CheckFailed):self.verify(auth)
    def test_audit_delete_rejected(self):
        auth=self.auth();auth['apiInfo']['storageApi']['allowed']['capabilities'].append('deleteFiles')
        with self.assertRaises(m.CheckFailed):self.verify(auth)
    def test_unrestricted_bucket_rejected(self):
        auth=self.auth();auth['apiInfo']['storageApi']['allowed']['buckets']=None
        with self.assertRaises(m.CheckFailed):self.verify(auth)
    def test_second_bucket_rejected(self):
        auth=self.auth();auth['apiInfo']['storageApi']['allowed']['buckets'].append({'id':'other'})
        with self.assertRaises(m.CheckFailed):self.verify(auth)
    def test_wrong_prefix_rejected(self):
        auth=self.auth();auth['apiInfo']['storageApi']['allowed']['namePrefix']=''
        with self.assertRaises(m.CheckFailed):self.verify(auth)
    def test_wrong_bucket_name_rejected(self):
        auth=self.auth();auth['apiInfo']['storageApi']['allowed']['buckets'][0]['name']='other-bucket'
        with self.assertRaises(m.CheckFailed):self.verify(auth)
    def test_expiring_key_rejected(self):
        auth=self.auth();auth['applicationKeyExpirationTimestamp']=123
        with self.assertRaises(m.CheckFailed):self.verify(auth)
    def test_unknown_expiry_rejected(self):
        auth=self.auth();auth.pop('applicationKeyExpirationTimestamp')
        with self.assertRaises(m.CheckFailed):self.verify(auth)
    def test_wrong_s3_endpoint_rejected(self):
        auth=self.auth();auth['apiInfo']['storageApi']['s3ApiUrl']='https://s3.other-001.backblazeb2.com'
        with self.assertRaises(m.CheckFailed):self.verify(auth)
    def test_no_api_redirect(self):self.assertIsNone(m.NoRedirect().redirect_request(None,None,None,None,None,None))
    def test_foreign_api_and_userinfo_rejected(self):
        for url in('http://api.backblazeb2.com','https://backblazeb2.com.evil.invalid',
                   'https://user:password@api.backblazeb2.com'):
            with self.assertRaises(m.CheckFailed):m.safe_api(url)
    def test_repository_scope_parsed_privately(self):
        self.assertEqual(m.repository_target('s3:https://s3.fixture-001.backblazeb2.com/fixture-bucket/restic'),
                         ('fixture-bucket','s3.fixture-001.backblazeb2.com','restic/'))
    def test_read_api_allowlist_resolves_null_name(self):
        calls=[]
        def fake(url,authorization,body=None):
            calls.append((url,body))
            if url==m.AUTHORIZE:
                a=self.auth();a['apiInfo']['storageApi']['allowed']['buckets'][0]['name']=None;return a
            self.assertTrue(url.endswith('/b2api/v4/b2_list_buckets'))
            self.assertEqual(body['bucketId'],'synthetic-id')
            return {'buckets':[{'bucketId':'synthetic-id','bucketName':'fixture-bucket','bucketType':'allPrivate'}]}
        identity,checks=m.authorize_pair('synthetic-key-id','synthetic-key',m.AUDIT,'fixture-bucket',
            's3.fixture-001.backblazeb2.com','restic/',fake)
        self.assertEqual(len(calls),2);self.assertTrue(all(checks.values()))
    def test_restic_calls_no_lock_no_mutation_no_secret_environment(self):
        calls=[]
        def fake(args,env,work,**kwargs):
            calls.append(args)
            self.assertNotIn('NEO_RESTIC_PASSWORD',env);self.assertNotIn('AWS_SESSION_TOKEN',env)
            self.assertNotIn('RESTIC_PASSWORD_COMMAND',env)
            if args==['version']:return b'restic 0.16.4 compiled with fixture\n'
            self.assertIn('--no-lock',args);self.assertIn('--no-cache',args)
            if 'snapshots'in args:return json.dumps([{'id':'a'*64}]).encode()
            self.assertEqual(args[-2:],['cat','config']);return json.dumps({'version':2,'id':'b'*64}).encode()
        with tempfile.TemporaryDirectory(prefix='access-restic-test.')as tmp:
            env={'NEO_RESTIC_PASSWORD':'synthetic-secret','AWS_SESSION_TOKEN':'synthetic-token',
                 'RESTIC_PASSWORD_COMMAND':'must-not-execute'}
            with patch.dict(os.environ,env,clear=True):
                count,_=m.verify_repository('synthetic-id','synthetic-key','synthetic-repo',Path(tmp)/'password',None,Path(tmp),fake)
            self.assertEqual(count,1);self.assertEqual(len(calls),3)
    def test_main_output_only_booleans_counts_no_private_values(self):
        with tempfile.TemporaryDirectory(prefix='access-main-test.')as tmp:
            env={'RUNNER_TEMP':tmp,'NEO_B2_AUDIT_KEY_ID':'private-audit-id','NEO_B2_AUDIT_KEY':'private-audit-secret',
                 'NEO_B2_MAINTENANCE_KEY_ID':'private-maintenance-id','NEO_B2_MAINTENANCE_KEY':'private-maintenance-secret',
                 'NEO_RESTIC_REPOSITORY':'s3:https://s3.fixture-001.backblazeb2.com/fixture-bucket/restic',
                 'NEO_RESTIC_PASSWORD':'private-recovery-secret'}
            def auth(*args):return 'private-bucket-id',{'authorized':True}
            def repository(*args):
                self.assertEqual(args[3].stat().st_mode&0o777,0o600);return 5,'private-config-id'
            output=io.StringIO()
            with patch.dict(os.environ,env,clear=True),patch.object(m,'authorize_pair',auth),patch.object(m,'verify_repository',repository),contextlib.redirect_stdout(output):m.main()
            result=json.loads(output.getvalue());self.assertFalse(result['retention_completed'])
            self.assertEqual(result['audit']['snapshot_count'],5)
            for secret in('private-audit','private-maintenance','private-recovery','private-bucket','private-config'):
                self.assertNotIn(secret,output.getvalue())


if __name__=='__main__':unittest.main()
