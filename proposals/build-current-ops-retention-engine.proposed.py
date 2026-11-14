#!/usr/bin/env python3
"""New inactive engine copy for already restored canonical Ops dependency kits."""
import importlib.util,shutil
from pathlib import Path

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;base=load('parallel_base',here/'build-native-parallel-engine.proposed.py');out=base.build(original,destination);kit=load('kit',here/'current-ops-kit-closure.proposed.py')
 shutil.copyfile(here/'current-ops-kit-closure.proposed.py',out/'current_ops_kit_closure.py')
 (out/'retention-plan.py').write_text(kit.patch_planner((out/'retention-plan.py').read_text()));return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
