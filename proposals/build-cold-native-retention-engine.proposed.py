#!/usr/bin/env python3
"""Inactive engine copy: one cold native PITR manifest read, same global budget."""
import importlib.util
from pathlib import Path

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;base=load('staged_base',here/'build-staged-retention-engine.proposed.py');out=base.build(original,destination);once=load('once_guard',here/'retention-safety-candidate.py').once
 p=out/'retention-audit.py';s=p.read_text()
 s=once(s,'        def dump(snapshot,path,maximum):','        cold_pitr_manifest_used=False\n        def dump(snapshot,path,maximum):\n            nonlocal cold_pitr_manifest_used')
 old="""            with tempfile.TemporaryFile(dir=work) as output:
                subprocess.run(external_command(['restic','dump',snapshot,path],env),env=env,
                    stdout=output,stderr=subprocess.DEVNULL,check=True,
                    timeout=min(25,remaining),preexec_fn=restrict_output)"""
 new="""            with tempfile.TemporaryFile(dir=work) as output:
                maximum_seconds=25
                if (not cold_pitr_manifest_used and maximum==8*1024*1024
                    and path.endswith('/base/backup_manifest')):
                    maximum_seconds=90
                    cold_pitr_manifest_used=True
                # Recompute immediately before the child: do not reset any
                # staged segment, metadata240, or whole-job540 deadline.
                remaining=min(deadline,BUDGET.segment_end or deadline,BUDGET.job_end)-time.monotonic()
                if remaining<=0:
                    raise TimeoutError('Same-job native metadata read budget exhausted')
                subprocess.run(external_command(['restic','dump',snapshot,path],env),env=env,
                    stdout=output,stderr=subprocess.DEVNULL,check=True,
                    timeout=min(maximum_seconds,remaining),preexec_fn=restrict_output)"""
 s=once(s,old,new);compile(s,str(p),'exec');p.write_text(s);return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
