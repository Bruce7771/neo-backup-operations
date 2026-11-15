#!/usr/bin/env python3
"""Inactive, explicitly reviewed long-bounded readonly diagnostic engine copy."""
import importlib.util
from pathlib import Path

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def build(original,destination):
 here=Path(__file__).parent
 base=load('long_cold_base',here/'build-cold-native-retention-engine.proposed.py')
 out=base.build(original,destination)
 once=load('long_once',here/'retention-safety-candidate.py').once
 p=out/'staged_derive.py';s=p.read_text()
 s=once(s,'0<=now()-self.start<540','0<=now()-self.start<4500')
 s=once(s,'self.metadata_end=self.start+240;self.finalize_end=self.start+270;self.job_end=self.start+540','self.metadata_end=self.start+3600;self.finalize_end=self.start+3630;self.job_end=self.start+4500')
 # A segment can roll over with <35 seconds left, so 30 segments do not
 # necessarily provide 3600 seconds. The independent global bound still wins.
 s=once(s,"self.segments<=2,'Two metadata segments exhausted'","self.segments<=43,'Long metadata segments exhausted'")
 compile(s,str(p),'exec');p.write_text(s)
 p=out/'retention-audit.py';s=p.read_text()
 s=once(s,'derivation_deadline_seconds=240,segment_deadline_seconds=120,job_deadline_seconds=540','derivation_deadline_seconds=3600,segment_deadline_seconds=120,job_deadline_seconds=4500')
 compile(s,str(p),'exec');p.write_text(s)
 p=out/'retention-readonly-check.py';s=p.read_text()
 s=once(s,"budget.phase_timeout('finalize',270)","budget.phase_timeout('finalize',3630)")
 compile(s,str(p),'exec');p.write_text(s)
 return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
