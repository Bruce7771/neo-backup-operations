#!/usr/bin/python3
"""Bounded streaming Docker-save verification; no extraction, daemon or network."""
import argparse,gzip,hashlib,io,json,pathlib,re,tarfile
MAX_ARCHIVE=2_000_000_000;MAX_DECODED=2_000_000_000;META=4_000_000;TOTAL_META=32_000_000
def need(value,message):
 if not value:raise ValueError(message)
def digest(value):need(isinstance(value,str)and re.fullmatch(r'sha256:[0-9a-f]{64}',value),'Invalid SHA256 identity');return value[7:]
def safe_path(value):
 need(isinstance(value,str)and value and '\\'not in value,'Invalid member path');p=pathlib.PurePosixPath(value)
 need(not p.is_absolute()and '..'not in p.parts,'Unsafe member path');s=str(p);need(s not in ('','.'),'Empty member path');return s

class CountingReader(io.RawIOBase):
 def __init__(self,stream,maximum):self.stream=stream;self.maximum=maximum;self.count=0;self.hash=hashlib.sha256()
 def readable(self):return True
 def readinto(self,buffer):
  data=self.stream.read(min(len(buffer),1024*1024));n=len(data)
  self.count+=n;need(self.count<=self.maximum,'Archive byte ceiling');self.hash.update(data);buffer[:n]=data;return n

class BoundedTarInfo(tarfile.TarInfo):
 def extension_guard(self,archive):
  archive._image_extension_count=getattr(archive,'_image_extension_count',0)+1
  archive._image_extension_bytes=getattr(archive,'_image_extension_bytes',0)+self.size
  need(0<=self.size<=65536 and archive._image_extension_count<=512 and archive._image_extension_bytes<=TOTAL_META,'Tar extension metadata bound')
 def _proc_pax(self,archive):self.extension_guard(archive);return super()._proc_pax(archive)
 def _proc_gnulong(self,archive):self.extension_guard(archive);return super()._proc_gnulong(archive)

