"""Private SAME-JOB preplan evidence reuse; never cross-run resume or a reader.

Only construct from the current trusted native engine's private validation
bundle. No load/save/CLI. Native immutable bytes were authenticated by that
engine; the actual planner is still invoked for every fresh candidate.
"""
import copy,hashlib,json,os,time

def require(x,m):
 if not x:raise ValueError(m)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def hourly(row,policy):
 s=next(x for x in policy['scopes']if x['kind']=='hourly');return row.get('hostname')==s['host']and s['tag']in row.get('tags',[])and set(row.get('paths',[]))==set(s['paths'])
class SameJobEvidence:
 def __init__(self,bundle,policy,static,validate_preplan,now=time.monotonic):
  require(bundle.get('schema')==1,'Trusted native bundle schema required');validate_preplan(bundle,policy,static)
  self.pid=os.getpid();self.now=now;self.created=now();self.policy=copy.deepcopy(policy);self.static=copy.deepcopy(static);self.rows={r['id']:copy.deepcopy(r)for r in bundle['inventory']};require(len(self.rows)==len(bundle['inventory']),'Duplicate initial inventory')
  edges=bundle.get('all_classified_hourly_recovery');require(isinstance(edges,list),'Native preplan ALL-classified evidence required');self.edges={e['child_snapshot']:copy.deepcopy(e)for e in edges};require(len(self.edges)==len(edges)and set(self.edges)=={sid for sid,r in self.rows.items()if hourly(r,policy)},'Preplan all-hourly proof incomplete')
  self.bases=frozenset(bundle.get('accepted_restore_base_sha256',[]));require(all(isinstance(x,str)and len(x)==64 for x in self.bases),'Invalid compatible base evidence')
  stats=bundle['candidate'].get('hourly_metadata_read',{});require(stats.get('staged_final_replay_verified')==1,'Native full replay acceptance required');self.used_calls=stats.get('catalog_cli_processes',0);self.used_bytes=stats.get('catalog_cli_selected_bytes',0);self.current=None;self.fresh_started=False
  self.used_json=stats.get('selected_json_bytes',0);require(type(self.used_json)is int and 0<=self.used_json<=256*1024*1024,'Initial selected JSON cap invalid')
  self.seal=hashlib.sha256(canonical([self.rows,self.edges,sorted(self.bases),self.policy,self.static,self.used_calls,self.used_bytes,self.used_json])).hexdigest()
 def __reduce__(self):raise TypeError('Same-job authority is not serializable')
 def guard(self,policy,static):
  require(self.pid==os.getpid()and 0<=self.now()-self.created<=900,'Same-job proof expired or crossed process');require(policy==self.policy and static==self.static,'Current policy/evidence changed');require(hashlib.sha256(canonical([self.rows,self.edges,sorted(self.bases),self.policy,self.static,self.used_calls,self.used_bytes,self.used_json])).hexdigest()==self.seal,'Private preplan evidence changed')
 def prepare(self,inventory,policy,static):
  self.guard(policy,static);rows={r['id']:r for r in inventory};require(len(rows)==len(inventory)and set(self.rows)<=set(rows),'Old snapshot disappeared or duplicate');require(all(rows[sid]==old for sid,old in self.rows.items()),'Immutable old snapshot metadata differs');added=set(rows)-set(self.rows);require(len(added)<=8,'Fresh append tail exceeds bounded admission');needed={sid for sid in added if hourly(rows[sid],policy)};require(len(needed)<=2,'Fresh hourly tail exceeds short HOLD budget');self.current=rows;return needed
 def restore_bases(self,inventory,policy,restored):
  self.guard(policy,self.static);require(restored==self.static['restored']and self.current=={r['id']:r for r in inventory},'Fresh derive context was not validated');return set(self.bases)
 def edge(self,sid):
  require(self.current is not None and sid in self.current,'Snapshot outside fresh context');return copy.deepcopy(self.edges.get(sid))
 def transport_limits(self):
  calls=4096-self.used_calls;size=512*1024*1024-self.used_bytes;selected=256*1024*1024-self.used_json;require(calls>0 and size>0 and selected>0,'Same-job native resource cap exhausted');return {'process_limit':min(calls,64),'byte_limit':min(size,32*1024*1024),'selected_json_limit':min(selected,32*1024*1024),'max_live':4}

def fresh_replan(cache,inventory,plans,policy,static,derive,planner,dump,confirm_inventory,*,deadline,now=time.monotonic):
 """Call only under durable publication HOLD. No forget/prune is performed."""
 require(not cache.fresh_started,'One fresh-tail admission attempt per preplan; no replay');cache.fresh_started=True
 require(deadline-now()<=45 and deadline>now(),'Fresh metadata must fit <=45seconds');cache.prepare(inventory,policy,static);limits=cache.transport_limits()
 # Caller creates existing native transport with limits+absolute deadline;
 # this function never creates a new/native/cloud reader or resets job caps.
 require(getattr(dump,'publication_tail_limits',None)==limits,'Bounded existing native transport not established')
 edges,parents,updated=derive(inventory,plans,policy,static['hourly_overrides'],static['restored'],dump,same_job_cache=cache)
 usage=getattr(dump,'publication_selected_json_usage',None);require(callable(usage),'Current native selected-JSON accounting required');selected=usage()
 require(type(selected)is int and cache.used_json<=selected<=cache.used_json+limits['selected_json_limit'],'Same-job selected JSON cap exceeded')
 require(now()<deadline,'Fresh tail metadata deadline exhausted')
 protected=sorted(set(static['protected'])|set(parents))
 from asof_recovery_hold import fixed_hold
 roots=fixed_hold(inventory,policy)if policy.get('unknown_recovery_hold_mode')=='reviewed-as-of-immutable-root-set'else None
 candidate=planner.build(inventory,updated,protected,static['restored'],static['dependencies'],edges,roots)
 require(confirm_inventory()==inventory,'Publication changed under HOLD; unsupported producer');require(now()<deadline,'Final fresh metadata deadline exhausted');candidate['inventory_stable_for_admission']=True;return candidate
