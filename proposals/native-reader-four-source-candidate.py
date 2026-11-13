#!/usr/bin/env python3
"""REVIEW ONLY: make five byte-pinned candidates in memory; no live install.

Four data-reader changes (8 flags) plus the mandatory v3 delegate PIN update.
Original byte strings form the rollback set. Runtime/source path writes forbidden.
"""
import ast,hashlib
PIN='03099ff16f6e6cf4c11efb29796863ac37ddff123463a09aa53176c520bca203'
BASELINES={
 'neo-hourly-v3-run.py':(PIN,2),
 'neo-daily-backup.sh':('c20802ff9bdcf915abb882b3b13a87dd3862b71023b15d44b1d006099175a9a8',1),
 'neo-main-preview-b2-accept.sh':('43d02440de45c3872ec3071f7b5d6a410caed0df33aa877ee8dde142b4a55167',4),
 'neo-main-preview-restore-check.sh':('a04d88e3528521fd501734a717949e7e5abffda73a9d80f0d077f39574f101bb',1),
 'neo-hourly-online-run.py':('3d78c95a9535dba5b4c0eaca7b37d9a2116954b858f90512e2765851e0c83d18',0),
}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def prepare(sources):
 if set(sources)!=set(BASELINES):raise ValueError('Exact reviewed five-source set required')
 originals=dict(sources);candidates={}
 for name,(expected,count)in BASELINES.items():
  raw=sources[name]
  if type(raw)is not bytes or digest(raw)!=expected:raise ValueError('Installed source hash changed')
  if b'\r'in raw:raise ValueError('Expected installed LF bytes required')
  if name=='neo-hourly-online-run.py':continue
  if raw.count(b'--no-lock')!=count:raise ValueError('Reader site count changed')
  lines=raw.splitlines()
  for line in lines:
   if b'--no-lock'in line and not(b'dump'in line or b'stats'in line):raise ValueError('Unreviewed no-lock operation')
  updated=raw.replace(b",'--no-lock'",b'')if name.endswith('.py')else raw.replace(b' --no-lock',b'')
  if b'--no-lock'in updated:raise ValueError('Incomplete reader enrollment')
  candidates[name]=updated
 runner_sha=digest(candidates['neo-hourly-v3-run.py'])
 delegate=sources['neo-hourly-online-run.py']
 if delegate.count(PIN.encode())!=1:raise ValueError('Delegate pin ambiguity')
 candidates['neo-hourly-online-run.py']=delegate.replace(PIN.encode(),runner_sha.encode())
 for name in('neo-hourly-v3-run.py','neo-hourly-online-run.py'):ast.parse(candidates[name])
 return {'candidates':candidates,'rollback':originals,'proof':{
  'scope':'proposed-native-reader-eight-flag-and-delegate-pin-change','data_reader_flags_removed':8,
  'old_runner_sha256':PIN,'new_runner_sha256':runner_sha,
  'sources':[{'file':name,'before_sha256':digest(sources[name]),'after_sha256':digest(candidates[name])}for name in sorted(candidates)],
  'runtime_installed':False,'nonzero_guard_removed':False,'timers_changed':False}}
