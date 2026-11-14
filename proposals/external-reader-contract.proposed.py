"""Explicit external-only GHA serialization contract; local default remains SH."""
import hashlib,os,re
from pathlib import Path
WORKFLOW_SHA256='0ccf6fcffc91b9aeea4b16f3072c1d106064d27f9696856b5818327d6b10b730'
MODE='github-serialized-readonly-native-trial'
def require(ok):
 if not ok:raise ValueError('External reader contract not established')
def verify(env):
 require(env.get('NEO_EXTERNAL_READER_MODE')==MODE)
 expected={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'Bruce7771/neo-backup-operations','GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_JOB':'readonly-maintenance','GITHUB_WORKFLOW_REF':'Bruce7771/neo-backup-operations/.github/workflows/retention-readonly-check.yml@refs/heads/main'}
 require(all(env.get(k)==v for k,v in expected.items()))
 sha=env.get('GITHUB_SHA','');require(re.fullmatch('[0-9a-f]{40}',sha)is not None and env.get('NEO_REVIEWED_TRIAL_COMMIT')==sha)
 require(all(env.get(k,'').isdigit()for k in('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')))
 root=Path(env.get('GITHUB_WORKSPACE',''));require(root.is_absolute()and root.is_dir())
 path=root/'.github/workflows/retention-readonly-check.yml';require(path.is_file()and not path.is_symlink()and path.resolve().is_relative_to(root.resolve()))
 require(hashlib.sha256(path.read_bytes()).hexdigest()==WORKFLOW_SHA256)
 return {'execution':'actual-manual-main-GHA-job','reader_mode':MODE,'workflow_sha256':WORKFLOW_SHA256,'concurrency_group':'backup-repository-maintenance','cancel_in_progress':False,'protected_environment':'NEO_BACKUP_MAINTENANCE','credential_class':'audit-read-list-only','native_shared_lock_used':False,'relies_on_serialized_external_GC_contract':True}
def command(args,env):
 if not env.get('NEO_EXTERNAL_READER_MODE'):return args
 verify(env);require(isinstance(args,list)and args and args[0]=='restic')
 tail=[a for a in args[1:]if a!='--no-lock'];clean=[a for a in tail if a!='--no-cache'];require(clean)
 verb=clean[0]
 require(verb in('version','snapshots','cat','dump','restore','check','forget'))
 if verb=='forget':require('--dry-run'in clean and '--json'in clean and '--prune'not in clean)
 return ['restic','--no-lock']+tail