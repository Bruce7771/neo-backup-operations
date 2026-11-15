#!/usr/bin/python3
"""Manual ephemeral-runner proposal. No repository writes or production access."""
import datetime,hashlib,importlib.util,json,os,pathlib,re,selectors,shutil,signal,stat,subprocess,tarfile,tempfile,time
P=pathlib.Path;MAX_IMAGE=400_000_000;MAX_SOURCE=1_100_000_000;MAX_EXTRACT=1_400_000_000;MAX_SMALL=65536;RESERVE=4_000_000_000
FULL_PATHS={'/var/lib/neo-main-daily-online/capture','/srv/neo-recovery/object-storage/objects'}
CAPTURE='/var/lib/neo-main-daily-online/capture';VALIDATOR_SHA='fc21d64edd5613caf1709b9f87d1ec53191b6fd191458372176a81756d7d10f9'
NAMES=['main-runtime-image.docker.tar','origin-proof.json','Dockerfile.neo-runtime','requirements.txt','build-baseline-vps.sh']
class Refused(Exception):pass
def need(x,code):
 if not x:raise Refused(code)
def hex64(x):return isinstance(x,str)and re.fullmatch('[0-9a-f]{64}',x)is not None
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def inputs(env):
 snapshot=env.get('NEO_IMAGE_SNAPSHOT','');origin=env.get('NEO_IMAGE_ORIGIN_SHA256','');image=env.get('NEO_IMAGE_ARCHIVE_SHA256','');directory=env.get('NEO_IMAGE_DIRECTORY','')
 need(all(hex64(x)for x in(snapshot,origin,image)),'INPUT_HEX_REQUIRED');need(directory=='runtime-image','INPUT_DIRECTORY_REQUIRED');return snapshot,origin,image,directory
def snapshot_scope(value):
 need(value.get('hostname')=='srv2140404-main-daily-composed'and'neo-daily-composed-v1'in value.get('tags',[])and set(value.get('paths',[]))==FULL_PATHS,'MAIN_FULL_SNAPSHOT_SCOPE_REQUIRED')
def native_listing(raw,paths):
 found={}
 for line in raw.splitlines():
  v=json.loads(line)
  if v.get('struct_type')!='node':continue
  path=v.get('path')
  if path in paths:
   need(path not in found and v.get('type')=='file'and type(v.get('size'))is int,'INVALID_RESTORED_NODE');maximum=MAX_IMAGE if path.endswith('/'+NAMES[0])else MAX_SMALL;need(0<=v['size']<=maximum,'RESTORE_FILE_SIZE_CEILING');found[path]=v['size']
 need(set(found)==set(paths),'FIVE_EXACT_FILES_REQUIRED');return found
def loaded_identity(v,origin,expected_tags):
 root=origin['image_id'];config='sha256:'+origin['config_sha256'];need(v.get('Id')in(root,config),'LOADED_IMAGE_IDENTITY_REQUIRED')
 need(v.get('RootFS',{}).get('Layers')==origin['ordered_diff_ids']and v.get('Os')==origin['os']and v.get('Architecture')==origin['architecture'],'LOADED_ROOTFS_PLATFORM_REQUIRED')
 c=v.get('Config')or{};need(c.get('User')=='1000:1000'and c.get('WorkingDir')=='/app'and c.get('Cmd')==['python3']and c.get('Entrypoint')is None,'LOADED_RUNTIME_CONFIG_REQUIRED')
 need(sorted(v.get('RepoTags')or[])==sorted(expected_tags),'LOADED_TAGS_DIFFER');need(sorted(x.split('=',1)[0]for x in c.get('Env',[]))==origin['config_env_names'],'LOADED_ENV_NAMES_DIFFER')
 return'oci-index'if v['Id']==root else'classic-config'
