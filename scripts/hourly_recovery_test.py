#!/usr/bin/env python3
"""Synthetic dependency-derivation tests; no account, network or real IDs."""
import gzip,hashlib,json,unittest
from hourly_recovery import derive

class DeriveTests(unittest.TestCase):
    def fixture(self):
        policy={'scopes':[dict(kind=k,host=k,tag=k,paths=['/fixture/'+k]) for k in ('daily','hourly','pitr')]}
        def row(sid,k):return dict(id=sid*64,hostname=k,tags=[k],paths=['/fixture/'+k])
        daily,hourly,pitr,new_pitr,new_hourly=row('a','daily'),row('b','hourly'),row('c','pitr'),row('d','pitr'),row('e','hourly')
        inventory=[daily,hourly,pitr,new_pitr,new_hourly]
        plans=[[dict(keep=[daily,hourly,pitr,new_hourly],remove=[new_pitr])]]
        external=[dict(child_snapshot=hourly['id'],kind='sqlite-files-only',source='reviewed-external-policy',verified=True,
                       evidence_sha256='f'*64,postgres_recovery_included=False)]
        name='neo_hourly_1234567890_abcdef01';segment='A'*24
        raw=(name.encode()+b'\0'*(16*1024*1024-len(name)))
        wal=gzip.compress(raw);digest=hashlib.sha256(wal).hexdigest()
        encode=lambda obj:json.dumps(obj,sort_keys=True).encode()
        base=encode({'Files':[],'Fixture':True})
        blobs={(pitr['id'],'/fixture/pitr/base/backup_manifest'):base,
               (new_pitr['id'],'/fixture/pitr/base/backup_manifest'):base,
               (new_hourly['id'],'/fixture/hourly/capture-result.json'):encode(dict(scope='neo-hourly-write-fenced-capture',sqlite_verified=6,postgres_marker_recorded=True)),
               (new_hourly['id'],'/fixture/hourly/postgres-archive-delivery.json'):encode(dict(archive_delivery_verified=True,wal_snapshot=new_pitr['id'],wal_segment=segment,wal_sha256=digest,marker_restore_point=name)),
               (new_hourly['id'],'/fixture/hourly/postgres-point.private.json'):encode(dict(restore_point=name,wal_segment=segment)),
               (new_pitr['id'],'/fixture/pitr/wal/'+segment+'.gz'):wal}
        return inventory,plans,policy,external,[pitr['id']],blobs
    def invoke(self,data):
        *args,blobs=data
        def dump(sid,path,max_bytes):
            raw=blobs[sid,path];self.assertLessEqual(len(raw),max_bytes);return raw
        return derive(*args,dump)
    def test_derive_without_owner_hourly_refresh(self):
        data=self.fixture();edges,parents,plans=self.invoke(data)
        self.assertEqual(len(edges),2);self.assertEqual(parents,{'d'*64})
        self.assertEqual(plans[0][0]['remove'],[])
        self.assertIn('d'*64,[r['id'] for r in plans[0][0]['keep']])
        self.assertEqual(edges[1]['source'],'postgres-archive-delivery.json')
        self.assertNotIn('d'*64,data[4]) # shared accepted base, no full restore per new parent
    def test_derived_dependencies_pass_exact_retention_guard(self):
        import importlib.util
        from pathlib import Path
        spec=importlib.util.spec_from_file_location('fixture_retention',Path(__file__).with_name('retention-plan.py'))
        planner=importlib.util.module_from_spec(spec);spec.loader.exec_module(planner)
        data=self.fixture();inventory,_,policy,_,_,_=data
        tags={'daily':'neo-daily','hourly':'neo-hourly-files','pitr':'neo-main-pitr'}
        for scope in policy['scopes']:scope['tag']=tags[scope['kind']]
        for row in inventory:row['tags']=[tags[row['hostname']]]
        planner.SCOPES={s['host']:(s['tag'],frozenset(s['paths'])) for s in policy['scopes']}
        planner.FULL_MAIN_HOST='daily';planner.CONFIG_SCOPES={}
        edges,parents,plans=self.invoke(data)
        result=planner.build(inventory,plans,['a'*64]+sorted(parents),['a'*64,'b'*64,'c'*64],[],edges)
        self.assertFalse(result['apply_ready'])
        self.assertEqual(result['remove_snapshot_ids'],[])
    def test_missing_metadata_never_means_legacy(self):
        data=self.fixture();del data[-1]['e'*64,'/fixture/hourly/postgres-archive-delivery.json']
        with self.assertRaises(KeyError):self.invoke(data)
    def test_wal_hash_mismatch(self):
        data=self.fixture();data[-1]['d'*64,'/fixture/pitr/wal/'+'A'*24+'.gz']=gzip.compress(b'wrong')
        with self.assertRaisesRegex(ValueError,'WAL content hash'):self.invoke(data)
    def test_marker_conflict(self):
        data=self.fixture();data[-1]['e'*64,'/fixture/hourly/postgres-point.private.json']=b'{}'
        with self.assertRaisesRegex(ValueError,'target differ'):self.invoke(data)
    def test_new_base_needs_periodic_compatible_restore(self):
        data=self.fixture();data[-1]['d'*64,'/fixture/pitr/base/backup_manifest']=b'{"Fixture":"different"}'
        with self.assertRaisesRegex(ValueError,'compatible full-restore'):self.invoke(data)
    def test_unknown_format_needs_external_review(self):
        data=self.fixture();data[-1]['e'*64,'/fixture/hourly/capture-result.json']=b'{"scope":"unknown"}'
        with self.assertRaisesRegex(ValueError,'Unknown hourly format'):self.invoke(data)
    def test_override_cannot_omit_review_source(self):
        data=self.fixture();data[3][0]['source']='guessed'
        with self.assertRaisesRegex(ValueError,'external review'):self.invoke(data)
    def test_unknown_parent_rejected(self):
        data=self.fixture();k=('e'*64,'/fixture/hourly/postgres-archive-delivery.json');obj=json.loads(data[-1][k]);obj['wal_snapshot']='f'*64;data[-1][k]=json.dumps(obj).encode()
        with self.assertRaisesRegex(ValueError,'Unknown hourly PITR parent'):self.invoke(data)
    def unknown_fixture(self):
        data=self.fixture();inventory,plans,policy,external,restored,blobs=data
        raw=b'[{"fixture":"unclassified"}]';blobs['b'*64,'/fixture/hourly/manifest.json']=raw
        external.clear();policy['protected_unknown_hourly']=[dict(child_snapshot='b'*64,kind='protected-unknown',
            source='reviewed-external-policy',evidence_sha256=hashlib.sha256(raw).hexdigest(),
            reason='ARCHIVE_CAPTURE_SCOPE_UNDECLARED',hold_verified=True,restore_coverage='unknown')]
        policy['unknown_recovery_hold_mode']='hold-all-authorized-recovery-roots'
        held=next(row for row in plans[0][0]['keep']if row['id']=='b'*64)
        plans[0][0]['keep'].remove(held);plans[0][0]['remove'].append(held)
        return data
    def test_unknown_held_without_false_recovery_and_all_roots_kept(self):
        edges,parents,plans=self.invoke(self.unknown_fixture())
        self.assertTrue({'a'*64,'b'*64,'c'*64,'d'*64}<=parents)
        unknown=next(edge for edge in edges if edge['child_snapshot']=='b'*64)
        self.assertEqual(unknown['restore_coverage'],'unknown');self.assertNotIn('verified',unknown)
        self.assertEqual(plans[0][0]['remove'],[])
    def test_unknown_manifest_hash_changed_rejected(self):
        data=self.unknown_fixture();data[-1]['b'*64,'/fixture/hourly/manifest.json']=b'changed'
        with self.assertRaisesRegex(ValueError,'fingerprint'):self.invoke(data)
    def test_unknown_cannot_invent_restore_coverage(self):
        data=self.unknown_fixture();data[2]['protected_unknown_hourly'][0]['verified']=True
        with self.assertRaisesRegex(ValueError,'invent'):self.invoke(data)

if __name__=='__main__':unittest.main()
