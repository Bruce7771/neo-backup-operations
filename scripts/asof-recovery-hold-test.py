#!/usr/bin/env python3
"""Fixed historical protection, not ever-growing future retention."""
import copy
import hashlib
import unittest
from asof_recovery_hold import canonical,fixed_hold,projection


class ASOF(unittest.TestCase):
    def fixture(self):
        def row(letter,kind,time='2026-11-10T00:00:00Z'):
            return {'id':letter*64,'hostname':kind,'tags':[kind],'paths':['/fixture/'+kind],'time':time}
        inventory=[row('a','daily'),row('b','pitr')]+[dict(row('c','hourly'),id=f'{i:064x}')for i in range(3,16)]
        unknown=[{'child_snapshot':f'{i:064x}','kind':'protected-unknown','source':'reviewed-external-policy',
            'evidence_sha256':'f'*64,'hold_verified':True,'restore_coverage':'unknown',
            'reason':'ARCHIVE_CAPTURE_SCOPE_UNDECLARED'}for i in range(3,16)]
        baseline=sorted([projection(row)for row in inventory],key=lambda r:r['id'])
        evidence=[{key:e[key]for key in('child_snapshot','evidence_sha256','restore_coverage')}for e in unknown]
        policy={'scopes':[{'kind':kind,'host':kind,'tag':kind,'paths':['/fixture/'+kind]}for kind in('daily','pitr','hourly')],
            'configuration_scopes':[],'protected_unknown_hourly':unknown,
            'as_of_unknown_hold':{'schema':2,'reviewed':True,'as_of_utc':'2026-11-13T00:00:00Z',
                'inventory_projection':baseline,'inventory_projection_sha256':hashlib.sha256(canonical(baseline)).hexdigest(),
                'unknown_evidence_count':13,'unknown_evidence_sha256':hashlib.sha256(canonical(evidence)).hexdigest()}}
        return inventory,policy,row
    def test_future_roots_not_held_forever(self):
        inventory,policy,row=self.fixture();inventory+=[row('d','daily','2026-11-14T00:00:00Z'),row('e','pitr','2026-11-14T00:00:00Z')]
        self.assertEqual(fixed_hold(inventory,policy),{'a'*64,'b'*64}|{f'{i:064x}'for i in range(3,16)})
    def test_old_possible_root_cannot_disappear(self):
        inventory,policy,_=self.fixture();inventory.pop(1)
        with self.assertRaisesRegex(ValueError,'Historical recovery root'):fixed_hold(inventory,policy)
    def test_changed_baseline_fingerprint_rejected(self):
        inventory,policy,_=self.fixture();policy['as_of_unknown_hold']['inventory_projection'][0]['paths']=['/other']
        with self.assertRaisesRegex(ValueError,'fingerprint'):fixed_hold(inventory,policy)
    def test_backdated_new_root_requires_review(self):
        inventory,policy,row=self.fixture();inventory.append(row('d','pitr','2026-11-11T00:00:00Z'))
        with self.assertRaisesRegex(ValueError,'backdated'):fixed_hold(inventory,policy)
    def test_unknown_manifest_contract_not_weakened(self):
        inventory,policy,_=self.fixture();policy['as_of_unknown_hold']['unknown_evidence_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'fingerprint'):fixed_hold(inventory,policy)
    def test_unknown_child_tamper_rejected(self):
        inventory,policy,_=self.fixture();policy['protected_unknown_hourly'][0]['child_snapshot']='e'*64
        with self.assertRaisesRegex(ValueError,'fingerprint'):fixed_hold(inventory,policy)
    def test_unknown_coverage_tamper_rejected(self):
        inventory,policy,_=self.fixture();policy['protected_unknown_hourly'][0]['restore_coverage']='restored'
        with self.assertRaisesRegex(ValueError,'fingerprint'):fixed_hold(inventory,policy)
    def test_unknown_count_tamper_rejected(self):
        inventory,policy,_=self.fixture();policy['protected_unknown_hourly'].pop()
        with self.assertRaisesRegex(ValueError,'count'):fixed_hold(inventory,policy)
    def test_canonical_unknown_order_is_stable(self):
        inventory,policy,_=self.fixture();policy['protected_unknown_hourly'].reverse()
        self.assertEqual(len(fixed_hold(inventory,policy)),15)


if __name__=='__main__':unittest.main()
