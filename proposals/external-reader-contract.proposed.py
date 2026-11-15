"""Explicit external-only GHA serialization contract; local default remains SH."""
import hashlib,os,re
from pathlib import Path
WORKFLOW_SHA256='e1f27020e3f3bba20d71d75ffcfc8c8c01327f592ca74a0cacde301bbd7f593e'
MODE='github-serialized-readonly-native-trial'
SCHEDULED_MODE='github-serialized-readonly-scheduled-audit'
SCHEDULED_WORKFLOW_SHA256='063b2405c4e565d957569a2f8a0153e220ae38e7d5e861cc20969729f8d81f2c'
def require(ok):
 if not ok:raise ValueError('External reader contract not established')
def verify(env):
 mode=env.get('NEO_EXTERNAL_READER_MODE');require(mode in(MODE,SCHEDULED_MODE))
 scheduled=mode==SCHEDULED_MODE
 workflow='retention-audit.yml'if scheduled else'retention-readonly-check.yml'
 expected={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'Bruce7771/neo-backup-operations','GITHUB_REF':'refs/heads/main','GITHUB_JOB':'audit'if scheduled else'readonly-maintenance','GITHUB_WORKFLOW_REF':'Bruce7771/neo-backup-operations/.github/workflows/'+workflow+'@refs/heads/main'}
 require(all(env.get(k)==v for k,v in expected.items()))
 event=env.get('GITHUB_EVENT_NAME');require(event in('schedule','workflow_dispatch')if scheduled else event=='workflow_dispatch')
 sha=env.get('GITHUB_SHA','');require(re.fullmatch('[0-9a-f]{40}',sha)is not None and env.get('NEO_REVIEWED_TRIAL_COMMIT')==sha)
 require(all(env.get(k,'').isdigit()for k in('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')))
 root=Path(env.get('GITHUB_WORKSPACE',''));require(root.is_absolute()and root.is_dir())
 path=root/'.github/workflows'/workflow;require(path.is_file()and not path.is_symlink()and path.resolve().is_relative_to(root.resolve()))
 expected_hash=SCHEDULED_WORKFLOW_SHA256 if scheduled else WORKFLOW_SHA256
 require(hashlib.sha256(path.read_bytes()).hexdigest()==expected_hash)
 return {'execution':'actual-scheduled-main-GHA-job'if scheduled and event=='schedule'else'actual-manual-main-GHA-job','reader_mode':mode,'workflow_sha256':expected_hash,'concurrency_group':'backup-repository-maintenance','cancel_in_progress':False,'protected_environment':'NEO_BACKUP_MAINTENANCE','credential_class':'audit-read-list-only','native_shared_lock_used':False,'relies_on_serialized_external_GC_contract':True}
def command(args,env):
 if not env.get('NEO_EXTERNAL_READER_MODE'):return args
 verify(env);require(isinstance(args,list)and args and args[0]=='restic')
 tail=[a for a in args[1:]if a!='--no-lock'];clean=[a for a in tail if a!='--no-cache'];require(clean)
 verb=clean[0]
 require(verb in('version','snapshots','cat','dump','restore','check','forget'))
 if verb=='forget':require('--dry-run'in clean and '--json'in clean and '--prune'not in clean)
 return ['restic','--no-lock']+tail