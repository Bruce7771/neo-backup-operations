#!/usr/bin/env python3
import copy,importlib.util,unittest
from pathlib import Path
p=Path(__file__).with_name('native-admission-contract.py');spec=importlib.util.spec_from_file_location('admission',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Contract(unittest.TestCase):
 def fixture(self):return {'repository':'Bruce7771/neo-backup-operations','gha_b2_workflows':[{'name':x,'group':m.GROUP,'cancel_in_progress':False}for x in sorted(m.WORKFLOWS)],'mutator_group':m.GROUP,'mutator_cancel_in_progress':False,'vm_roster_reviewed_complete':True,'vm_data_read_sites':[{'command':'dump','explicit_no_lock':False,'installed_sha256':'a'*64,'multi_command':True,'selected_snapshot_protected':True}],'late_v2_parent_snapshots':[c*64 for c in'123'],'protected_snapshots':[c*64 for c in'123']}
 def window(self):return {'actual_active_backup_or_accept_jobs':0,'observed_native_locks':0,'seconds_to_next':{'pitr':121,'hourly':122,'daily':999},'native_gc_max_seconds':90,'native_timeout_cleanup_proved':True,'fresh_inventory_digest':'a'*64,'reviewed_plan_inventory_digest':'a'*64}
 def test_complete_contract_does_not_grant_nonzero(self):self.assertFalse(m.validate_reader_contract(self.fixture())['nonzero_authority_granted'])
 def test_any_external_other_group_refused(self):
  x=self.fixture();x['gha_b2_workflows'][0]['group']='other'
  with self.assertRaises(ValueError):m.validate_reader_contract(x)
 def test_no_lock_data_reader_refused(self):
  x=self.fixture();x['vm_data_read_sites'][0]['explicit_no_lock']=True
  with self.assertRaises(ValueError):m.validate_reader_contract(x)
 def test_default_ls_is_not_a_native_locked_reader(self):
  x=self.fixture();x['vm_data_read_sites'][0]['command']='ls'
  with self.assertRaises(ValueError):m.validate_reader_contract(x)
 def test_multicall_unprotected_snapshot_refused(self):
  x=self.fixture();x['vm_data_read_sites'][0]['selected_snapshot_protected']=False
  with self.assertRaises(ValueError):m.validate_reader_contract(x)
 def test_late_parent_missing_refused(self):
  x=self.fixture();x['protected_snapshots'].pop()
  with self.assertRaises(ValueError):m.validate_reader_contract(x)
 def test_unreviewed_roster_refused(self):
  x=self.fixture();x['vm_roster_reviewed_complete']=False
  with self.assertRaises(ValueError):m.validate_reader_contract(x)
 def test_window_no_authority(self):self.assertFalse(m.validate_gc_window(self.window())['nonzero_authority_granted'])
 def test_exact120_seconds_refused(self):
  x=self.window();x['seconds_to_next']['pitr']=120
  with self.assertRaises(ValueError):m.validate_gc_window(x)
 def test_active_backup_refused(self):
  x=self.window();x['actual_active_backup_or_accept_jobs']=1
  with self.assertRaises(ValueError):m.validate_gc_window(x)
 def test_changed_inventory_refused(self):
  x=self.window();x['fresh_inventory_digest']='b'*64
  with self.assertRaises(ValueError):m.validate_gc_window(x)
 def test_unknown_lock_prevents_unlock(self):
  own={'id':'a','pid':5,'hostname':'fixture','exclusive':True}
  self.assertTrue(m.own_dead_lock_cleanup_allowed(['a'],[own],reaped=True,pid=5,hostname='fixture'))
  self.assertFalse(m.own_dead_lock_cleanup_allowed(['a'],[own,dict(own,id='b')],reaped=True,pid=5,hostname='fixture'))
  self.assertFalse(m.own_dead_lock_cleanup_allowed(['a'],[own],reaped=False,pid=5,hostname='fixture'))
if __name__=='__main__':unittest.main()
