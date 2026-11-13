#!/usr/bin/env python3
"""Real isolated SQLite component tests, with no B2 or account access."""
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import retention_postcheck as p


class Component(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='retained-component.');self.root=Path(self.tmp.name)
        self.source=self.root/'source.db'
        with sqlite3.connect(self.source)as db:db.execute('CREATE TABLE current_objects(key TEXT)')
        self.path='/fixture/hourly/files/object-overlay/overlay.sqlite3'
        self.candidate={'retained_snapshot_ids':['a'*64],'protected_snapshot_ids':['a'*64]}
        self.policy={'scopes':[{'paths':['/fixture/hourly']}],'maintenance_postcheck':{
            'snapshot':'a'*64,'path':self.path,'kind':'sqlite','bytes':self.source.stat().st_size,
            'sha256':hashlib.sha256(self.source.read_bytes()).hexdigest()}}
    def tearDown(self):self.tmp.cleanup()
    def fake_restore(self,args):
        self.assertIn('--no-lock',args);self.assertIn('--verify',args)
        target=Path(args[args.index('--target')+1])/self.path.lstrip('/')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.source,target)
    def test_actual_component_restored_sha_and_sqlite(self):
        result=p.restore(self.candidate,self.policy,self.root,self.fake_restore)
        self.assertTrue(result['component_restore_verified']);self.assertFalse(result['full_database_or_site_restore_claimed'])
    def test_shadow_artifact_rejected(self):
        self.policy['maintenance_postcheck']['path']='/fixture/hourly/files/object-snapshot/index.sqlite3'
        with self.assertRaises(ValueError):p.validate(self.candidate,self.policy)
    def test_unprotected_point_rejected(self):
        self.candidate['protected_snapshot_ids']=[]
        with self.assertRaises(ValueError):p.validate(self.candidate,self.policy)
    def test_changed_payload_rejected(self):
        self.policy['maintenance_postcheck']['sha256']='f'*64
        with self.assertRaises(ValueError):p.restore(self.candidate,self.policy,self.root,self.fake_restore)
    def test_oversized_component_rejected(self):
        self.policy['maintenance_postcheck']['bytes']=17*1024*1024
        with self.assertRaises(ValueError):p.validate(self.candidate,self.policy)


if __name__=='__main__':unittest.main()
