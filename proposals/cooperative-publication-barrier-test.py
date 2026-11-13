#!/usr/bin/env python3
"""LOCAL SYNTHETIC ONLY: cooperative flock protocol, never a cloud client.

This is a protocol fixture, not installed code or authority to remove backups.
Every synthetic producer selects/validates its parent while holding SH and
retains SH through publication. Maintenance takes EX nonblocking, then replans
from current inventory plus persistent producer-parent roots before deletion.
Real remote native locks and all producer wrapping remain required separately.
"""
import fcntl
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import time
import unittest


class Barrier:
    def __init__(self, path, exclusive=False, nonblocking=False):
        self.path=path;self.exclusive=exclusive;self.nonblocking=nonblocking;self.fd=None
    def __enter__(self):
        self.fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600)
        try:
            mode=fcntl.LOCK_EX if self.exclusive else fcntl.LOCK_SH
            fcntl.flock(self.fd,mode|(fcntl.LOCK_NB if self.nonblocking else 0))
        except BaseException:
            os.close(self.fd);self.fd=None;raise
        return self
    def __exit__(self,*exc):
        if self.fd is not None:os.close(self.fd);self.fd=None


def hold(path, exclusive, acquired, release):
    with Barrier(path,exclusive=exclusive):
        acquired.set();release.wait(5)


def maintained_inventory(inventory, requested, producer_roots):
    """Called ONLY under EX in this fixture; closure is recomputed, not cached."""
    protected=set(producer_roots)
    for parents in inventory.values():protected.update(parents)
    removable=set(requested)-protected
    return {key:parents for key,parents in inventory.items() if key not in removable},removable


def publish(inventory, child, requested_parent, replacement=None):
    """Called ONLY under SH; stale pre-EX parent guesses cannot authorize use."""
    parent=requested_parent
    if parent not in inventory:
        if replacement is None or replacement not in inventory:raise ValueError('Parent missing: refuse publication')
        parent=replacement
    inventory[child]={parent}
    return parent


class CooperativeBarrier(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='neo-local-publication-')
        self.path=str(Path(self.temp.name)/'publication.lock')
        self.children=[]
    def tearDown(self):
        for process in self.children:
            if process.is_alive():process.terminate()
            process.join(3)
        self.temp.cleanup()
    def start(self,exclusive=False):
        context=mp.get_context('spawn') # independent clients must not inherit lock FDs
        acquired=context.Event();release=context.Event()
        process=context.Process(target=hold,args=(self.path,exclusive,acquired,release));process.start()
        self.children.append(process);return process,acquired,release
    def test_active_writer_finishes_without_interruption_maintenance_refuses(self):
        process,acquired,release=self.start();self.assertTrue(acquired.wait(2))
        before=time.monotonic()
        with self.assertRaises(BlockingIOError):
            with Barrier(self.path,exclusive=True,nonblocking=True):self.fail('EX while writer active')
        self.assertLess(time.monotonic()-before,.25);self.assertTrue(process.is_alive())
        release.set();process.join(2);self.assertEqual(process.exitcode,0)
    def test_future_writer_waits_short_exclusive_then_continues(self):
        with Barrier(self.path,exclusive=True):
            process,acquired,release=self.start()
            self.assertFalse(acquired.wait(.08));self.assertTrue(process.is_alive())
        self.assertTrue(acquired.wait(2));release.set();process.join(2);self.assertEqual(process.exitcode,0)
    def test_new_child_after_old_plan_before_ex_replan_preserves_parent(self):
        inventory={'base':set(),'old':set()};old_requested={'old'}
        with Barrier(self.path):publish(inventory,'new-child','old')
        with Barrier(self.path,exclusive=True,nonblocking=True):
            result,removed=maintained_inventory(inventory,old_requested,set())
        self.assertEqual(removed,set());self.assertIn('old',result)
        self.assertTrue(all(parent in result for parents in result.values() for parent in parents))
    def test_current_producer_roots_protect_parent_before_child_exists(self):
        inventory={'source-base':set(),'unused':set()}
        with Barrier(self.path,exclusive=True,nonblocking=True):
            result,removed=maintained_inventory(inventory,set(inventory),{'source-base'})
        self.assertEqual(removed,{'unused'});self.assertIn('source-base',result)
    def test_next_writer_refuses_or_explicitly_rebases_removed_parent(self):
        inventory={'base':set(),'obsolete':set()}
        with Barrier(self.path,exclusive=True,nonblocking=True):
            inventory,removed=maintained_inventory(inventory,{'obsolete'},set())
        self.assertEqual(removed,{'obsolete'})
        with Barrier(self.path):
            with self.assertRaisesRegex(ValueError,'Parent missing'):publish(inventory,'child','obsolete')
            self.assertNotIn('child',inventory)
            self.assertEqual(publish(inventory,'child','obsolete','base'),'base')
    def test_controller_crash_releases_exclusive(self):
        process,acquired,release=self.start(exclusive=True);self.assertTrue(acquired.wait(2))
        process.terminate();process.join(2)
        with Barrier(self.path,nonblocking=True):pass
    def test_controller_timeout_kill_releases_exclusive(self):
        process,acquired,release=self.start(exclusive=True);self.assertTrue(acquired.wait(2))
        process.join(.05);self.assertTrue(process.is_alive())
        process.kill();process.join(2)
        with Barrier(self.path,exclusive=True,nonblocking=True):pass


if __name__=='__main__':unittest.main()