def stop(p):
 if p.poll()is None:
  p.send_signal(signal.SIGINT)
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
def cleanup_synthetic_permissions(work,temporary,image,base_env):
 need(work.resolve()==work and work.parent==temporary and work.name.startswith('neo-main-image-cold-'),'CLEANUP_NAMESPACE_REQUIRED')
 data=work/'synthetic-data'
 if not image or not data.exists():return
 need(data.resolve()==data and data.is_dir(),'SYNTHETIC_CLEANUP_PATH_REQUIRED')
 program="import os,stat\nfor root,dirs,files in os.walk('/cleanup',followlinks=False):\n if root!='/cleanup':os.chmod(root,0o777)\n for name in files:\n  p=os.path.join(root,name)\n  if not os.path.islink(p):os.chmod(p,0o666)"
 result=subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','1000:1000','--pids-limit','32','--memory','64m','--cpus','1','--mount','type=bind,source='+str(data)+',target=/cleanup',image,'python3','-B','-c',program],env=base_env,capture_output=True,timeout=20)
 need(result.returncode==0,'SYNTHETIC_PERMISSION_CLEANUP_REQUIRED')
def selected_source(name):
 p=P(name)
 need(not p.is_absolute()and '..'not in p.parts,'UNSAFE_SOURCE_MEMBER')
 if p.name.startswith('.env')or p.name.lower()in('secrets.json','credentials.json')or p.suffix.lower()in('.key','.pem','.p12','.pfx','.token'):return False
 if any(part in('uploads','user_uploads','node_modules','__pycache__')for part in p.parts):return False
 if name.endswith(('.env','.db','.sqlite','.sqlite3'))and name!='data/catalog_seed.db':return False
 return name.startswith(('backend/','apps/neoacademy/','frontend/'))or name in('data/catalog_seed.db','data/catalog_seed_manifest.json','scripts/__init__.py','scripts/bootstrap_neo_agents_production.py','scripts/seed_neo_agents.py','scripts/release_neo_agents_incremental.py')
def extract_source(archive,target):
 total=count=0
 with tarfile.open(archive,'r|gz')as source:
  for member in source:
   name=member.name.removeprefix('./')
   if not selected_source(name)or member.isdir():continue
   if not member.isfile():continue
   need(not name.endswith(('.env','.db','.sqlite','.sqlite3'))or name=='data/catalog_seed.db','PRIVATE_DATA_NOT_SOURCE')
   need(member.size<=MAX_EXTRACT and total+member.size<=MAX_EXTRACT,'SOURCE_EXTRACT_CEILING')
   path=target/name;path.parent.mkdir(parents=True,exist_ok=True);need(path.resolve().is_relative_to(target),'UNSAFE_SOURCE_TARGET')
   with source.extractfile(member)as inp,path.open('xb')as output:shutil.copyfileobj(inp,output,1024*1024)
   path.chmod(0o644);total+=member.size;count+=1
 for path in target.rglob('*'):
  if path.is_dir():path.chmod(0o755)
 target.chmod(0o755)
 need((target/'backend/app/startup_entrypoint.py').is_file()and(target/'data/catalog_seed.db').is_file(),'ACTUAL_NEO_AND_CATALOG_REQUIRED')
 return {'selected_files':count,'selected_bytes':total,'user_rows_or_media_extracted':False}
