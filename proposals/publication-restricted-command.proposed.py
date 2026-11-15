"""Inactive restricted SSH dispatch core. No shell, credentials or B2 client.

Existing read-only identity retains writer-status ONLY. Scoped publication
commands require the existing maintenance identity's separate forced wrapper.
"""
import re,time
HEX=re.compile('[0-9a-f]{64}')
def require(x,m):
 if not x:raise ValueError(m)
def fields(body,allowed):require(isinstance(body,dict)and set(body)==set(allowed),'Unexpected bounded command fields')
def dispatch(command,body,gate,status_reader,actual_policy_sha256,*,maintenance_identity=False):
 if command=='writer-status':
  fields(body,());return status_reader() # No gate transition, process or write.
 require(maintenance_identity is True,'Read-only identity cannot alter coordination state')
 if command=='publication-acquire':
  fields(body,('owner_nonce','producer_policy_sha256','maximum_seconds'));s=status_reader()
  require(s.get('local_inventory_complete')is True and s.get('source_review_integrity')is True
          and s.get('publication_producers_enrolled')is True and not s.get('unknown_writer_units')
          and s.get('unknown_repository_clients')==0,'Complete enrolled writer policy required')
  require(not s.get('active_known_writer_units') and s.get('active_known_repository_clients')==0,
          'Existing producer must finish naturally before publication admission')
  require(HEX.fullmatch(actual_policy_sha256)and body['producer_policy_sha256']==actual_policy_sha256==s.get('writer_policy_sha256'),'Actual installed source-policy mismatch')
  result=gate.acquire(body['owner_nonce'],actual_policy_sha256,body['maximum_seconds']);return {'acquired':True,**result,'application_writers_blocked':False}
 if command=='publication-begin-forget':
  fields(body,('owner_nonce','candidate_sha256','native_timeout_seconds'));gate.begin_forget(body['owner_nonce'],body['candidate_sha256'],body['native_timeout_seconds']);return {'begin_recorded':True,'actual_B2_call_performed':False}
 if command=='publication-acknowledge':
  fields(body,('owner_nonce','native_exit_zero','exact_transition_verified'));require(type(body['native_exit_zero'])is bool and type(body['exact_transition_verified'])is bool,'Boolean outcome required');gate.acknowledge(body['owner_nonce'],native_exit_zero=body['native_exit_zero'],exact_transition_verified=body['exact_transition_verified']);return {'outcome_recorded':True}
 if command=='publication-release':
  fields(body,('owner_nonce',));gate.release(body['owner_nonce']);return {'released':True}
 raise ValueError('Unsupported literal maintenance command')
