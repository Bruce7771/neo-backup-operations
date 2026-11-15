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
def reviewed_composed_control(inventory,protected,configuration_scopes):
 rows={r['id']:r for r in inventory}
 if CHILD not in rows:return {}
 child=rows[CHILD]
 require((child.get('hostname'),'neo-builder-preview-config')in configuration_scopes,'Composed controls outside reviewed configuration scope')
 projection={k:child[k]for k in('id','hostname','tags','paths','time')}
 require(hashlib.sha256(json.dumps(projection,sort_keys=True,separators=(',',':')).encode()).hexdigest()==CHILD_INVENTORY_SHA256,'Composed controls native inventory projection differs')
 require(CHILD in protected and PARENT in protected,'Both composed-control dependency endpoints need protected holds')
 require(PARENT in rows,'Accepted composed daily parent absent')
 parent=rows[PARENT]
 require(parent.get('hostname')=='srv2140404-main-daily-composed'and set(parent.get('tags',[]))=={'neo-daily','neo-daily-composed-v1'}and set(parent.get('paths',[]))=={'/var/lib/neo-main-daily-online/capture','/srv/neo-recovery/object-storage/objects'},'Accepted parent must retain exact composed daily host/tag/paths')
 return {CHILD:dict(EVIDENCE,parent_snapshot=PARENT,child_snapshot=CHILD)}
