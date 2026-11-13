#!/usr/bin/env python3
"""Synthetic JSON-only restore/cache tests; no real repository is contacted."""
import copy,hashlib,json,tempfile,time,unittest
from pathlib import Path
from hourly_metadata_batch import HourlyMetadataBatch,LIMITS

class Batch(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='neo-metadata-batch-test-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.cache=self.root/'private-cache';self.calls=[]
        self.scope={'kind':'hourly','host':'fixture-hourly','tag':'fixture-hourly','paths':['/fixture/hourly']}
        self.inventory=[dict(id=s*64,hostname='fixture-hourly',tags=['fixture-hourly'],paths=['/fixture/hourly'])for s in('a','b')]
        self.env={'RESTIC_REPOSITORY':'s3:https://example.invalid/private/restic'}
        self.payloads={s*64:self.payload(v3=s=='b')for s in('a','b')}
        self.batch=self.make()
    def payload(self,v3=False):
        enc=lambda obj:json.dumps(obj,sort_keys=True).encode()
        result={'capture-result.json':enc({'scope':'fixture'}),'postgres-point.private.json':enc({'marker':'fixture'})}
        delivery={'schema':3 if v3 else 2}
        if v3:
            result['postgres-selfcontained/sealed-pg.json']=enc({'schema':3})
            delivery['sealed_pg_sha256']=hashlib.sha256(result['postgres-selfcontained/sealed-pg.json']).hexdigest()
        result['postgres-archive-delivery.json']=enc(delivery)
        result['manifest.json']=enc([dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())for name,raw in result.items()])
        return result
    def restore(self,command,env,deadline):
        self.calls.append(command);self.assertEqual(env,self.env);self.assertGreater(deadline,time.monotonic())
        self.assertEqual(command[:4],['restic','--no-lock','restore','--verify'])
        index=command.index('--target');target=Path(command[index+1]);snapshot=command[index+2]
        includes=command[index+3:];self.assertEqual(includes[::2],['--include']*5)
        self.assertEqual(set(includes[1::2]),{'/fixture/hourly/'+name for name in LIMITS})
        for name,raw in self.payloads[snapshot].items():
            path=target/'fixture/hourly'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    def make(self):
        return HourlyMetadataBatch(self.cache,self.env,self.inventory,self.scope,time.monotonic()+180,self.restore)
    def get(self,sid='a',name='manifest.json',maximum=8*1024*1024):
        return self.batch.get(sid*64,'/fixture/hourly/'+name,maximum)
    def test_v2_four_actual_files_use_one_five_path_allowlisted_call(self):
        for name in self.payloads['a'*64]:self.get(name=name)
        self.assertEqual(len(self.calls),1);self.assertEqual(self.batch.stats['native_batches'],1)
    def test_v3_exact_five_files_and_durable_checkpoint_reused_new_instance(self):
        for name in self.payloads['b'*64]:self.get('b',name)
        self.assertEqual(self.batch.stats['v3_points_authenticated'],1)
        self.batch=self.make();self.get('b');self.assertEqual(len(self.calls),1)
        self.assertEqual(self.batch.stats['checkpoint_reads'],1)
    def test_snapshot_and_path_allowlist(self):
        for sid,path in [('c'*64,'/fixture/hourly/manifest.json'),('a'*64,'/fixture/hourly/../media'),
                         ('a'*64,'/fixture/hourly/files/secret.db'),('a'*64,'/fixture/hourlyX/manifest.json')]:
            with self.assertRaises(ValueError):self.batch.get(sid,path,100)
        self.assertEqual(self.calls,[])
    def test_scope_root_traversal_refused(self):
        self.scope['paths']=['/fixture/../secret']
        with self.assertRaises(ValueError):self.make()
    def test_oversize_restored_json_refused_without_checkpoint(self):
        self.payloads['a'*64]['manifest.json']=b' '*(LIMITS['manifest.json']+1)
        with self.assertRaisesRegex(ValueError,'oversize'):self.get()
        self.assertEqual(list(self.cache.iterdir()),[])
    def test_manifest_traversal_refused(self):
        self.payloads['a'*64]['manifest.json']=json.dumps([dict(path='../escape',bytes=1,sha256='a'*64)]).encode()
        with self.assertRaisesRegex(ValueError,'Unsafe'):self.get()
    def test_individual_metadata_hash_still_verified(self):
        self.payloads['a'*64]['capture-result.json']=b'{"tampered":true}'
        with self.assertRaisesRegex(ValueError,'fingerprint'):self.get()
    def test_cross_point_cache_contamination_refused(self):
        self.get();record=next(self.cache.glob('*/record.json'));data=json.loads(record.read_text());data['snapshot']='b'*64;record.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'Cross-point'):self.get()
    def test_cache_oversize_refused(self):
        self.get();point=self.cache/self.batch._key('a'*64)
        (point/self.batch._filename('manifest.json')).write_bytes(b' '*(LIMITS['manifest.json']+1))
        with self.assertRaisesRegex(ValueError,'oversize'):self.get()
    def test_distinct_snapshots_get_distinct_checkpoints(self):
        self.get();self.get('b');self.assertEqual(len(self.calls),2)
        self.assertEqual(len(list(self.cache.iterdir())),2)
    def test_request_size_and_deadline_remain_enforced_on_cache_hit(self):
        self.get()
        with self.assertRaisesRegex(ValueError,'size bound'):self.get(maximum=1)
        self.batch.deadline=time.monotonic()-1
        with self.assertRaises(TimeoutError):self.get()
        self.assertEqual(len(self.calls),1)
    def test_completed_point_survives_later_failed_point(self):
        self.get();self.payloads['b'*64]['unexpected.sqlite3']=b'not allowed'
        with self.assertRaisesRegex(ValueError,'Unexpected'):self.get('b')
        self.batch=self.make();self.get();self.assertEqual(len(self.calls),2)
    def test_native_reader_does_not_select_payload_paths(self):
        self.get();selected=self.calls[0][self.calls[0].index('--include'):]
        for value in selected:
            if value!='--include':self.assertTrue(value.endswith('.json'))

if __name__=='__main__':unittest.main()
