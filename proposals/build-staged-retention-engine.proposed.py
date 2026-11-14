#!/usr/bin/env python3
"""Build NEW inactive staged engine. Actual scripts/workflow remain unchanged."""
import importlib.util,shutil
from pathlib import Path

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;base=load('ops_base',here/'build-current-ops-retention-engine.proposed.py');out=base.build(original,destination);m=load('staged_safety',here/'retention-safety-candidate.py');once=m.once
 shutil.copyfile(here/'staged-derive.proposed.py',out/'staged_derive.py')
 p=out/'hourly_recovery.py';s=p.read_text();s=once(s,'def derive(inventory,plans,policy,overrides,restored,dump):','def derive(inventory,plans,policy,overrides,restored,dump,child_subset=None,child_observer=None):')
 anchor="    children=sorted(sid for sid in retained if authorized(rows[sid],'hourly'))"
 s=once(s,anchor,anchor+"\n    if child_observer is not None:child_observer(tuple(children))\n    if child_subset is not None:\n        require(isinstance(child_subset,list)and len(child_subset)==len(set(child_subset))and set(child_subset)<=set(children),'Invalid staged child subset')\n        children=[sid for sid in children if sid in child_subset]")
 p.write_text(s)
 p=out/'retention-audit.py';s=p.read_text();s=once(s,'from hourly_recovery import derive','from hourly_recovery import derive\nfrom staged_derive import Budget,staged_derive')
 s=once(s,"SAFE_DIAGNOSTIC={'phase':'initialize'}","SAFE_DIAGNOSTIC={'phase':'initialize'}\nBUDGET=None")
 s=once(s,'def run(args, env, timeout=45):','def run(args, env, timeout=45):\n    if BUDGET is not None:timeout=BUDGET.phase_timeout(\'finalize\'if SAFE_DIAGNOSTIC[\'phase\']in(\'validate-candidate\',\'final-inventory\')else\'metadata\',timeout)')
 s=once(s,'def main():\n    env=dict(os.environ)','def main():\n    global BUDGET\n    BUDGET=Budget(float(os.environ[\'NEO_STAGED_JOB_START\']))\n    env=dict(os.environ)')
 s=once(s,'deadline=time.monotonic()+180','deadline=BUDGET.metadata_end');s=once(s,"derive_started_monotonic=deadline-180","derive_started_monotonic=BUDGET.start")
 s=once(s,'remaining=deadline-time.monotonic()','remaining=min(deadline,BUDGET.segment_end or deadline)-time.monotonic()')
 old="edge_inventory,parents,updated=derive(json.loads(inventory),\n            held_plans,policy,\n            json.loads((work/'hourly-recovery.json').read_text()),\n            json.loads((work/'restored.json').read_text()),dump)"
 new="edge_inventory,parents,updated=staged_derive(derive,json.loads(inventory),\n            held_plans,policy,\n            json.loads((work/'hourly-recovery.json').read_text()),\n            json.loads((work/'restored.json').read_text()),dump,metadata_batch,BUDGET,work/'staged-private')"
 s=once(s,old,new);s=once(s,"time.monotonic()-(deadline-180)","time.monotonic()-BUDGET.start");s=once(s,'derivation_deadline_seconds=180','derivation_deadline_seconds=240,segment_deadline_seconds=120,job_deadline_seconds=540')
 s=once(s,"'native_parallel_transport.py'","'native_parallel_transport.py','staged_derive.py'")
 p.write_text(s)
 p=out/'retention-readonly-check.py';s=p.read_text();s=once(s,'import tempfile','import tempfile\nimport time\nfrom staged_derive import Budget')
 s=once(s,'os.umask(0o077);env=dict(os.environ)','os.umask(0o077);env=dict(os.environ);budget=Budget();env[\'NEO_STAGED_JOB_START\']=repr(budget.start)')
 s=once(s,'check=True,timeout=240','check=True,timeout=budget.phase_timeout(\'finalize\',270)')
 s=once(s,"timeout=180 if arguments[-1]=='check'else 90)","timeout=budget.phase_timeout('integrity'if arguments[-1]=='check'else'component',180 if arguments[-1]=='check'else 90))")
 s=once(s,"'catalog_peak_children_rss_kib'}","'catalog_peak_children_rss_kib','staged_completed_children','staged_segments','staged_cache_bytes','staged_final_replay_verified'}")
 s=once(s,"'native_parallel_transport.py'","'native_parallel_transport.py','staged_derive.py'")
 # Permit only the new fixed module name in sanitized failure frames.
 s=once(s,"'native_parallel_catalog.py'","'native_parallel_catalog.py','staged_derive.py'")
 p.write_text(s)
 return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])