def validate_stream(stream,image_id,ordered_diff_ids,expected_size=None,expected_sha=None,max_archive=MAX_ARCHIVE,max_decoded=MAX_DECODED,expected_platform=None):
 config_hash=digest(image_id);need(isinstance(ordered_diff_ids,list)and 0<len(ordered_diff_ids)<=64,'Layer list bound');expected=[digest(x)for x in ordered_diff_ids]
 need(0<max_archive<=MAX_ARCHIVE and 0<max_decoded<=MAX_DECODED,'Invalid byte bounds')
 raw=CountingReader(stream,max_archive);buffered=io.BufferedReader(raw,65536);records={};metadata={};decoded_total=0;metadata_total=0;members=0
 with tarfile.open(fileobj=buffered,mode='r|',tarinfo=BoundedTarInfo)as archive:
  for member in archive:
   members+=1;need(members<=512,'Member count bound')
   if member.isdir()and member.name in('.','./'):continue
   name=safe_path(member.name)
   need(member.isdir()or member.isfile(),'Unsupported link or special member')
   if member.isdir():continue
   need(name not in records and 0<=member.size<=max_archive,'Duplicate member or file bound')
   inner=CountingReader(archive.extractfile(member),member.size);body=io.BufferedReader(inner,65536);compressed=body.peek(2)[:2]==b'\x1f\x8b';data=gzip.GzipFile(fileobj=body)if compressed else body
   decoded=hashlib.sha256();count=0;small=bytearray()
   while True:
    chunk=data.read(1024*1024)
    if not chunk:break
    count+=len(chunk);decoded_total+=len(chunk);need(decoded_total<=max_decoded,'Decoded byte ceiling');decoded.update(chunk)
    if len(small)<=META:
     if len(small)+len(chunk)<=META:small.extend(chunk)
     else:small=bytearray(b' '*(META+1))
   need(inner.count==member.size,'Truncated member')
   records[name]={'bytes':member.size,'sha256':inner.hash.hexdigest(),'decoded_bytes':count,'diff_sha256':decoded.hexdigest(),'gzip':compressed}
   if len(small)<=META and small.lstrip()[:1]in(b'{',b'['):
    try:value=json.loads(small)
    except(ValueError,UnicodeDecodeError):value=None
    if value is not None:metadata_total+=len(small);need(metadata_total+getattr(archive,'_image_extension_bytes',0)<=TOTAL_META,'Metadata memory bound');metadata[name]=value
 # Consume the full raw stream, including native tar padding, for exact archive SHA/size.
 while buffered.read(1024*1024):pass
 need(expected_size is None or raw.count==expected_size,'Archive size mismatch');archive_sha=raw.hash.hexdigest();need(expected_sha is None or archive_sha==expected_sha,'Archive SHA mismatch')
 bindings=[];legacy=None;selected=None;attestations=[];graph_nodes=0;seen_manifests=set()
 def config(path):
  path=safe_path(path);need(path in metadata and path in records,'Missing image config');r=records[path];need(not r['gzip'],'Compressed image config unsupported');value=metadata[path]
  need(isinstance(value,dict)and value.get('rootfs',{}).get('type')=='layers'and value['rootfs'].get('diff_ids')==ordered_diff_ids,'RootFS order differs')
  if expected_platform is not None:need(all(value.get(k)==expected_platform[k]for k in('os','architecture')),'Config platform differs')
  return value
 def layers(paths):
  need(isinstance(paths,list)and len(paths)==len(expected),'Layer reference count/order')
  for path,wanted in zip(paths,expected):
   path=safe_path(path);need(path in records and records[path]['diff_sha256']==wanted,'Missing or corrupt layer')
 if 'manifest.json'in metadata:
  manifests=metadata['manifest.json'];need(isinstance(manifests,list)and len(manifests)==1,'Save must contain exactly one image');m=manifests[0];need(isinstance(m,dict),'Invalid Docker manifest');config(m['Config']);layers(m['Layers']);legacy={'config':safe_path(m['Config']),'layers':[safe_path(p)for p in m['Layers']]};bindings.append('docker-manifest')
 def descriptor(value):
  nonlocal graph_nodes
  graph_nodes+=1;need(graph_nodes<=128,'OCI graph node bound');need(isinstance(value,dict)and not value.get('urls'),'External/invalid descriptor');h=digest(value.get('digest'));p='blobs/sha256/'+h
  need(type(value.get('size'))is int and p in records and records[p]['sha256']==h and value['size']==records[p]['bytes'],'Descriptor content mismatch');return p
 def walk(index,chain,depth):
  nonlocal selected
  need(depth<=4 and isinstance(index,dict)and index.get('schemaVersion')==2 and isinstance(index.get('manifests'),list)and 0<len(index['manifests'])<=16,'OCI index shape/depth')
  for entry in index['manifests']:
   p=descriptor(entry);need(p in metadata and p not in seen_manifests,'Missing/cyclic/duplicate OCI manifest');seen_manifests.add(p);value=metadata[p];kind=entry.get('mediaType');nextchain=chain+[(entry['digest'],kind)]
   if kind in('application/vnd.oci.image.index.v1+json','application/vnd.docker.distribution.manifest.list.v2+json'):walk(value,nextchain,depth+1);continue
   need(kind in('application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.v2+json')and value.get('schemaVersion')==2,'Unsupported OCI image type/version')
   cfg=value.get('config');need(isinstance(cfg,dict),'Missing OCI config');cfgpath=descriptor(cfg);ann=entry.get('annotations')or{}
   if ann.get('vnd.docker.reference.type')=='attestation-manifest':
    need(entry.get('platform')=={'architecture':'unknown','os':'unknown'}and cfg.get('mediaType')=='application/vnd.oci.empty.v1+json'and metadata.get(cfgpath)=={}and not records[cfgpath]['gzip'],'Unsupported attestation config/platform')
    refs=value.get('layers');need(isinstance(refs,list)and 0<len(refs)<=8,'Attestation layer bound')
    for layer in refs:
     lp=descriptor(layer);need(layer.get('mediaType')=='application/vnd.in-toto+json'and lp in metadata and not records[lp]['gzip'],'Unsupported attestation layer')
    attestations.append({'reference':ann.get('vnd.docker.reference.digest'),'manifest':entry['digest']});continue
   need(not ann.get('vnd.docker.reference.type')and cfg.get('mediaType')in('application/vnd.oci.image.config.v1+json','application/vnd.docker.container.image.v1+json'),'Unsupported config/reference type')
   need(selected is None,'Multiple platform image ambiguity');config(cfgpath)
   if expected_platform is not None:need(all((entry.get('platform')or{}).get(k)==expected_platform[k]for k in('os','architecture')),'Descriptor platform differs')
   paths=[];refs=value.get('layers');need(isinstance(refs,list)and len(refs)==len(expected),'OCI layer count')
   for layer in refs:
    media=layer.get('mediaType');need(media in('application/vnd.oci.image.layer.v1.tar','application/vnd.oci.image.layer.v1.tar+gzip','application/vnd.docker.image.rootfs.diff.tar','application/vnd.docker.image.rootfs.diff.tar.gzip'),'Foreign or unsupported layer');lp=descriptor(layer);need(records[lp]['gzip']==media.endswith(('+gzip','.gzip')),'Layer compression differs');paths.append(lp)
   layers(paths);selected={'config':cfgpath,'layers':paths,'manifest':entry['digest'],'chain':nextchain}
 if 'index.json'in metadata:
  need(metadata.get('oci-layout',{}).get('imageLayoutVersion')=='1.0.0','Invalid OCI layout')
  walk(metadata['index.json'],[],0);need(selected is not None,'No platform image')
  need(all(a['reference']==selected['manifest']for a in attestations),'Attestation references another platform')
  if legacy is not None:need(legacy['config']==selected['config']and legacy['layers']==selected['layers'],'Docker/OCI platform bindings differ')
  bindings.append('oci-index')
 need(bindings,'Unsupported Docker-save layout')
 chosen=selected or legacy;actual_config=records[chosen['config']]['sha256'];kind='config'
 if actual_config!=config_hash:
  need(selected is not None,'Legacy config identity mismatch');matches=[media for h,media in selected['chain']if h==image_id];need(len(matches)==1,'Expected image root not authenticated');kind='oci-index'if matches[0]in('application/vnd.oci.image.index.v1+json','application/vnd.docker.distribution.manifest.list.v2+json')else'oci-manifest'
 return {'scope':'bounded-docker-save-stream-verification','image_id':image_id,'image_identity_kind':kind,'image_identity_authenticated':True,'config_sha256':actual_config,'archive_bytes':raw.count,'archive_sha256':archive_sha,'layer_count':len(expected),'all_ordered_rootfs_diff_ids_match':True,'config_digest_matches_image_id':actual_config==config_hash,'config_digest_authenticated_by_image_graph':True,'attestation_descriptors_verified':len(attestations),'attestation_signer_trust_claimed':False,'layouts_verified':bindings,'decoded_bytes':decoded_total,'metadata_bytes':metadata_total,'member_count':members,'graph_nodes_verified':graph_nodes,'extracted_files':0,'daemon_operations':0}

if __name__=='__main__':
 import sys
 p=argparse.ArgumentParser();p.add_argument('--expected',required=True);a=p.parse_args();e=json.load(open(a.expected));platform={k:e[k]for k in('os','architecture')}if'os'in e and'architecture'in e else None;print(json.dumps(validate_stream(sys.stdin.buffer,e['image_id'],e['ordered_diff_ids'],e['archive_bytes'],e['archive_sha256'],expected_platform=platform),sort_keys=True))
