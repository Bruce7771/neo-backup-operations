#!/usr/bin/env python3
"""Inactive complete known configuration admission; no broad path allowance."""
import importlib.util,shutil
from pathlib import Path

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;base=load('complete_controls_base',here/'build-reviewed-controls-retention-engine.proposed.py');out=base.build(original,destination);once=load('complete_once',here/'retention-safety-candidate.py').once
 shutil.copyfile(here/'reviewed-composed-control.proposed.py',out/'reviewed_composed_control.py')
 p=out/'retention-plan.py';s=p.read_text()
 s=once(s,'from reviewed_control_artifacts import reviewed_controls','from reviewed_control_artifacts import reviewed_controls\nfrom reviewed_composed_control import reviewed_composed_control')
 s=once(s,'    standalone_controls=reviewed_controls(inventory,protected,CONFIG_SCOPES)','    standalone_controls=reviewed_controls(inventory,protected,CONFIG_SCOPES)\n    composed_controls=reviewed_composed_control(inventory,protected,CONFIG_SCOPES)')
 s=once(s,"if row['id']in standalone_controls:continue","if row['id']in standalone_controls or row['id']in composed_controls:continue")
 s=once(s,'"independent_control_artifacts_preserved":standalone_controls,','"independent_control_artifacts_preserved":standalone_controls,\n        "typed_composed_control_dependencies":composed_controls,')
 compile(s,str(p),'exec');p.write_text(s);return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
