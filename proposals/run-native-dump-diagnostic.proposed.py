#!/usr/bin/env python3
"""ONE manual metadata-only cold dump. Never runs a retention planner or cleanup."""
import hashlib,importlib.util,json,os,re,tempfile,time
from pathlib import Path
SNAPSHOT='e07b1c90d384ddc4b3a83074cc1abeccc9cea451d6c7ff3e52f3c8cdb907a99d'
MANIFEST='/var/lib/neo-main-pitr/capture/base/backup_manifest'
EXPECTED_SHA='b0c4df4d55096add07c19b28bebc5afb41d93da735323bcbab1b1f77d91e0443'
EXPECTED_BYTES=655839

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def main():
 os.umask(0o077);here=Path(__file__).resolve().parent;contract=load('diag_external_contract',here/'external-reader-contract.proposed.py');guard=contract.verify(dict(os.environ))
 if any(v for k,v in os.environ.items()if any(w in k.upper()for w in('MASTER','MAINTENANCE_KEY','SSH_PRIVATE'))):raise ValueError('Unexpected elevated credential')
 root=Path(os.environ['RUNNER_TEMP']).resolve();module=load('controlled_native_dump',here/'native-dump-controlled-diagnostic.proposed.py');started=time.monotonic();proofs=[]
 with tempfile.TemporaryDirectory(prefix='neo-one-native-manifest-diagnostic-',dir=root)as tmp:
  work=Path(tmp);work.chmod(0o700);env=dict(os.environ);password=env.pop('NEO_RESTIC_PASSWORD');file=work/'password';file.write_text(password);file.chmod(0o600);password=None;env['RESTIC_PASSWORD_FILE']=str(file);env['XDG_CACHE_HOME']=str(work/'cache')
  def save(x):
   proofs.append(x);print(json.dumps({'scope':'one-controlled-native-manifest-dump','native':x,'execution_contract':guard,'old_failed_snapshot_ID_known':False,'target_is_current_independently_restored_PITR':True,'normal_retention_25_540_limits_changed':False,'retention_planner_invoked':False,'delete_or_prune_invoked':False}),flush=True)
  raw=module.diagnostic_dump(['restic','--no-lock','dump',SNAPSHOT,MANIFEST],env,work,8*1024*1024,90,started+120,save)
  if len(raw)!=EXPECTED_BYTES or hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA:raise ValueError('Reviewed manifest identity mismatch')
  value=json.loads(raw)
  if value.get('PostgreSQL-Backup-Manifest-Version')not in(1,2):raise ValueError('Not a native PG manifest')
  print(json.dumps({'scope':'controlled-native-manifest-dump-result','snapshot':SNAPSHOT,'manifest_sha256':EXPECTED_SHA,'manifest_bytes':len(raw),'native_manifest_version':value['PostgreSQL-Backup-Manifest-Version'],'elapsed_seconds':round(time.monotonic()-started,3),'native_CLI_invocations':1,'ok':True,'retention_admission_proved':False,'deletion_enabled':False}),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  print(json.dumps({'scope':'controlled-native-manifest-dump-result','ok':False,'failure_type':type(e).__name__,'retention_admission_proved':False,'deletion_enabled':False}),flush=True);raise SystemExit(1)
