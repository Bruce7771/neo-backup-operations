#!/usr/bin/env python3
"""PROPOSAL ONLY: coherent8source reader+recovery-scope candidate, memory only."""
import ast,hashlib,importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('five',Path(__file__).with_name('native-reader-four-source-candidate.py'));five=importlib.util.module_from_spec(spec);spec.loader.exec_module(five)
EXTRA={'neo-hourly-v3-config-collect.py':'947b48f75984171df88d26ad18544b91d437d832f6664d432c682d08cff56cbc','neo-builder-preview-config-collect.py':'947b48f75984171df88d26ad18544b91d437d832f6664d432c682d08cff56cbc','neo-hourly-v3-config-coverage.py':'dc36f83664c11599d113b13da295f610dd0a7140fe8bed42a473aa9b2a92a479'}
BEFORE={n:h for n,(h,_)in five.BASELINES.items()};BEFORE.update(EXTRA)
def prepare(sources):
 if set(sources)!=set(BEFORE):raise ValueError('Exact8source set required')
 for n,h in BEFORE.items():
  if five.digest(sources[n])!=h or b'\r'in sources[n]:raise ValueError('Actual installedLF source mismatch')
 result=five.prepare({n:sources[n]for n in five.BASELINES});candidates=dict(result['candidates'])
 paths=sorted({'/usr/local/libexec/'+n for n in BEFORE}|{'/etc/neo/backup/native-reader-enrollment.json'}|{'/etc/neo/backup/rollback/native-reader-before-'+n+'.'+h+'.txt'for n,h in BEFORE.items()})
 include=('\n# Native reader contract: all changed controls, original rollback bytes and receipt.\nsources += [Path(name) for name in '+repr(paths)+']\n').encode()
 for n in('neo-hourly-v3-config-collect.py','neo-builder-preview-config-collect.py'):
  raw=sources[n];needle=b'sources = sorted(set(sources))'
  if raw.count(needle)!=1:raise ValueError('Collector insertion boundary changed')
  candidates[n]=raw.replace(needle,include+needle)
 raw=sources['neo-hourly-v3-config-coverage.py'];needle=b'\ndef verify(metadata):'
 if raw.count(needle)!=1:raise ValueError('Coverage boundary changed')
 candidates['neo-hourly-v3-config-coverage.py']=raw.replace(needle,('\n# Required complete native reader enrollment and rollback set.\nREQUIRED.update('+repr(paths)+')\n').encode()+needle)
 for n,data in candidates.items():
  if n.endswith('.py'):ast.parse(data)
 return {'candidates':candidates,'rollback':dict(sources),'proof':{'scope':'proposed-eight-source-native-reader-contract','source_count':8,'reader_flags_removed':8,'rollback_sources':8,'required_enrollment_paths':len(paths),'new_runner_sha256':five.digest(candidates['neo-hourly-v3-run.py']),'source_code_bytes':sum(map(len,candidates.values())),'additional_rollback_bytes':sum(map(len,sources.values())),'sources':[{'file':n,'before_sha256':BEFORE[n],'after_sha256':five.digest(candidates[n])}for n in sorted(candidates)],'runtime_installed':False,'nonzero_guard_removed':False}}
