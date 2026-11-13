#!/usr/bin/env python3
"""Exact inventory transition guards; no repository or credential access."""
import ast
import importlib.util
from pathlib import Path
import unittest

source=Path(__file__).with_name('retention-coordinator.py')
spec=importlib.util.spec_from_file_location('coordinator',source)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


class Coordinator(unittest.TestCase):
    def test_exact_approved_forget_transition(self):
        self.assertEqual(c.mutation_transition([{'id':'a'},{'id':'b'}],[{'id':'b'}],['a']),set())
    def test_unapproved_disappearance_rejected(self):
        with self.assertRaises(ValueError):c.mutation_transition([{'id':'a'},{'id':'b'}],[],['a'])
    def test_immutable_old_record_change_rejected(self):
        with self.assertRaises(ValueError):c.mutation_transition([{'id':'a'},{'id':'b','tag':'old'}],[{'id':'b','tag':'new'}],['a'])
    def test_new_snapshot_requires_gc_replan(self):
        self.assertEqual(c.mutation_transition([{'id':'a'},{'id':'b'}],[{'id':'b'},{'id':'c'}],['a']),{'c'})
    def test_no_service_pause_or_server_fence_command(self):
        tree=ast.parse(source.read_text())
        literals=[n.value for n in ast.walk(tree)if isinstance(n,ast.Constant)and isinstance(n.value,str)]
        self.assertNotIn('systemctl',literals);self.assertNotIn('acquire 300',literals)
        self.assertNotIn('release',literals);self.assertNotIn('unlock',literals)
        self.assertIn('writer-status',literals)


if __name__=='__main__':unittest.main()
