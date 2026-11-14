#!/usr/bin/env python3
"""New inactive engine copy: valid restic empty-node compatibility + diagnostics."""
import importlib.util
from pathlib import Path

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build(original,destination):
 here=Path(__file__).parent;safety=load('size_safety',here/'retention-safety-candidate.py');base=load('external_base',here/'build-native-external-engine.proposed.py');out=base.build(original,destination)
 cat=(out/'native_pg_catalog_v2.py').read_text()
 cat=safety.once(cat,"type(n.get('size'))is int and n['size']>=0","type(n.get('size',0))is int and n.get('size',0)>=0")
 cat=safety.once(cat,"(n['size']==0 and not ids)or(n['size']>0 and bool(ids))","(n.get('size',0)==0 and not ids)or(n.get('size',0)>0 and bool(ids))")
 cat=safety.once(cat,"files[rel]={'bytes':n['size'],'content':tuple(n.get('content')or[])}","files[rel]={'bytes':n.get('size',0),'content':tuple(n.get('content')or[])}")
 (out/'native_pg_catalog_v2.py').write_text(cat)
 batch=(out/'hourly_metadata_batch.py').read_text();start=batch.index('  result=self.catalog.verify(sid,files,sealed_raw,');old=batch[start:]
 expected="""  result=self.catalog.verify(sid,files,sealed_raw,
      lambda snapshot,path:self.reader.read(['dump',snapshot,path],8*1024*1024))
  self.stats.update({'catalog_'+k:v for k,v in self.catalog.stats.items()})
  self.stats['catalog_cli_processes']=self.reader.calls;self.stats['catalog_cli_selected_bytes']=self.reader.output_bytes
  return result"""
 replacement="""  try:
   return self.catalog.verify(sid,files,sealed_raw,
       lambda snapshot,path:self.reader.read(['dump',snapshot,path],8*1024*1024))
  finally:
   self.stats.update({'catalog_'+k:v for k,v in self.catalog.stats.items()})
   self.stats['catalog_cli_processes']=self.reader.calls;self.stats['catalog_cli_selected_bytes']=self.reader.output_bytes"""
 batch=safety.once(batch,expected,replacement);(out/'hourly_metadata_batch.py').write_text(batch)
 audit=(out/'retention-audit.py').read_text();audit=safety.once(audit,"'hourly_selfcontained_v3.py','asof_recovery_hold.py'}","'hourly_selfcontained_v3.py','asof_recovery_hold.py','native_pg_catalog_v2.py'}")
 audit=safety.once(audit,"and frame.name!='require'","and frame.name not in('require','need')")
 (out/'retention-audit.py').write_text(audit)
 checker=(out/'retention-readonly-check.py').read_text();checker=safety.once(checker,"'hourly_selfcontained_v3.py','asof_recovery_hold.py',None)","'hourly_selfcontained_v3.py','asof_recovery_hold.py','native_pg_catalog_v2.py',None)")
 (out/'retention-readonly-check.py').write_text(checker);return out
if __name__=='__main__':
 import sys;build(sys.argv[1],sys.argv[2])
