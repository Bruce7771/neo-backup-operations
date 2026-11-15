"""Two exact restored Main control artifacts; no generic path or parent bypass."""
import hashlib,json
ARTIFACTS={
 '11aed282ce0ae26c699d4b39be50c36ab5ee3bf2e583c1e9945db41190c88af9':{
  'inventory_sha256':'0eaa30e60513081e4826f64cbda0e199377036d23be36d8846b09cfc5dfbc662',
  'artifact_scope':'main-current-protected-controls-and-executable-source',
  'targeted_restore_proof_sha256':'a7642c3429f8344e62a1c6ca19a3ac585179cd7097b9422c70fbc1dc6bcf88c5'},
 'da47e6c570052024a1f71783d8333356d56ecd8c6f640a3a31cedb4e93c9e0f0':{
  'inventory_sha256':'d373a8c1854ce9917157b2860c63982cc4bf138c047411c408ac1b772ecfa7f7',
  'artifact_scope':'main-social-final-hold-manifest-and-capture-receipt',
  'targeted_restore_proof_sha256':'f4cd3abe0ed184c51cc31ca9e0039b4a60ec6d4ce6a231ea4ffcc08ca743471f'}
}
def reviewed_controls(inventory,protected,configuration_scopes):
 approved={}
 for row in inventory:
  sid=row['id']
  if sid not in ARTIFACTS:continue
  evidence=ARTIFACTS[sid]
  if (row.get('hostname'),'neo-builder-preview-config')not in configuration_scopes or 'neo-builder-preview-config'not in row.get('tags',[]):raise ValueError('Control artifact outside exact reviewed host/tag scope')
  projection={k:row[k]for k in('id','hostname','tags','paths','time')}
  digest=hashlib.sha256(json.dumps(projection,sort_keys=True,separators=(',',':')).encode()).hexdigest()
  if digest!=evidence['inventory_sha256']:raise ValueError('Control artifact exact native inventory projection changed')
  if sid not in protected:raise ValueError('Control artifact requires explicit owner protected hold')
  approved[sid]=dict(evidence,scope_of_restore='targeted-artifact-only',generic_Neo_restore_claimed=False,external_parent_claimed=False)
 return approved
