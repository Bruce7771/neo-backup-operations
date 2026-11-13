#!/usr/bin/env python3
"""Pure source/process inventory cases; no host/systemd/credential reads."""
import importlib.util
import ast
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('writer',Path(__file__).with_name('writer-status.py'))
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)


class Writers(unittest.TestCase):
    def fixture(self):
        source='/usr/local/libexec/fixture-backup.py';unit='/etc/systemd/system/fixture-backup.service'
        files={source:'a'*64,unit:'b'*64}
        policy={'schema':2,'reviewed':True,'repository_id':'c'*64,'all_repository_writers_use_native_restic_locks':True,
            'reviewed_files':files,'reviewed_cron_inventory':{},'reviewed_writer_programs':[source],
            'units':[{'unit':'fixture-backup.service','role':'repository-writer','source_paths':[unit]}]}
        units=[{'unit':'fixture-backup.service','state':'inactive','source_paths':[unit]}]
        return policy,dict(files),{},units,[],1000,'d'*64
    def test_known_idle_inventory_does_not_claim_future_fence(self):
        result=w.assemble(*self.fixture());self.assertTrue(result['local_inventory_complete'])
        self.assertFalse(result['future_writers_prevented']);self.assertFalse(result['environment_values_read'])
    def test_working_backup_reported_busy_without_stopping(self):
        args=self.fixture();args[3][0]['state']='activating';r=w.assemble(*args)
        self.assertEqual(r['active_known_writer_units'],['fixture-backup.service'])
        self.assertFalse(r['service_or_schedule_changes'])
    def test_unknown_native_client_is_not_invented_as_safe(self):
        args=self.fixture();args[4].append({'pid':123,'unit':None,'repository_client':True})
        self.assertFalse(w.assemble(*args)['local_inventory_complete'])
    def test_source_changed_fails(self):
        args=self.fixture();args[1]['/usr/local/libexec/fixture-backup.py']='e'*64
        with self.assertRaises(ValueError):w.assemble(*args)
    def test_new_cron_entry_fails(self):
        args=self.fixture();args[2]['/etc/cron.d/new']='e'*64
        with self.assertRaises(ValueError):w.assemble(*args)
    def test_new_dropin_fails(self):
        args=self.fixture();args[3][0]['source_paths'].append('/etc/systemd/system/fixture-backup.service.d/new.conf')
        with self.assertRaises(ValueError):w.assemble(*args)
    def test_unreviewed_policy_fails(self):
        args=self.fixture();args[0]['reviewed']=False
        with self.assertRaises(ValueError):w.assemble(*args)
    def test_actual_systemd_utc_timestamp_format(self):
        self.assertEqual(w.next_epoch('Fri 2026-11-13 15:17:00 UTC'),1794583020)
        self.assertIsNone(w.next_epoch(''))
    def test_readonly_forced_command_has_no_legacy_fence_grant(self):
        source=Path(__file__).with_name('writer-status-ssh-command.sh').read_text()
        self.assertIn('writer-status)',source)
        self.assertNotIn('acquire 300',source);self.assertNotIn('release)',source)
        self.assertNotIn('neo-offsite-retention-fence',source)
        self.assertIn('stat -c %u',source);self.assertIn('0022',source)


if __name__=='__main__':unittest.main()
