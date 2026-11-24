#!/usr/bin/env python3
"""Existing weekly audit: exact-source, serialized, auditor-only, no mutations."""
import importlib.util,json,os,subprocess,sys,tempfile
from pathlib import Path

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def configure_cold_inventory_deadline(engine):
 """Give the scheduled job time to populate its private cache from B2."""
 here=Path(__file__).resolve().parent
 once=load('scheduled_audit_source_guard',here/'retention-safety-candidate.py').once
 audit=engine/'retention-audit.py'
 source=audit.read_text()
 source=once(source,"inventory=run(['restic','snapshots','--json'],env)",
             "inventory=run(['restic','snapshots','--json'],env,timeout=240)")
 compile(source,str(audit),'exec')
 audit.write_text(source)

def main():
 os.umask(0o077);here=Path(__file__).resolve().parent
 contract=load('contract',here/'external-reader-contract.proposed.py');proof=contract.verify(dict(os.environ))
 # Audit3 has no upload/delete permission. No maintenance/master/SSH injection.
 if any(v for k,v in os.environ.items()if any(w in k.upper()for w in('MASTER','MAINTENANCE_KEY','SSH_PRIVATE'))):raise ValueError('Unexpected elevated credential in readonly trial')
 root=Path(os.environ['RUNNER_TEMP']).resolve();builder=load('builder',here/'build-unverified-base-family-retention-engine.proposed.py')
 with tempfile.TemporaryDirectory(prefix='neo-native-external-trial-',dir=root)as tmp:
  folder=Path(tmp);folder.chmod(0o700);engine=builder.build(here.parent/'scripts',folder/'engine')
  configure_cold_inventory_deadline(engine)
  print(json.dumps({'scope':'explicit-native-external-trial-contract',**proof}),flush=True)
  subprocess.run([sys.executable,str(engine/'retention-readonly-check.py')],env=dict(os.environ),stdin=subprocess.DEVNULL,check=True,timeout=4500)
if __name__=='__main__':
 try:main()
 except Exception as error:
  print('::error::Native external trial failed closed ('+type(error).__name__+'); no apply or deployment',file=sys.stderr);raise SystemExit(1)
