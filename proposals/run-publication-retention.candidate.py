#!/usr/bin/env python3
"""SOURCE ONLY launcher for a separate protected maintenance job; default PLAN."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def build_engine(here, destination):
    builder = load('publication_candidate_family_builder', here / 'build-same-job-tail-retention-engine.proposed.py')
    engine = builder.build(here.parent / 'scripts', destination)
    # Preserve the auditor's ONE nonmutating no-lock dry-run planning call.
    # Native dry-run forget otherwise requires EX and conflicts with ordinary SH readers.
    # Actual forget remains default EX under the reviewed publication HOLD.
    audit = engine / 'retention-audit.py'
    source = audit.read_text(encoding='utf-8')
    old = "['restic','--no-lock','forget','--dry-run'"
    if source.count(old) != 1:
        raise ValueError('Exact staged native dry-run anchor changed')
    inventory = "run(['restic','snapshots','--json'],env)"
    if source.count(inventory) != 2:
        raise ValueError('Exact initial/final inventory read anchors changed')
    source = source.replace(inventory, "run(['restic','--no-lock','snapshots','--json'],env,90)")
    compile(source, str(audit), 'exec')
    audit.write_text(source, encoding='utf-8')
    # Maintenance preplan only: longer cold reads, unchanged total admission budget.
    transforms = {
        'native_parallel_transport.py': [('spawned+35', 'spawned+90', 2),
            ("TimeoutExpired('reviewed-native-reader',35)", "TimeoutExpired('reviewed-native-reader',90)", 1)],
        'staged_derive.py': [('self.segment_end-self.now()<35', 'self.segment_end-self.now()<90', 1),
            ('self.now()+120', 'self.now()+300', 1),
            ("self.segments<=43,'Long metadata segments exhausted'", "self.segments<=30,'Long metadata segments exhausted'", 1)],
        'retention-audit.py': [('segment_deadline_seconds=120', 'segment_deadline_seconds=300', 1)]}
    for relative, changes in transforms.items():
        path = engine / relative; body = path.read_text(encoding='utf-8')
        for old, new, count in changes:
            if body.count(old) != count: raise ValueError('Exact maintenance preplan timing anchor changed')
            body = body.replace(old, new)
        compile(body, str(path), 'exec'); path.write_text(body, encoding='utf-8')
    # SOURCE-ONLY candidate: a point may cross I/O segments, never the same-job
    # metadata deadline. The fresh-tail transport has no callback or no-lock flag.
    path = engine / 'staged_derive.py'; body = path.read_text(encoding='utf-8')
    old = """ def begin_child(self):
  self.metadata()
  if self.segment_end is None or self.segment_end-self.now()<90:
   self.segments+=1;need(self.segments<=30,'Long metadata segments exhausted')
   self.segment_end=min(self.now()+300,self.metadata_end)
  self.check();return self.segment_end
 def check(self):
  self.metadata()
  if self.segment_end is not None and self.now()>=self.segment_end:raise TimeoutError('Metadata segment exhausted')"""
    new = """ def reserve_native_read(self):
  with self._native_reservation_lock:
   self.metadata();now=self.now()
   if self.metadata_end-now<90:raise TimeoutError('Global metadata budget cannot reserve native read')
   if self.segment_end is None or self.segment_end-now<90:
    need(self.segments<30,'Long metadata segments exhausted');self.segments+=1
    self.segment_end=min(now+300,self.metadata_end)
   return self.segment_end
 def begin_child(self):return self.reserve_native_read()
 def check(self):self.metadata()"""
    if body.count(old) != 1: raise ValueError('Exact per-child preplan budget anchor changed')
    body = body.replace(old, new)
    anchor = 'self.segment_end=None;self.segments=0'
    if body.count(anchor) != 1: raise ValueError('Exact preplan lock anchor changed')
    body = body.replace(anchor, anchor + ';self._native_reservation_lock=threading.RLock()')
    anchor = ' def deadline(value):batch.deadline=value;batch.reader.deadline=value;catalog.deadline=value'
    if body.count(anchor) != 1: raise ValueError('Exact preplan enclosing deadline anchor changed')
    body = body.replace(anchor, """ old_reserver=getattr(batch.reader,'deadline_reserver',None);old_nolock=getattr(batch.reader,'preplan_read_only_nolock',False);old_restore=batch.restore
 batch.reader.deadline_reserver=budget.reserve_native_read;batch.reader.preplan_read_only_nolock=True
 def reserved_restore(args,env,ignored):return old_restore(args,env,budget.reserve_native_read())
 batch.restore=reserved_restore
 def deadline(value):batch.deadline=budget.metadata_end;batch.reader.deadline=budget.metadata_end;catalog.deadline=budget.metadata_end""")
    anchor = '  catalog.authenticated_file_origin=old_origin'
    if body.count(anchor) != 1: raise ValueError('Exact preplan cleanup anchor changed')
    body = body.replace(anchor, anchor + "\n  batch.reader.deadline_reserver=old_reserver;batch.reader.preplan_read_only_nolock=old_nolock;batch.restore=old_restore")
    compile(body, str(path), 'exec'); path.write_text(body, encoding='utf-8')
    path = engine / 'retention-audit.py'; body = path.read_text(encoding='utf-8')
    anchor = 'from staged_derive import Budget,staged_derive'
    if body.count(anchor) != 1: raise ValueError('Exact preplan metadata command import changed')
    body = body.replace(anchor, anchor + '\nfrom native_parallel_transport import readonly_metadata_command')
    anchor = '            nonlocal cold_pitr_manifest_used'
    if body.count(anchor) != 1: raise ValueError('Exact preplan dump reservation anchor changed')
    body = body.replace(anchor, anchor + '\n            BUDGET.reserve_native_read()')
    anchor = "external_command(['restic','dump',snapshot,path],env)"
    if body.count(anchor) != 1: raise ValueError('Exact preplan metadata dump command changed')
    body = body.replace(anchor, "external_command(readonly_metadata_command(['dump',snapshot,path]),env)")
    compile(body, str(path), 'exec'); path.write_text(body, encoding='utf-8')
    return engine


def main():
    os.umask(0o077)
    here = Path(__file__).resolve().parent
    coordinator = load('publication_candidate_coordinator', here / 'publication-retention-coordinator.candidate.py')
    with tempfile.TemporaryDirectory(prefix='neo-publication-engine-', dir=os.environ['RUNNER_TEMP']) as tmp:
        folder = Path(tmp); folder.chmod(0o700)
        engine = build_engine(here, folder / 'engine')
        # Same parent process owns preplan bundle, cache and restricted-RPC admission.
        result = coordinator.main(engine, sys.argv[1:])
        print(json.dumps({'scope': 'publication-forget-only-candidate', **result}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        reason = getattr(error, 'reason', 'downstream-failure-inspect-private-phase')
        print('::error::Publication maintenance stopped safely (' + type(error).__name__ + ': ' + reason + '); no automatic retry or unlock', file=sys.stderr)
        raise SystemExit(1)
