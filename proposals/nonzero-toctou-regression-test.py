#!/usr/bin/env python3
"""Exact external-DAG race counterexample + mandatory production-path block.

All IDs/data are synthetic; no backend, process, key or service is touched.
"""
import ast
import copy
import importlib.util
from pathlib import Path
import unittest

root=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
fixture=load('admission_fixture',Path(__file__).with_name('lease-admission-test.py'))
c=load('blocked_coordinator',Path(__file__).with_name('retention-coordinator.py'))


class PublicationRace(unittest.TestCase):
    def test_completed_new_child_invalidates_quiescent_old_plan(self):
        args=list(fixture.Admission().fixture());bundle=args[0]
        parent=next(row for row in bundle['inventory']if row['id']=='d'*64)
        kept_pitr=next(row for row in bundle['inventory']if row['id']=='b'*64)
        parent.update({key:copy.deepcopy(kept_pitr[key])for key in('hostname','tags','paths')})
        candidate=fixture.planner.build(bundle['inventory'],bundle['plans'],bundle['protected'],bundle['restored'],[],bundle['hourly_recovery'])
        candidate['inventory_stable_for_admission']=True;bundle['candidate']=candidate
        args[3]=fixture.a.removal_review_digest(candidate,args[1],args[4],args[2])
        # The second plan completed. Before the next writer/lock observations,
        # another supported writer committed a new child, then exited cleanly.
        new_child={'id':'e'*64,'wal_snapshot':'d'*64}
        self.assertEqual(args[7]['active_known_writer_units'],[])
        self.assertEqual(args[9]['total_locks'],0)
        lease=fixture.a.admit(*args)
        self.assertTrue(lease['admitted']) # demonstrates the old assumption gap
        hypothetical_remaining={row['id']for row in bundle['inventory']}|{new_child['id']}
        hypothetical_remaining-=set(candidate['remove_snapshot_ids'])
        self.assertNotIn(new_child['wal_snapshot'],hypothetical_remaining)
        # Production proposal cannot reach forget, even if all old flags pass.
        with self.assertRaisesRegex(ValueError,'NONZERO DISABLED'):
            c.require_atomic_publication_boundary()
    def test_hard_guard_precedes_first_forget_and_is_not_an_environment_flag(self):
        tree=ast.parse(Path(c.__file__).read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main')
        calls=[n for n in ast.walk(main)if isinstance(n,ast.Call)]
        guard=next(n for n in calls if isinstance(n.func,ast.Name)and n.func.id=='require_atomic_publication_boundary')
        forget=next(n for n in calls if isinstance(n.func,ast.Name)and n.func.id=='native_call'
                    and any(isinstance(x,ast.Constant)and x.value=='forget'for x in ast.walk(n)))
        self.assertLess(guard.lineno,forget.lineno)


if __name__=='__main__':unittest.main()
