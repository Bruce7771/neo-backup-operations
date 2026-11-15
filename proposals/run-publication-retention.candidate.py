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
