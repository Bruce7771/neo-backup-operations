#!/usr/bin/env python3
"""Synthetic v3 archive metadata; does not claim a native PostgreSQL replay."""
import copy,gzip,hashlib,importlib.util,json,unittest
from pathlib import Path
from hourly_recovery_test import DeriveTests

class SelfContained(unittest.TestCase):
    def fixture(self):
        data=DeriveTests().fixture();blobs=data[-1];sid='e'*64;root='/fixture/hourly'
        encode=lambda x:json.dumps(x,sort_keys=True).encode()
        marker={'restore_point':'neo_hourly_1234567890_abcdef01','wal_segment':'000000010000000000000001','wal_lsn':'0/1000030'}
        base=encode({'WAL-Ranges':[{'Timeline':1,'Start-LSN':'0/1000001','End-LSN':'0/1000010'}]})
        for parent in('c'*64,'d'*64):blobs[parent,'/fixture/pitr/base/backup_manifest']=base
        wal=gzip.compress(marker['restore_point'].encode()+bytes(16*1024*1024-len(marker['restore_point'])))
        pgfiles={'base/backup_manifest':base,'wal/'+marker['wal_segment']+'.gz':wal}
        files=[dict(path=path,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())for path,raw in pgfiles.items()]
        sealed=dict(schema=3,scope='main-neo-builder-physical-postgres-selfcontained',external_parent_dependency=None,
                    base_manifest_sha256=hashlib.sha256(base).hexdigest(),files=files,**marker)
        seal=encode(sealed)
        outer=[dict(row,path='postgres-selfcontained/'+row['path'])for row in files]
        outer.append(dict(path='postgres-selfcontained/sealed-pg.json',bytes=len(seal),sha256=hashlib.sha256(seal).hexdigest()))
        delivery=dict(schema=3,postgres_recovery_included=True,external_parent_dependency=None,
                      marker_restore_point=marker['restore_point'],wal_segment=marker['wal_segment'],
                      sealed_pg_sha256=hashlib.sha256(seal).hexdigest(),base_manifest_sha256=hashlib.sha256(base).hexdigest())
        for path,raw in pgfiles.items():blobs[sid,root+'/postgres-selfcontained/'+path]=raw
        for path,obj in [('postgres-point.private.json',marker),('postgres-archive-delivery.json',delivery),
                         ('manifest.json',outer),('postgres-selfcontained/sealed-pg.json',sealed)]:blobs[sid,root+'/'+path]=encode(obj)
        return data
    def invoke(self,data):return DeriveTests().invoke(data)
    def test_v3_no_external_parent_hold_and_no_replay_claim(self):
        edges,parents,plans=self.invoke(self.fixture());edge=next(e for e in edges if e['child_snapshot']=='e'*64)
        self.assertEqual(parents,set());self.assertNotIn('wal_snapshot',edge)
        self.assertEqual(edge['kind'],'selfcontained-pg-named-point');self.assertFalse(edge['postgres_named_target_restore_verified'])
        self.assertEqual([r['id']for r in plans[0][0]['remove']],['d'*64])
    def test_old_external_parent_still_held(self):
        old=DeriveTests().fixture();edges,parents,_=self.invoke(old);self.assertEqual(parents,{'d'*64})
    def test_seal_tamper_refused(self):
        data=self.fixture();data[-1]['e'*64,'/fixture/hourly/postgres-selfcontained/sealed-pg.json']=b'{}'
        with self.assertRaisesRegex(ValueError,'seal fingerprint'):self.invoke(data)
    def test_outer_unbound_file_refused(self):
        data=self.fixture();data[-1]['e'*64,'/fixture/hourly/manifest.json']=b'[]'
        with self.assertRaisesRegex(ValueError,'outer manifest'):self.invoke(data)
    def test_cloud_parent_refused(self):
        data=self.fixture();key=('e'*64,'/fixture/hourly/postgres-archive-delivery.json');obj=json.loads(data[-1][key]);obj['wal_snapshot']='d'*64;data[-1][key]=json.dumps(obj).encode()
        with self.assertRaisesRegex(ValueError,'cloud parent'):self.invoke(data)
    def test_planner_accepts_v3_metadata_without_deleting_guard_authority(self):
        data=self.fixture();inventory,_,policy,_,_,_=data
        tags={'daily':'neo-daily','hourly':'neo-hourly-files','pitr':'neo-main-pitr'}
        for scope in policy['scopes']:scope['tag']=tags[scope['kind']]
        for row in inventory:row['tags']=[tags[row['hostname']]]
        spec=importlib.util.spec_from_file_location('fixture_v3_retention',Path(__file__).with_name('retention-plan.py'))
        planner=importlib.util.module_from_spec(spec);spec.loader.exec_module(planner)
        planner.SCOPES={s['host']:(s['tag'],frozenset(s['paths']))for s in policy['scopes']};planner.FULL_MAIN_HOST='daily';planner.CONFIG_SCOPES={}
        edges,parents,plans=self.invoke(data)
        result=planner.build(inventory,plans,['a'*64],['a'*64,'b'*64,'c'*64],[],edges)
        self.assertFalse(result['apply_ready']);self.assertEqual(result['remove_snapshot_ids'],['d'*64])

if __name__=='__main__':unittest.main()
