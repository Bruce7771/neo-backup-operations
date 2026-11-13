#!/usr/bin/env python3
"""Generate a NEW inactive engine copy; never change actual scripts/deployment."""
import importlib.util,shutil
from pathlib import Path

def load(path):
 s=importlib.util.spec_from_file_location('candidate_builder',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 original=Path(original);destination=Path(destination);destination.mkdir(mode=0o700,exist_ok=False)
 proposals=Path(__file__).parent;m=load(proposals/'retention-safety-candidate.py')
 for source in original.glob('*.py'):shutil.copyfile(source,destination/source.name)
 shutil.copyfile(original/'hourly_metadata_batch.py',destination/'hourly_metadata_batch_legacy.py')
 shutil.copyfile(proposals/'native-hourly-integration.proposed.py',destination/'hourly_metadata_batch.py')
 shutil.copyfile(proposals/'retention-safety-candidate.py',destination/'retention_safety_candidate.py')
 catalog=(proposals/'native-pg-catalog-authentication.proposed.py').read_text()
 catalog=m.once(catalog,'max_trees=512,max_rows=20000):','max_trees=512,max_rows=20000,authenticated_file_origin=None):')
 catalog=m.once(catalog,"need(bool(repository_binding),'Repository binding required');self.binding=repository_binding;", "need(callable(authenticated_file_origin),'Native file provenance callback required');self.authenticated_file_origin=authenticated_file_origin\n  need(bool(repository_binding),'Repository binding required');self.binding=repository_binding;")
 catalog=m.once(catalog,'  nodes,pg_tree=self.nodes(sid);',"  need(self.authenticated_file_origin(sid,self.root+'/postgres-selfcontained/sealed-pg.json',sealed_raw)is True,'Native seal provenance rejected')\n  nodes,pg_tree=self.nodes(sid);")
 (destination/'native_pg_catalog_v2.py').write_text(catalog)
 audit=m.audit_candidate((original/'retention-audit.py').read_text())
 audit=m.once(audit,'from hourly_metadata_batch import HourlyMetadataBatch','from hourly_metadata_batch import NativeHourlyMetadataBatch as HourlyMetadataBatch')
 # Original audit's bounded direct dump also uses native default shared locks.
 audit=m.once(audit,"['restic','--no-lock','dump',snapshot,path]","['restic','dump',snapshot,path]")
 expected="['restic','--no-lock','snapshots','--json']"
 if audit.count(expected)!=2:raise ValueError('Unexpected inventory reader source')
 audit=audit.replace(expected,"['restic','snapshots','--json']")
 audit=m.once(audit,'        plan_paths=[Path(plans[i])', '        dump.native_pg_catalog=metadata_batch.verify_catalog\n        plan_paths=[Path(plans[i])')
 (destination/'retention-audit.py').write_text(audit)
 (destination/'hourly_selfcontained_v3.py').write_text(m.v3_catalog_candidate((original/'hourly_selfcontained_v3.py').read_text()))
 return destination
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
