"""Inactive wiring to existing SSH/bounded native callbacks and native engine.

No credentials, SSH identity, service, workflow, account or B2 client is created.
Caller keeps existing maintenance capability validation, exact owner review and
external same-group/credential-holder admission. No prune interface exists.
"""
import hashlib,importlib.util,json,pathlib,time

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
HERE=pathlib.Path(__file__).parent
core=load('publication_bound_core',HERE/'publication-coordinator-core.proposed.py')
tail=load('publication_same_job',HERE/'same-job-fresh-tail.proposed.py')

class ExistingSSH:
 """Use existing pinned SSH argv/environment and existing bounded executor."""
 def __init__(self,argv,env,bounded,*,now=time.monotonic):
  self.argv=tuple(argv);self.env=dict(env);self.bounded=bounded;self.now=now
  core.need(argv and pathlib.Path(argv[0]).name=='ssh','Existing reviewed SSH argv required')
  core.need(not any(k.startswith(('NEO_','AWS_','RESTIC_'))for k in env),'SSH subprocess must not inherit provider/B2 credentials')
 def call(self,command,body,*,rpc_timeout=15,deadline=None):
  core.need(command in('writer-status','publication-acquire','publication-begin-forget','publication-acknowledge','publication-release'),'Literal publication verb required')
  timeout=min(15,rpc_timeout,deadline-self.now()if deadline is not None else 15)
  core.need(timeout>0,'Publication SSH deadline exhausted')
  raw=self.bounded(list(self.argv)+[command],self.env,timeout,input=core.canonical(body))
  core.need(deadline is None or self.now()<deadline,'Publication SSH exceeded monotonic deadline')
  core.need(len(raw)<=65536,'Bounded SSH status response required');r=json.loads(raw)
  core.need(r.get('ok')is not False,'Remote publication command refused');return r
 def status(self):return self.call('writer-status',{})
 def acquire(self,nonce,policy,maximum,**budget):return self.call('publication-acquire',dict(owner_nonce=nonce,producer_policy_sha256=policy,maximum_seconds=maximum),**budget)
 def begin_forget(self,nonce,candidate,timeout,**budget):return self.call('publication-begin-forget',dict(owner_nonce=nonce,candidate_sha256=candidate,native_timeout_seconds=timeout),**budget)
 def acknowledge(self,nonce,*,native_exit_zero,exact_transition_verified,**budget):return self.call('publication-acknowledge',dict(owner_nonce=nonce,native_exit_zero=native_exit_zero,exact_transition_verified=exact_transition_verified),**budget)
 def release(self,nonce,**budget):return self.call('publication-release',dict(owner_nonce=nonce),**budget)

def revalidate(bundle,policy,static,planner,fixed_hold):
 core.need(bundle.get('schema')==1 and bundle.get('policy')==policy,'Exact current native preplan required')
 core.need(set(static['protected'])<=set(bundle['protected'])and bundle['restored']==static['restored']and bundle['dependencies']==static['dependencies'],'Current owner recovery metadata differs')
 for e in static['hourly_overrides']:core.need(e in bundle['hourly_recovery'],'Reviewed legacy override missing')
 for e in policy.get('protected_unknown_hourly',[]):core.need(e in bundle['hourly_recovery'],'Immutable UNKNOWN evidence changed')
 roots=fixed_hold(bundle['inventory'],policy)if policy.get('unknown_recovery_hold_mode')=='reviewed-as-of-immutable-root-set'else None
 rebuilt=planner.build(bundle['inventory'],bundle['plans'],bundle['protected'],bundle['restored'],bundle['dependencies'],bundle['hourly_recovery'],roots)
 core.need(all(bundle['candidate'].get(k)==v for k,v in rebuilt.items()),'Actual planner disagrees with private preplan')
 return dict(rebuilt,inventory_stable_for_admission=bundle['candidate'].get('inventory_stable_for_admission')is True)

