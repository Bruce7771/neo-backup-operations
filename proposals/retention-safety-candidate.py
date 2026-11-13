#!/usr/bin/env python3
"""CODE-ONLY candidate builder. Does not install, run restic or alter source files."""
from pathlib import Path
import copy, re


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Candidate requires exact reviewed source anchor')
    return source.replace(old, new, 1)


def move_explicit_holds_before_derive(plans, protected):
    if (not isinstance(protected, list) or len(set(protected)) != len(protected)
        or any(not isinstance(x, str) or re.fullmatch('[0-9a-f]{64}', x) is None for x in protected)):
        raise ValueError('Invalid explicit protected inventory')
    held=set(protected); result=copy.deepcopy(plans); seen=set()
    for plan in result:
        for group in plan:
            for kind in ('keep','remove'):
                for row in group.get(kind) or []:
                    sid=row.get('id')
                    if not isinstance(sid,str) or re.fullmatch('[0-9a-f]{64}',sid) is None or sid in seen:
                        raise ValueError('Malformed or duplicate native plan point')
                    seen.add(sid)
            moved=[r for r in group.get('remove') or [] if r['id'] in held]
            group['remove']=[r for r in group.get('remove') or [] if r['id'] not in held]
            group['keep']=list(group.get('keep') or [])+moved
    return result


def scoped_rule_suffix(scope):
    if scope.get('kind') == 'daily':
        return ['--keep-daily','30','--keep-monthly','3']
    if scope.get('kind') in ('hourly','pitr'):
        # NO approved hourly/PITR expiry horizon exists. Preserve current rules.
        return ['--keep-within','30d','--keep-daily','30','--keep-monthly','3']
    raise ValueError('Unreviewed retention scope kind')


def audit_candidate(source):
    source=once(source,'from hourly_metadata_batch import HourlyMetadataBatch',
        'from hourly_metadata_batch import HourlyMetadataBatch\nfrom retention_safety_candidate import move_explicit_holds_before_derive, scoped_rule_suffix')
    source=once(source,"'--tag',scope['tag'],'--group-by','host','--keep-within','30d',\n                      '--keep-daily','30','--keep-monthly','3'],env)",
        "'--tag',scope['tag'],'--group-by','host'] + scoped_rule_suffix(scope),env)")
    source=once(source,"edge_inventory,parents,updated=derive(json.loads(inventory),\n            [json.loads(p.read_text()) for p in plan_paths],policy,",
        "explicit=json.loads((work/'protected.json').read_text())\n        held_plans=move_explicit_holds_before_derive([json.loads(p.read_text()) for p in plan_paths],explicit)\n        edge_inventory,parents,updated=derive(json.loads(inventory),\n            held_plans,policy,")
    return source


def batch_candidate(source):
    source=once(source,'from pathlib import Path','from pathlib import Path\nfrom types import MappingProxyType')
    source=once(source,'self._seen_v3=set()',
        "self._seen_v3=set()\n        self._memo_key=None; self._memo_payload=None\n        self.stats['memory_payload_hits']=0")
    source=once(source,'    def _fetch(self,snapshot):', '''    def _fetch(self,snapshot):
        # Instance is bound to exact repository/scope; snapshot completes identity.
        # Bytes are immutable; mapping is read-only; only one <=19MiB point lives.
        key=(self.binding,self.root,snapshot)
        if key==self._memo_key:
            self.stats['memory_payload_hits']+=1
            return self._memo_payload
        payload=self._fetch_uncached(snapshot)
        require(sum(len(raw)for raw in payload.values())<=sum(LIMITS.values()),'Oversize in-memory point')
        self._memo_payload=MappingProxyType(dict(payload)); self._memo_key=key
        return self._memo_payload

    def _fetch_uncached(self,snapshot):''')
    return source


def write_candidate(original, destination):
    """Only an explicit new disposable output directory; source never overwritten."""
    destination=Path(destination)
    destination.mkdir(mode=0o700,exist_ok=False)
    (destination/'retention_safety_candidate.py').write_text(Path(__file__).read_text())
    (destination/'retention-audit.py').write_text(audit_candidate((Path(original)/'retention-audit.py').read_text()))
    (destination/'hourly_metadata_batch.py').write_text(batch_candidate((Path(original)/'hourly_metadata_batch.py').read_text()))

def v3_catalog_candidate(source):
    """Optional explicit native branch; original archived-manifest path unchanged.

    This is not enabled by tags/schema alone. The trusted caller must attach the
    reviewed catalog validator to its exact snapshot-bound native dump callable.
    """
    start="    outer_raw=dump(sid,root+'/manifest.json',8*1024*1024);outer=json.loads(outer_raw)"
    end="    rows={row['path']:row for row in files}"
    first=source.index(start);last=source.index(end,first)
    old=source[first:last]
    replacement='''    files=sealed.get('files',[]);require(files and len({row['path']for row in files})==len(files),'V3 empty/duplicate PG files')
    catalog=getattr(dump,'native_pg_catalog',None)
    if catalog is not None:
        # Distinct proof scheme, not an invented archived outer manifest.
        proof=catalog(sid,root,files,sealed_raw)
        require(isinstance(proof,dict) and proof.get('validation')=='native-PG-catalog-content-identity-v1'
                and proof.get('snapshot')==sid and proof.get('file_rows')==len(files)
                and re.fullmatch('[0-9a-f]{64}',proof.get('catalog_proof_sha256',''))is not None
                and proof.get('physical_restore_claimed')is False,'Invalid native catalog evidence')
        outer_raw=b'native-PG-catalog-content-identity-v1\\0'+json.dumps(proof,sort_keys=True,separators=(',',':')).encode()
        metadata_validation='native-PG-catalog-content-identity-v1'
    else:
'''+''.join('    '+line+'\n' for line in old.splitlines())+'''        metadata_validation='archived-outer-manifest-v3'
'''
    source=source[:first]+replacement+source[last:]
    source=once(source,'base_manifest_sha256=base_sha)',
        'base_manifest_sha256=base_sha,metadata_validation=metadata_validation)')
    return source
