#!/usr/bin/env python3
"""Synthetic public-run census; no network or tokens."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('external',Path(__file__).with_name('external_writer_observation.py'))
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)


class External(unittest.TestCase):
    def fixture(self,other=False):
        def fetch(url):
            if '/actions/'not in url:return {'private':False,'full_name':'fixture/ops'}
            rows=[{'id':1,'status':'in_progress','head_sha':'a'*40}]
            if other:rows.append({'id':2,'status':'in_progress','head_sha':'b'*40})
            return {'total_count':len(rows),'workflow_runs':rows}
        return fetch
    def test_self_run_only_not_busy(self):
        r=e.observe(['fixture/ops'],'fixture/ops','1',self.fixture(),lambda:1000)
        self.assertEqual(r['other_running_jobs'],0);self.assertFalse(r['token_used'])
    def test_unknown_other_run_conservatively_busy(self):
        self.assertEqual(e.observe(['fixture/ops'],'fixture/ops','1',self.fixture(True),lambda:1000)['other_running_jobs'],1)
    def test_private_repository_requires_other_reviewed_interface(self):
        with self.assertRaises(ValueError):e.observe(['fixture/ops'],'fixture/ops','1',lambda _: {'private':True})


if __name__=='__main__':unittest.main()
