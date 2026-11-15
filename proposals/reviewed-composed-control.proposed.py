"""Exact accepted e8 current-controls dependency on eb03 COMPOSED daily only."""
import hashlib,json
CHILD='e8cef9682159b2670d8e6d11d2976d79068a8cddf9445d248d6195fb221a3057'
PARENT='eb03a8a2b88bc3db09a22ff0bdc6fa4e089503ea0d170a14c99d849275565ad3'
CHILD_INVENTORY_SHA256='30c016e267745317b814560ef8f9830d2726b99c18583bcf44b8d6de72f43ce6'
EVIDENCE={
 'child_scope':'main-neo-and-saved-builder-current-operations-v1',
 'parent_scope':'main-neo-daily-composed-v1',
 'relation':'current-operations-controls-for-composed-daily',
 'child_actual_restore_proof_sha256':'1678a25b20f5836ea8cfa0ac9b16a811d550cb54a2baaca68714ac6e18049a12',
 'child_recovery_descriptor_sha256':'e77a4dde38df917a9756cf02cd766831bd593a97cfe9f100cfea9491e7301f36',
 'parent_actual_restore_proof_sha256':'5e60eb3caff6c8e4c42b2e9f5bbcd2381fc457d22b56f4f12cc72008eb9bf046',
 'parent_native_acceptance_receipt_sha256':'2fa1c4a0cd6d8ff96992977720ba76e19aa9b7dfbe50002c033b5eae91323d34',
 'legacy_FULL_classification':False,
 'generic_restored_array_modified':False}
def require(x,message):
 if not x:raise ValueError(message)
NEW_CHILD='1c45bcb0e25148006902c2f1ef1ae3721119b9f78f278bcf747eb8d2a7a403b3'
NEW_CHILD_INVENTORY_SHA256='f9100f0d5c7bd2721a6637b89ed0efc4861ec860dc029d72060ca2d156bcf931'
NEW_EVIDENCE=dict(EVIDENCE,
 child_actual_restore_proof_sha256='8e5ad5ff0345a369f248208911106c4fae58bb7acf4fe8f587d3d3244ae5879d',
 child_recovery_descriptor_sha256='8b45188aea9ecf9fcf5f2bf2c54fa40902caa8f8f3381f3ced865c24fd70b90f',
 owner_compatible_data_snapshot='c559b4041887004930a071de4c1818a624223e97526d338f11eb3d9179a5f351',
 owner_data_composition_is_separate_from_embedded_dependency=True,
 child_files_verified=280,child_bytes_verified=14090834,
 child_release_sha='12907094721fe52654ed1ca1bcbe196f94c13842',
 maintenance_writer_policy_sha256='1baabdd58d55459f8e715d44bab86829f3b499b07d2e1b30e6145acacf211161')
REVIEWED={CHILD:(CHILD_INVENTORY_SHA256,EVIDENCE),NEW_CHILD:(NEW_CHILD_INVENTORY_SHA256,NEW_EVIDENCE)}

def reviewed_composed_control(inventory,protected,configuration_scopes):
 rows={r['id']:r for r in inventory};result={}
 for child_id,(projection_sha,evidence) in REVIEWED.items():
  if child_id not in rows:continue
  child=rows[child_id]
  require((child.get('hostname'),'neo-builder-preview-config')in configuration_scopes,'Composed controls outside reviewed configuration scope')
  projection={k:child[k]for k in('id','hostname','tags','paths','time')}
  require(hashlib.sha256(json.dumps(projection,sort_keys=True,separators=(',',':')).encode()).hexdigest()==projection_sha,'Composed controls native inventory projection differs')
  require(child_id in protected and PARENT in protected,'Both composed-control dependency endpoints need protected holds')
  require(PARENT in rows,'Accepted composed daily parent absent')
  parent=rows[PARENT]
  require(parent.get('hostname')=='srv2140404-main-daily-composed'and set(parent.get('tags',[]))=={'neo-daily','neo-daily-composed-v1'}and set(parent.get('paths',[]))=={'/var/lib/neo-main-daily-online/capture','/srv/neo-recovery/object-storage/objects'},'Accepted parent must retain exact composed daily host/tag/paths')
  result[child_id]=dict(evidence,parent_snapshot=PARENT,child_snapshot=child_id)
 return result
