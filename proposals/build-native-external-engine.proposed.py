#!/usr/bin/env python3
"""Generate only an inactive external-contract engine COPY; no cloud call."""
import importlib.util,shutil
from pathlib import Path

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;base=load('native_builder',here/'build-native-engine.proposed.py');out=base.build(original,destination)
 safety=load('safety',here/'retention-safety-candidate.py')
 shutil.copyfile(here/'external-reader-contract.proposed.py',out/'external_reader_contract.py')
 batch=(out/'hourly_metadata_batch.py').read_text()
 batch=safety.once(batch,'from types import MappingProxyType','from types import MappingProxyType\nfrom external_reader_contract import command as external_command')
 batch=safety.once(batch,' process=subprocess.Popen(args,',' args=external_command(args,env)\n process=subprocess.Popen(args,')
 (out/'hourly_metadata_batch.py').write_text(batch)
 audit=(out/'retention-audit.py').read_text()
 audit=safety.once(audit,'from hourly_recovery import derive','from hourly_recovery import derive\nfrom external_reader_contract import command as external_command')
 audit=safety.once(audit,'    try:\n        return subprocess.run(args,env=env,',"    if args and args[0]=='restic':args=external_command(args,env)\n    try:\n        return subprocess.run(args,env=env,")
 audit=safety.once(audit,"subprocess.run(['restic','dump',snapshot,path],env=env,","subprocess.run(external_command(['restic','dump',snapshot,path],env),env=env,")
 (out/'retention-audit.py').write_text(audit)
 # Extend fixed numeric diagnostic allowlist ONLY in this inactive copy.
 checker=(out/'retention-readonly-check.py').read_text()
 old="{'native_batches','checkpoint_reads','selected_json_bytes','v3_points_authenticated'}"
 new="{'native_batches','checkpoint_reads','selected_json_bytes','v3_points_authenticated','memory_payload_hits','native_v3_four_json_points','legacy_full_manifest_points','catalog_native_pg_root_reads','catalog_native_subtree_reads','catalog_tree_cache_hits','catalog_full_outer_seed_reads','catalog_cli_processes','catalog_cli_selected_bytes'}"
 checker=safety.once(checker,old,new)
 (out/'retention-readonly-check.py').write_text(checker)
 return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
