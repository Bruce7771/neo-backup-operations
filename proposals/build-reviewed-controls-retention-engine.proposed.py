#!/usr/bin/env python3
"""Inactive exact-artifact admission on current long-bounded engine only."""
import importlib.util,shutil
from pathlib import Path

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;base=load('control_long_base',here/'build-long-bounded-retention-engine.proposed.py');out=base.build(original,destination);once=load('control_once',here/'retention-safety-candidate.py').once
 shutil.copyfile(here/'reviewed-control-artifacts.proposed.py',out/'reviewed_control_artifacts.py')
 p=out/'retention-plan.py';s=p.read_text()
 s=once(s,'import unittest','import unittest\nfrom reviewed_control_artifacts import reviewed_controls')
 s=once(s,'    rows = {row["id"]: row for row in inventory}','    rows = {row["id"]: row for row in inventory}\n    standalone_controls=reviewed_controls(inventory,protected,CONFIG_SCOPES)')
 s=once(s,"            if row.get('hostname')==host and tag in row.get('tags',[]):","            if row.get('hostname')==host and tag in row.get('tags',[]):\n                if row['id']in standalone_controls:continue")
 s=once(s,'"configuration_deltas_preserved":len(config_ids),','"configuration_deltas_preserved":len(config_ids),\n        "independent_control_artifacts_preserved":standalone_controls,')
 compile(s,str(p),'exec');p.write_text(s);return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