def fresh_native(cache,engine,native_env,work,native_call,policy,static,deadline):
 """Existing four-JSON/native catalog transport, <=45s, only append-tail reads."""
 import sys
 engine=pathlib.Path(engine);work=pathlib.Path(work);sys.path.insert(0,str(engine))
 from hourly_metadata_batch import NativeHourlyMetadataBatch,native_locked_restore
 from native_parallel_transport import ParallelNativeCLI
 from hourly_recovery import derive
 from retention_safety_candidate import scoped_rule_suffix,move_explicit_holds_before_derive
 planner=load('publication_fresh_actual_planner',engine/'retention-plan.py')
 planner.SCOPES={s['host']:(s['tag'],frozenset(s['paths']))for s in policy['scopes']}
 planner.CONFIG_SCOPES={(s['host'],s['tag']):s['paths'][0]for s in policy.get('configuration_scopes',[])}
 planner.FULL_MAIN_HOST=next(s['host']for s in policy['scopes']if s['kind']=='daily')
 def call(args,maximum_seconds=10):
  left=deadline-time.monotonic();core.need(left>0,'Fresh native deadline exhausted');return native_call(args,min(maximum_seconds,left))
 def inventory():return json.loads(call(['snapshots','--json']))
 rows=inventory();cache.prepare(rows,policy,static);plans=[]
 for scope in policy['scopes']:
  args=['forget','--dry-run','--json','--host',scope['host'],'--tag',scope['tag'],'--group-by','host']+scoped_rule_suffix(scope)
  plans.append(json.loads(call(args)))
 plans=move_explicit_holds_before_derive(plans,static['protected'])
 limits=cache.transport_limits();selected=work/'fresh-native-metadata';selected.mkdir(mode=0o700)
 reader=ParallelNativeCLI(native_env,deadline,selected,max_live=limits['max_live'],process_limit=limits['process_limit'],byte_limit=limits['byte_limit'])
 hourly=next(s for s in policy['scopes']if s['kind']=='hourly')
 batch=NativeHourlyMetadataBatch(selected,native_env,rows,hourly,deadline,reader=reader)
 batch.stats['selected_json_bytes']=cache.used_json
 def dump(sid,path,maximum):
  if path.startswith(hourly['paths'][0]+'/'):return batch.get(sid,path,maximum)
  return reader.read(['dump',sid,path],maximum)
 dump.native_pg_catalog=batch.verify_catalog;dump.publication_tail_limits=limits;dump.publication_selected_json_usage=lambda:batch.stats['selected_json_bytes']
 try:
  candidate=tail.fresh_replan(cache,rows,plans,policy,static,derive,planner,dump,inventory,deadline=deadline)
  return candidate,rows
 except BaseException:reader.cancel_all();raise

def coordinate(bundle,engine,native_env,work,native_call,policy,static,
               rpc,producer_policy_sha256,expected_review_digest,review_digest,
               external_admission,postcheck):
 """Existing coordinator calls here AFTER scoped auth and full native preplan.

 `external_admission` must retain the reviewed actual serialized GHA execution
 and other credential-holder checks; this module never substitutes a JSON flag.
 """
 engine=pathlib.Path(engine);planner=load('publication_initial_actual_planner',engine/'retention-plan.py')
 planner.SCOPES={s['host']:(s['tag'],frozenset(s['paths']))for s in policy['scopes']}
 planner.CONFIG_SCOPES={(s['host'],s['tag']):s['paths'][0]for s in policy.get('configuration_scopes',[])}
 planner.FULL_MAIN_HOST=next(s['host']for s in policy['scopes']if s['kind']=='daily')
 fixed=load('publication_initial_asof',engine/'asof_recovery_hold.py').fixed_hold
 candidate=revalidate(bundle,policy,static,planner,fixed)
 if not candidate['remove_snapshot_ids']:return {'result':'zero-candidate-noop','hold_acquired':False,'deleted_snapshots':0,'prune':False,**postcheck(candidate)}
 external_admission();cache=tail.SameJobEvidence(bundle,policy,static,lambda b,p,s:revalidate(b,p,s,planner,fixed))
 def fresh(deadline):
  result=fresh_native(cache,engine,native_env,work,native_call,policy,static,deadline)
  external_admission() # Still inside the 45s pre-native deadline; never billed as native execution.
  core.need(time.monotonic()<deadline,'External admission exhausted fresh-tail deadline')
  return result
 def native_forget(ids,timeout):
  native_call(['--retry-lock','0s','forget','--json']+ids,timeout)
 return core.execute(candidate,expected_review_digest,review_digest,producer_policy_sha256,rpc,
  fresh,
  native_forget,lambda timeout:json.loads(native_call(['snapshots','--json'],timeout)),postcheck)
