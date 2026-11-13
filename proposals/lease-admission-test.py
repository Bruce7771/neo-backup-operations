#!/usr/bin/env python3
"""Actual planner revalidation admits safe readonly candidates without flag hacks."""
import copy
import importlib.util
from pathlib import Path
import unittest

root=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
a=load('admission',Path(__file__).with_name('lease_admission.py'))
planner=load('candidate_builder',root/'scripts/retention-plan.py')


class Admission(unittest.TestCase):
    def fixture(self):
        scopes=[];inventory=[]
        for letter,(host,(tag,paths))in zip('abc',planner.SCOPES.items()):
            kind={'neo-daily':'daily','neo-main-pitr':'pitr','neo-hourly-files':'hourly'}[tag]
            scopes.append({'kind':kind,'host':host,'tag':tag,'paths':sorted(paths)})
            inventory.append({'id':letter*64,'hostname':host,'tags':[tag],'paths':sorted(paths),'time':'2026-11-10T00:00:00Z'})
        old=dict(inventory[-1],id='d'*64);inventory.append(old)
        plans=[[{'keep':inventory[:3],'remove':[old]}]]
        protected=['a'*64,'b'*64,'c'*64];restored=list(protected)
        edge={'child_snapshot':'c'*64,'kind':'sqlite-files-only','source':'reviewed-external-policy',
              'evidence_sha256':'e'*64,'verified':True,'postgres_recovery_included':False}
        candidate=planner.build(inventory,plans,protected,restored,[],[edge])
        candidate['inventory_stable_for_admission']=True
        policy={'schema':1,'scopes':scopes,'configuration_scopes':[],
            'writer_policy_sha256':'e'*64,'credential_holder_repositories':['fixture/ops']}
        bundle={'schema':1,'validated_epoch':1000,'policy':policy,'inventory':inventory,'plans':plans,
            'protected':protected,'restored':restored,'dependencies':[],'hourly_recovery':[edge],'candidate':candidate}
        static={'protected':protected,'restored':restored,'dependencies':[],'hourly_overrides':[edge]}
        local={'schema':2,'local_inventory_complete':True,'source_review_integrity':True,'native_restic_writer_protocol_only':True,
            'repository_id':'f'*64,'writer_policy_sha256':'e'*64,'observed_epoch':1000,'unknown_writer_units':[],
            'unknown_repository_clients':0,'active_known_writer_units':[],'active_known_repository_clients':0,
            'next_known_writer_start_epoch':1250}
        external={'complete':True,'observed_epoch':1000,'repositories':['fixture/ops'],'other_running_jobs':0}
        locks={'complete':True,'repository_id':'f'*64,'observed_epoch':1000,'total_locks':0}
        digest=a.removal_review_digest(candidate,policy,'a'*40,static)
        return bundle,policy,static,digest,'a'*40,1,'f'*64,local,external,locks,1000
    def test_real_readonly_candidate_admitted_without_flipping_flag(self):
        args=self.fixture();lease=a.admit(*args)
        self.assertTrue(lease['admitted']);self.assertFalse(args[0]['candidate']['apply_ready'])
        self.assertFalse(lease['backup_starts_blocked']);self.assertEqual(lease['expires_epoch'],1300)
    def test_owner_digest_stable_across_nonremoval_metadata(self):
        args=self.fixture();candidate=copy.deepcopy(args[0]['candidate']);candidate['inventory_sha256']='b'*64
        self.assertEqual(a.removal_review_digest(candidate,args[1],'a'*40,args[2]),args[3])
    def test_working_backup_not_stopped_but_admission_refused(self):
        args=self.fixture();args[7]['active_known_writer_units']=['fixture-backup.service']
        with self.assertRaisesRegex(a.NotAdmitted,'Working backup'):a.admit(*args)
    def test_lock_busy_no_automatic_unlock(self):
        args=self.fixture();args[9]['total_locks']=1
        with self.assertRaisesRegex(a.NotAdmitted,'never unlock'):a.admit(*args)
    def test_plan_tampering_is_rebuilt_and_rejected(self):
        args=self.fixture();args[0]['candidate']['protected_snapshot_ids']=[]
        with self.assertRaisesRegex(a.NotAdmitted,'revalidation'):a.admit(*args)
    def test_cannot_invent_restore_evidence(self):
        args=self.fixture();args[0]['restored'].append('d'*64)
        # Break the alias intentionally: protected environment remains unchanged.
        args[2]['restored']=['a'*64,'b'*64,'c'*64]
        with self.assertRaisesRegex(a.NotAdmitted,'evidence'):a.admit(*args)
    def test_append_only_unstable_candidate_is_not_mutation_authority(self):
        args=self.fixture();args[0]['candidate']['inventory_stable_for_admission']=False
        with self.assertRaisesRegex(a.NotAdmitted,'stable replan'):a.admit(*args)
    def test_prune_requires_separate_shared_gc_review(self):
        with self.assertRaisesRegex(a.NotAdmitted,'shared GC'):a.admit(*self.fixture(),prune=True)
    def test_future_command_respects_next_backup_window(self):
        args=self.fixture();lease=a.admit(*args);args[7]['next_known_writer_start_epoch']=1040
        with self.assertRaisesRegex(a.NotAdmitted,'Scheduled writer'):
            a.before_native_mutation(lease,args[6],args[1],args[7],args[8],args[9],1000,30)
    def test_expired_or_insufficient_budget_lease_refused(self):
        args=self.fixture();lease=a.admit(*args)
        with self.assertRaisesRegex(a.NotAdmitted,'budget'):
            a.before_native_mutation(lease,args[6],args[1],args[7],args[8],args[9],1290,10)


if __name__=='__main__':unittest.main()
