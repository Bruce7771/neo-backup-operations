#!/usr/bin/env python3
"""Pure policy validation and limited actual SQLite-component restoration."""
import hashlib
from pathlib import Path
import re
import sqlite3

HEX=re.compile(r'^[0-9a-f]{64}$')


def require(ok):
    if not ok:raise ValueError('Retained component postcheck boundary failed')


def validate(candidate,policy):
    c=policy.get('maintenance_postcheck',{});sid=c.get('snapshot');path=c.get('path','')
    require(isinstance(sid,str)and HEX.fullmatch(sid)is not None and sid in candidate['retained_snapshot_ids']
            and sid in candidate['protected_snapshot_ids'])
    require(c.get('kind')=='sqlite'and isinstance(path,str)and path.startswith('/')
            and'..'not in Path(path).parts and not any(k in path for k in'*?[]'))
    require(isinstance(c.get('sha256'),str)and HEX.fullmatch(c['sha256'])is not None
            and type(c.get('bytes'))is int and 0<c['bytes']<=16*1024*1024)
    roots=[root.rstrip('/')for scope in policy['scopes']for root in scope['paths']]
    require(any(path.startswith(root+'/')for root in roots))
    # Never choose the known shadow artifact merely to make a restore tiny.
    require(not path.endswith('/files/object-snapshot/index.sqlite3'))
    return c


def restore(candidate,policy,work,call):
    c=validate(candidate,policy);target=Path(work)/'component-restore';target.mkdir(mode=0o700)
    call(['--no-cache','--no-lock','restore','--verify','--include',c['path'],'--target',str(target),c['snapshot']])
    file=target/c['path'].lstrip('/')
    require(file.is_file()and not file.is_symlink()and file.stat().st_size==c['bytes'])
    with file.open('rb')as handle:require(hashlib.file_digest(handle,'sha256').hexdigest()==c['sha256'])
    with sqlite3.connect(file.as_uri()+'?mode=ro&immutable=1',uri=True)as db:
        require(db.execute('PRAGMA quick_check').fetchall()==[('ok',)])
    return {'component_restore_verified':True,'component_sha_verified':True,
            'sqlite_integrity_verified':True,'component_bytes_verified':c['bytes'],
            'full_database_or_site_restore_claimed':False}