def actual_neo_probe(run,image,work,source,container):
 data=work/'synthetic-data';data.mkdir(mode=0o777);data.chmod(0o777)
 cfg={'PYTHONPATH':'/app:/app/apps/neoacademy','PYTHONDONTWRITEBYTECODE':'1','PYTHON_DOTENV_DISABLED':'1','APP_ENV':'test','APP_SECRET_KEY':'synthetic-cold-acceptance-only-at-least-thirty-two-characters','NEO_TOOLS_DB_PATH':'/app/data/app.db','NEO_DATABASE_URL':'sqlite+aiosqlite:////app/data/portal.db','ACADEMY_DB_PATH':'/app/data/academy.db','PORTAL_DB_PATH':'/app/data/academy.db','NEO_CATALOG_SEED_PATH':'/seed/catalog_seed.db','NEO_CATALOG_SEED_MANIFEST':'/seed/catalog_seed_manifest.json','NEO_AGENTS_ENABLED':'0','NEO_SOCIAL_WORKER':'0','NEO_COUNCIL_RECOVERY_ENABLED':'0','NEO_STARTUP_DIAGNOSTICS':'1','PORT':'8000','REAL_CHECKOUT':'0'}
 cfg.update({k:'0'for k in('NEO_SOCIAL_DISCOVERY','NEO_SOCIAL_AI','NEO_SOCIAL_MONITORING','NEO_SOCIAL_ANALYTICS','NEO_SOCIAL_PUBLICATION','NEO_SOCIAL_CONNECTIONS')})
 envfile=work/'synthetic.env';envfile.write_text(''.join(k+'='+v+'\n'for k,v in cfg.items()));envfile.chmod(0o600)
 base=['docker','run','--name',container,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--user','1000:1000','--pids-limit','256','--memory','1536m','--cpus','1','--tmpfs','/tmp:rw,nosuid,nodev,size=134217728','--env-file',str(envfile),'--workdir','/app','--mount','type=bind,source='+str(source)+',target=/app,readonly','--mount','type=bind,source='+str(data)+',target=/app/data']
 for name in('catalog_seed.db','catalog_seed_manifest.json'):base+=['--mount','type=bind,source='+str(source/'data'/name)+',target=/seed/'+name+',readonly']
 prepare="from backend.app.tools.db import init_db;init_db();from backend.app.tools.chat_runtime_schema import migrate;migrate();from sqlalchemy import create_engine;import backend.app.workspace.models;from backend.app.social.models import SocialRecord,SocialJob,SocialWebhook;engine=create_engine('sqlite:////app/data/portal.db');[model.__table__.create(engine,checkfirst=True)for model in(SocialRecord,SocialJob,SocialWebhook)];engine.dispose();import sqlite3;c=sqlite3.connect('/app/data/portal.db');c.execute('CREATE TABLE IF NOT EXISTS phone_antifraud_settings(setting_key TEXT PRIMARY KEY,setting_value TEXT,value_type TEXT)');c.commit();c.close()"
 run(base+['--rm',image,'python3','-B','-c',prepare],'SYNTHETIC_SCHEMA_ONLY',timeout=45)
 run(base[:2]+['-d']+base[2:]+[image,'python3','-B','-m','backend.app.startup_entrypoint','uvicorn','--port','8000'],'ACTUAL_NEO_START',timeout=20)
 probe="import urllib.request,json;r=urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=1);v=json.load(r);assert r.status==200 and v.get('catalog')=='ok';print(json.dumps({'status':r.status,'catalog':v['catalog']}))"
 end=time.monotonic()+100
 while time.monotonic()<end:
  p=subprocess.run(['docker','exec',container,'python3','-B','-c',probe],capture_output=True,text=True,timeout=4)
  if p.returncode==0:
   import sqlite3
   c=sqlite3.connect('file:'+str(data/'app.db')+'?mode=ro',uri=True)
   try:
    need(c.execute('PRAGMA quick_check').fetchall()==[('ok',)],'SYNTHETIC_TOOLS_INTEGRITY_REQUIRED');count=c.execute('SELECT count(*) FROM tools').fetchone()[0];need(count>=1000,'REAL_CATALOG_SEED_REQUIRED')
   finally:c.close()
   return {'actual_Neo_entrypoint':True,'network':'none','synthetic_schema_only':True,'health':json.loads(p.stdout),'catalog_rows':count,'tools_quick_check':True,'provider_calls':0}
  status=subprocess.run(['docker','inspect','--format','{{.State.Running}}',container],capture_output=True,text=True,timeout=3)
  if status.returncode==0 and status.stdout.strip()=='false':raise Refused('ACTUAL_NEO_PROCESS_EXITED_BEFORE_HEALTH')
  time.sleep(1)
 raise Refused('ACTUAL_NEO_HEALTH_NOT_READY')
def main():
 env=os.environ;snapshot,origin_sha,image_sha,directory=inputs(env)
 need(hex64(env.get('NEO_MAIN_ARCHIVE_SHA256'))and re.fullmatch('[0-9a-f]{40}',env.get('NEO_MAIN_SHA',''))and re.fullmatch('[0-9]{1,10}',env.get('NEO_MAIN_ARCHIVE_BYTES','')),'MAIN_SOURCE_INPUTS_REQUIRED');need(0<int(env['NEO_MAIN_ARCHIVE_BYTES'])<=MAX_SOURCE,'MAIN_SOURCE_SIZE_REQUIRED')
 need(env.get('GITHUB_ACTIONS')=='true'and env.get('GITHUB_EVENT_NAME')=='workflow_dispatch'and env.get('GITHUB_REPOSITORY')=='Bruce7771/neo-backup-operations'and env.get('GITHUB_REF')=='refs/heads/main','REVIEWED_MANUAL_RUNNER_REQUIRED')
 need(env.get('NEO_REVIEWED_COMMIT')==env.get('GITHUB_SHA')and re.fullmatch('[0-9a-f]{40}',env.get('GITHUB_SHA','')),'REVIEWED_COMMIT_REQUIRED')
 temporary=P(env['RUNNER_TEMP']);need(temporary.resolve()==temporary and temporary.is_dir(),'RUNNER_TEMP_REQUIRED');need(shutil.disk_usage(temporary).free>=8_500_000_000,'INITIAL_COLD_CAPACITY_REQUIRED')
 os.umask(0o077);work=P(tempfile.mkdtemp(prefix='neo-main-image-cold-',dir=temporary));restore=work/'restore';restore.mkdir(mode=0o700);password=work/'repository-password';password.write_text(env['NEO_RESTIC_PASSWORD']);password.chmod(0o600)
 base_env={k:env[k]for k in('PATH','HOME','TMPDIR')if k in env};base_env.update(DOCKER_HOST='unix:///var/run/docker.sock',DOCKER_CONFIG=str(work/'docker-config'))
 restic_env=dict(base_env,RESTIC_REPOSITORY=env['RESTIC_REPOSITORY'],RESTIC_PASSWORD_FILE=str(password),AWS_ACCESS_KEY_ID=env['AWS_ACCESS_KEY_ID'],AWS_SECRET_ACCESS_KEY=env['AWS_SECRET_ACCESS_KEY'],AWS_DEFAULT_REGION=env['AWS_DEFAULT_REGION'])
 result={'scope':'ephemeral-main-current-cold-restore','status':'failed','image_archive_only':False,'main_application_code_or_database_run':False,'provider_calls':0,'b2_mutations':0,'restic_disk_cache_disabled':True};phase='admission';owned_image=None;container='neo-main-image-cold-'+work.name.rsplit('-',1)[-1];started_container=False;docker_root=None
 def guard():
  need(shutil.disk_usage(work).free>=RESERVE,'RUNNER_DISK_RESERVE')
  if docker_root is not None:need(shutil.disk_usage(docker_root).free>=RESERVE,'DOCKER_DISK_RESERVE')
  total=0
  for root,dirs,files in os.walk(restore):
   for name in files:
    p=P(root)/name;s=p.lstat();need(stat.S_ISREG(s.st_mode)and not p.is_symlink(),'UNEXPECTED_RESTORE_NODE');total+=s.st_size
  need(total<=MAX_IMAGE+MAX_SOURCE+4*MAX_SMALL,'RESTORE_WORKSPACE_CEILING')
 def run(args,label,timeout=120,child_env=None,maxout=262144):
  guard();start=time.monotonic();out=bytearray();err=bytearray();p=subprocess.Popen(args,env=child_env or base_env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  try:
   with selectors.DefaultSelector()as sel:
    sel.register(p.stdout,selectors.EVENT_READ,'out');sel.register(p.stderr,selectors.EVENT_READ,'err')
    while sel.get_map():
     need(time.monotonic()-start<timeout,label+'_TIMEOUT');guard()
     for key,_ in sel.select(.2):
      b=os.read(key.fd,65536)
      if not b:sel.unregister(key.fileobj);continue
      target=out if key.data=='out'else err;target.extend(b);need(len(target)<=maxout,label+'_OUTPUT_CEILING')
   rc=p.wait(timeout=max(.1,timeout-(time.monotonic()-start)))
   if rc:
    result['failed_process']={'phase':label,'exit_status':rc,'stderr_bytes':len(err),'stderr_sha256':hashlib.sha256(err).hexdigest()};raise Refused(label+'_EXIT_NONZERO')
   return bytes(out)
  finally:stop(p);p.stdout.close();p.stderr.close()
 restic=['restic','--no-lock','--no-cache']
 try:
  phase='local-docker-admission';info=json.loads(run(['docker','info','--format','{"root":{{json .DockerRootDir}},"driver":{{json .Driver}},"driver_status":{{json .DriverStatus}}}'],'DOCKER_INFO'));docker_root=P(info['root']);guard()
  before=set(run(['docker','image','ls','-aq','--no-trunc'],'DOCKER_BASELINE').decode().split());result['target_docker_storage']={k:v for k,v in info.items()if k!='root'}
  phase='snapshot-scope';snapshot_scope(json.loads(run([*restic,'cat','snapshot',snapshot],'SNAPSHOT_SCOPE',child_env=restic_env,maxout=MAX_SMALL)))
  prefix=CAPTURE+'/'+directory;wanted=[prefix+'/'+name for name in NAMES]
  phase='five-file-preflight';sizes=native_listing(run([*restic,'ls','--json','--recursive',snapshot,prefix],'FIVE_FILE_METADATA',child_env=restic_env,maxout=MAX_SMALL),wanted)
  phase='native-five-file-restore';cmd=[*restic,'restore',snapshot,'--verify','--target',str(restore)]
  for path in wanted:cmd+=['--include',path]
  source_path=CAPTURE+'/release-kit/main-source.tar.gz';cmd+=['--include',source_path]
  run(cmd,'EXACT_RESTORE',timeout=360,child_env=restic_env)
  archive=restore/source_path.lstrip('/');need(archive.is_file()and archive.stat().st_size==int(env['NEO_MAIN_ARCHIVE_BYTES'])and archive.stat().st_size<=MAX_SOURCE and sha(archive)==env['NEO_MAIN_ARCHIVE_SHA256'],'EXACT_MAIN_SOURCE_ARCHIVE_REQUIRED')
  source=work/'source';source.mkdir(mode=0o755);result['source_extraction']=extract_source(archive,source)
  result['main_sha']=env['NEO_MAIN_SHA'];need(re.fullmatch('[0-9a-f]{40}',result['main_sha']),'MAIN_SHA_REQUIRED')
  files={name:restore/(prefix.lstrip('/')+'/'+name)for name in NAMES}
  for name,p in files.items():need(p.resolve().is_relative_to(restore)and p.is_file()and not p.is_symlink()and p.stat().st_size==sizes[prefix+'/'+name],'RESTORED_PATH_SIZE_REQUIRED')
  phase='origin-and-archive-validation';need(sha(files['origin-proof.json'])==origin_sha,'ORIGIN_HASH_REQUIRED');origin=json.loads(files['origin-proof.json'].read_text())
  need(origin.get('scope')=='main-generated-runtime-image-preservation'and origin.get('kind')=='generated-main-runtime-image-docker-save'and origin.get('local_archive_readback_verified')is True and origin.get('image_identity_authenticated')is True,'POSITIVE_MAIN_IMAGE_ORIGIN_REQUIRED')
  need(origin.get('archive_sha256')==image_sha and origin.get('archive_bytes')==files[NAMES[0]].stat().st_size and 0<origin['archive_bytes']<=MAX_IMAGE and len(origin.get('ordered_diff_ids',[]))==11,'EXACT_IMAGE_ORIGIN_REQUIRED')
  need(origin.get('os')=='linux'and origin.get('architecture')=='amd64'and hex64(origin.get('config_sha256'))and re.fullmatch('sha256:[0-9a-f]{64}',origin.get('image_id','')),'IMAGE_ID_PLATFORM_REQUIRED')
  aliases={origin['image_id'],'sha256:'+origin['config_sha256']};need(not aliases.intersection(before),'CUSTOM_IMAGE_TARGET_NOT_EMPTY')
  recipes=origin.get('validated_recipes')or origin.get('recipes');need(isinstance(recipes,list)and{v['name']for v in recipes}==set(NAMES[2:]),'THREE_RECIPE_MANIFEST_REQUIRED')
  for row in recipes:need(files[row['name']].stat().st_size==row['bytes']and sha(files[row['name']])==row['sha256'],'RECIPE_HASH_REQUIRED')
  validator=P(__file__).with_name('main-image-stream-validator.proposed.py');need(sha(validator)==VALIDATOR_SHA,'VALIDATOR_CODE_REQUIRED');spec=importlib.util.spec_from_file_location('reviewed_main_image_validator',validator);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  with files[NAMES[0]].open('rb')as f:verified=m.validate_stream(f,origin['image_id'],origin['ordered_diff_ids'],origin['archive_bytes'],image_sha,expected_platform={'os':origin['os'],'architecture':origin['architecture']})
  need(verified['image_identity_authenticated']and verified['config_sha256']==origin['config_sha256'],'AUTHENTICATED_IMAGE_GRAPH_REQUIRED')
  with tarfile.open(files[NAMES[0]],'r:')as archive:manifest=json.load(archive.extractfile('manifest.json'))
  need(isinstance(manifest,list)and len(manifest)==1,'ONE_LOAD_TARGET_REQUIRED');tags=manifest[0].get('RepoTags')or[];need(isinstance(tags,list)and all(isinstance(x,str)for x in tags),'LOAD_TAGS_REQUIRED')
  for tag in tags:
   probe=subprocess.run(['docker','image','inspect',tag],env=base_env,capture_output=True,timeout=15);need(probe.returncode!=0,'TAG_TARGET_NOT_EMPTY')
  phase='cold-load-ephemeral-docker';run(['docker','image','load','--input',str(files[NAMES[0]])],'DOCKER_LOAD',timeout=120)
  after=set(run(['docker','image','ls','-aq','--no-trunc'],'DOCKER_AFTER').decode().split());loaded=list(aliases.intersection(after));need(len(loaded)==1,'LOADED_ALIAS_AMBIGUITY');owned_image=loaded[0];v=json.loads(run(['docker','image','inspect',owned_image],'LOADED_INSPECT'))[0];loaded_kind=loaded_identity(v,origin,tags)
  result.update(native_restore_verify=True,exact_image_archive_sha_verified=True,image_graph_verified=True,cold_docker_load_verified=True,ordered_layers_verified=11,loaded_identity_kind=loaded_kind,source_identity_kind=origin['image_identity_kind'])
  phase='network-none-actual-Neo-probe';started_container=True
  result['actual_Neo_startup_attempted']=True
  observed=actual_neo_probe(run,owned_image,work,source,container);server=json.loads(run(['docker','version','--format','{{json .Server}}'],'ENGINE_VERSION'))
  result.update(status='success',native_restore_verify=True,restored_files=6,exact_image_archive_sha_verified=True,image_graph_verified=True,ordered_layers_verified=11,loaded_identity_kind=loaded_kind,source_identity_kind=origin['image_identity_kind'],attestation_descriptors_verified=verified['attestation_descriptors_verified'],attestation_signer_trust_claimed=False,source_engine=origin.get('docker_engine'),target_engine={k:server.get(k)for k in('Version','ApiVersion','Os','Arch')},runtime_probe=observed,main_application_code_or_database_run=True,real_user_data_mounted=False)
 except BaseException as exc:
  result.update(status='failed',phase=phase,failure_code=str(exc)if isinstance(exc,Refused)else type(exc).__name__)
  if phase=='network-none-actual-Neo-probe'and started_container:
   logs=subprocess.run(['docker','logs','--tail','100',container],env=base_env,capture_output=True,timeout=5);events=[]
   for line in(logs.stdout+logs.stderr).decode(errors='replace').splitlines():
    if '[neo-startup-safe]'not in line:continue
    try:
     value=json.loads(line.split('[neo-startup-safe]',1)[1]);entry={k:value[k]for k in('event','phase','exit_code')if k in value}
     entry['exceptions']=[{'type':str(v.get('type',''))[:120],'frames':[{k:f[k]for k in('file','function','line')if k in f}for f in v.get('frames',[])[-6:]]}for v in value.get('exceptions',[])[:4]];events.append(entry)
    except(ValueError,TypeError,AttributeError):pass
   result['safe_startup_events']=events[-5:]
 finally:
  if started_container:subprocess.run(['docker','rm','-f',container],env=base_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
  cleanup_synthetic_permissions(work,temporary,owned_image,base_env)
  if owned_image and owned_image not in before:subprocess.run(['docker','image','rm',owned_image],env=base_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
  need(work.resolve()==work and work.parent==temporary and work.name.startswith('neo-main-image-cold-'),'CLEANUP_NAMESPACE_REQUIRED');shutil.rmtree(work);result['ephemeral_files_removed']=True;print(json.dumps(result,sort_keys=True))
 return 0 if result['status']=='success'else 1
if __name__=='__main__':
 previous={s:signal.signal(s,lambda *_:(_ for _ in()).throw(InterruptedError('runner cancellation')))for s in(signal.SIGINT,signal.SIGTERM)}
 try:raise SystemExit(main())
 except Refused as e:print(json.dumps({'status':'refused','failure_code':str(e)}));raise SystemExit(1)
 finally:
  for s,h in previous.items():signal.signal(s,h)
