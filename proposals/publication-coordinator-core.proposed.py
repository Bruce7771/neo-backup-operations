"""Inactive bounded controller core around EXISTING planner/native callbacks.

No B2/SSH/client/service creation; production coordinator hard guard unchanged.
Full metadata preplan is outside HOLD; caller uses same_job_fresh_tail for the
fresh callback. Native check/component callback runs after known clean release.
"""
import hashlib,json,secrets,time,re

def need(x,m):
 if not x:raise ValueError(m)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def exact_transition(before,after,approved):
 old={r['id']:r for r in before};new={r['id']:r for r in after};need(set(old)-set(new)==set(approved),'Native result removed unexpected snapshots');need(all(new[sid]==r for sid,r in old.items()if sid in new),'Immutable retained snapshot changed');need(not(set(new)-set(old)),'New publisher bypassed HOLD')
def execute(preplan_candidate,expected_review_digest,review_digest,producer_policy_sha256,rpc,fresh_candidate,native_forget,native_inventory,postcheck,*,now=time.monotonic):
 if not preplan_candidate['remove_snapshot_ids']:return {'result':'zero-candidate-noop','hold_acquired':False,'deleted_snapshots':0,'prune':False}
 need(review_digest(preplan_candidate)==expected_review_digest,'Exact reviewed preplan differs')
 nonce=secrets.token_hex(32);start=now();deadline=start+116 # Four seconds for bounded child termination/reap within the 120s HOLD.
 held=False;begin_attempted=False;native_started=False;acknowledged=False;released=False;phase='acquire'
 def rpc_call(method,*args,reserve=0,**kwargs):
  left=deadline-now()-reserve;need(left>0,'Publication RPC deadline exhausted')
  return getattr(rpc,method)(*args,rpc_timeout=min(15,left),deadline=deadline,**kwargs)
 try:
  rpc_call('acquire',nonce,producer_policy_sha256,120);held=True
  phase='fresh-tail';candidate,inventory=fresh_candidate(start+45);need(now()<=start+45,'Fresh tail exceeded 45-second publication budget');need(now()<deadline,'Publication critical deadline exhausted')
  if not candidate['remove_snapshot_ids']:
   rpc_call('release',nonce,reserve=1);released=True;return {'result':'fresh-zero-noop','hold_acquired':True,'deleted_snapshots':0,'prune':False}
  need(candidate.get('inventory_stable_for_admission')is True,'Fresh under-HOLD inventory required');need(review_digest(candidate)==expected_review_digest,'Fresh removals/config require a new exact review')
  ids=candidate['remove_snapshot_ids'];need(isinstance(ids,list)and 0<len(ids)<=10 and len(ids)==len(set(ids))and all(isinstance(x,str)and re.fullmatch('[0-9a-f]{64}',x)for x in ids),'Bounded exact snapshot removals required');need(candidate.get('apply_ready')is False and not set(ids)&set(candidate.get('protected_snapshot_ids',[]))and not set(ids)&set(candidate.get('retained_snapshot_ids',[])),'Planner protection boundary violated')
  # Reserve begin RPC15 + inventory10 + acknowledge15 + release15 + margin1.
  advertised=min(60,int(deadline-now()-56));need(advertised>=1,'No native operation budget remains')
  phase='begin-native';begin_attempted=True
  rpc_call('begin_forget',nonce,hashlib.sha256(canonical(candidate)).hexdigest(),advertised,reserve=41)
  # The begin round trip has actually elapsed. Never spend its reserved time twice.
  timeout=min(advertised,int(deadline-now()-41));need(timeout>=1,'No native operation budget remains after begin RPC')
  native_started=True;phase='native-forget';native_forget(ids,timeout)
  phase='native-transition';inventory_timeout=min(10,int(deadline-now()-31));need(inventory_timeout>=1,'No transition inventory budget remains')
  after=native_inventory(inventory_timeout);need(now()<=deadline-31,'Native result exceeded critical deadline');exact_transition(inventory,after,ids)
  rpc_call('acknowledge',nonce,native_exit_zero=True,exact_transition_verified=True,reserve=16);acknowledged=True
  rpc_call('release',nonce,reserve=1);released=True
  phase='postcheck-after-release';checks=postcheck(candidate);return {'result':'exact-forget-only','deleted_snapshots':len(ids),'prune':False,'HOLD_released_before_postcheck':True,**checks}
 except BaseException:
  if held and not released:
   if begin_attempted and not acknowledged:
    try:rpc_call('acknowledge',nonce,native_exit_zero=False,exact_transition_verified=False,reserve=1)
    except BaseException:pass # Unknown remote outcome remains HOLD, never autofix.
   elif not begin_attempted:
    try:rpc_call('release',nonce,reserve=1)
    except BaseException:pass
  raise
