#!/usr/bin/env python3
"""Inactive copy only: four RAW readers, main-thread authentication/LRU."""
import importlib.util,shutil
from pathlib import Path

def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;safety=load('parallel_safety',here/'retention-safety-candidate.py');base=load('empty_base',here/'build-native-empty-file-fix.proposed.py');out=base.build(original,destination)
 for source,name in [('native-parallel-transport.proposed.py','native_parallel_transport.py'),('native-parallel-catalog.proposed.py','native_parallel_catalog.py')]:shutil.copyfile(here/source,out/name)
 batch=(out/'hourly_metadata_batch.py').read_text()
 batch=safety.once(batch,'from native_pg_catalog_v2 import NativePGCatalog','from native_parallel_catalog import ParallelPGCatalog as NativePGCatalog\nfrom native_parallel_transport import ParallelNativeCLI')
 batch=safety.once(batch,'self.reader=reader or BoundedNativeCLI(env,deadline,self.cache)','self.reader=reader or ParallelNativeCLI(env,deadline,self.cache)')
 batch=safety.once(batch,'authenticated_file_origin=self.assert_native_origin)','authenticated_file_origin=self.assert_native_origin,cancel_callback=getattr(self.reader,\'cancel_all\',lambda:None))')
 batch=safety.once(batch,"self.stats['catalog_cli_processes']=self.reader.calls;self.stats['catalog_cli_selected_bytes']=self.reader.output_bytes", "self.stats['catalog_cli_processes']=self.reader.calls;self.stats['catalog_cli_selected_bytes']=self.reader.output_bytes\n   self.stats['catalog_max_live_children']=getattr(self.reader,'max_live_children',0)\n   self.stats['catalog_peak_children_rss_kib']=getattr(self.reader,'peak_children_rss_kib',0)")
 (out/'hourly_metadata_batch.py').write_text(batch)
 for filename in ('retention-audit.py','retention-readonly-check.py'):
  s=(out/filename).read_text();s=safety.once(s,"'asof_recovery_hold.py','native_pg_catalog_v2.py'","'asof_recovery_hold.py','native_pg_catalog_v2.py','native_parallel_catalog.py','native_parallel_transport.py'")
  if filename=='retention-readonly-check.py':
   s=safety.once(s,"'catalog_cli_processes','catalog_cli_selected_bytes'}","'catalog_cli_processes','catalog_cli_selected_bytes','catalog_tree_cache_evictions','catalog_max_parallel_fetches','catalog_max_live_children','catalog_peak_children_rss_kib'}")
  (out/filename).write_text(s)
 return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
