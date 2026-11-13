#!/usr/bin/env python3
"""Proposed root-owned READ-ONLY writer inventory endpoint, not installed.

Reads reviewed code/unit/cron metadata and process identities, never environment
values, backup keys, databases or user files. No service/backup/fence changes.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time


def require(ok,reason):
    if not ok:raise ValueError(reason)


def next_epoch(value):
    match=re.fullmatch(r'@([0-9]+(?:\.[0-9]+)?)',value)
    if match:return float(match.group(1))
    if value.endswith(' UTC'):
        return datetime.datetime.strptime(value,'%a %Y-%m-%d %H:%M:%S UTC').replace(tzinfo=datetime.timezone.utc).timestamp()
    return None


def digest_file(path):
    path=Path(path)
    require(path.is_absolute()and not path.is_symlink(),'Nonregular review source')
    allowed=('/etc/systemd/','/usr/lib/systemd/','/usr/local/libexec/','/etc/cron','/var/spool/cron/')
    require(any(str(path).startswith(root)for root in allowed)
            and path.suffix!='.env'and 'password'not in path.name.lower(),'Review scope excludes credentials/data')
    before=path.stat();require(stat.S_ISREG(before.st_mode)and before.st_uid==0 and before.st_mode&0o022==0,'Untrusted review source ownership')
    with path.open('rb')as file:value=hashlib.file_digest(file,'sha256').hexdigest()
    after=path.stat();require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
        (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'Source changed during read')
    return value


def assemble(policy,files,cron,units,processes,now,policy_sha):
    """Pure admission evidence assembly; source observations are provided by OS reads."""
    require(policy.get('schema')==2 and policy.get('reviewed')is True,'Writer source policy not reviewed')
    require(policy.get('all_repository_writers_use_native_restic_locks')is True,
            'Unsupported/raw repository writers are not admitted')
    require(re.fullmatch('[0-9a-f]{64}',policy.get('repository_id',''))is not None,'Missing reviewed repository identity')
    expected=policy.get('reviewed_files',{});require(expected and files==expected,'Reviewed source/units changed')
    require(cron==policy.get('reviewed_cron_inventory'),'Cron inventory changed')
    declarations={row['unit']:row for row in policy.get('units',[])}
    require(declarations and len(declarations)==len(policy['units']),'Invalid unit roster')
    require(all(row.get('role')in('repository-writer','observer','timer')for row in declarations.values()),'Unknown unit role')
    for unit in units:
        if unit['unit']in declarations:
            actual=set(unit.get('source_paths',[]));reviewed=set(declarations[unit['unit']].get('source_paths',[]))
            require(actual and actual==reviewed and actual<=set(expected),'Unit fragment/drop-in census changed')
    unknown_units=[row['unit']for row in units if row['unit']not in declarations]
    active=[row['unit']for row in units if row['unit']in declarations
        and declarations[row['unit']].get('role')=='repository-writer'
        and row['state']in('active','activating','deactivating','reloading')]
    next_starts=[]
    for row in units:
        if row['unit']in declarations and declarations[row['unit']].get('role')=='timer'and row['state']=='active':
            if row.get('next_epoch')is None and active:continue
            require(type(row.get('next_epoch'))in(int,float)and row['next_epoch']>=now,'Timer deadline unknown/stale')
            next_starts.append(row['next_epoch'])
    known_programs=set(policy.get('reviewed_writer_programs',[]))
    require(known_programs<=set(expected),'Writer programs need exact reviewed source hashes')
    unknown_processes=[];busy=[]
    for process in processes:
        if not process['repository_client']:continue
        unit=process.get('unit')
        if unit not in declarations or declarations[unit].get('role')!='repository-writer':
            unknown_processes.append(process['pid'])
        else:busy.append(process['pid'])
    return {'schema':2,'observed_epoch':now,'repository_id':policy['repository_id'],
        'writer_policy_sha256':policy_sha,'local_inventory_complete':not unknown_units and not unknown_processes,
        'reviewed_sources':['systemd','cron','manual_sessions'],'source_review_integrity':True,
        'native_restic_writer_protocol_only':True,'future_writers_prevented':False,
        'active_known_writer_units':sorted(set(active)),'active_known_repository_clients':len(busy),
        'next_known_writer_start_epoch':min(next_starts)if next_starts else None,
        'unknown_writer_units':sorted(unknown_units),'unknown_repository_clients':len(unknown_processes),
        'service_or_schedule_changes':False,'environment_values_read':False,'credential_values_returned':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--policy',type=Path,
        default=Path('/etc/neo/backup/maintenance-writer-policy.json'));args=parser.parse_args()
    require(os.geteuid()==0,'Root-owned endpoint required')
    p=args.policy;require(p.is_file()and not p.is_symlink()and p.stat().st_uid==0
        and stat.S_IMODE(p.stat().st_mode)==0o600,'Private reviewed policy required')
    raw=p.read_bytes();policy=json.loads(raw);started=time.monotonic()
    files={path:digest_file(path)for path in policy.get('reviewed_files',{})}
    cron={}
    for root in('/etc/crontab','/etc/cron.d','/etc/cron.hourly','/etc/cron.daily',
                 '/etc/cron.weekly','/etc/cron.monthly','/var/spool/cron/crontabs'):
        path=Path(root)
        if path.is_file():cron[str(path)]=digest_file(path)
        elif path.is_dir():
            for child in sorted(path.rglob('*')):
                if child.is_file():cron[str(child)]=digest_file(child)
    observed=[]
    command=['systemctl','list-units','--all','--type=service,timer','--output=json','--no-pager']
    rows=json.loads(subprocess.check_output(command,timeout=8,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}))
    declared={row['unit']for row in policy.get('units',[])}
    names=declared|{row['unit']for row in rows if re.search(r'(?:backup|restic|pitr|hourly|retention|b2-accept|ops-config)',row['unit'])}
    for name in sorted(names):
        text=subprocess.check_output(['systemctl','show','--timestamp=unix',name,'-p','ActiveState','-p','FragmentPath','-p','DropInPaths','-p','LoadState','-p','NextElapseUSecRealtime'],
            timeout=3,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'}).decode()
        fields=dict(line.split('=',1)for line in text.splitlines());require(fields.get('LoadState')=='loaded','Unit unavailable')
        paths=([fields['FragmentPath']]if fields.get('FragmentPath')else[])+fields.get('DropInPaths','').split()
        next_value=fields.get('NextElapseUSecRealtime','')
        observed.append({'unit':name,'state':fields['ActiveState'],'source_paths':sorted(paths),
                         'next_epoch':next_epoch(next_value)})
    processes=[];programs=set(policy.get('reviewed_writer_programs',[]))
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit()or int(directory.name)==os.getpid():continue
        try:
            words=(directory/'cmdline').read_bytes().decode(errors='replace').split('\0')
            executable=(directory/'exe').resolve().name
            candidate=(executable=='restic'or any(word in programs for word in words)
                or any(re.search(r'(?:backup|pitr|hourly-online-run|hourly-files|collector)',Path(word).name)for word in words[:3]))
            if not candidate:continue
            cgroup=(directory/'cgroup').read_text();match=re.search(r'/([^/\n]+\.service)(?:/|\n|$)',cgroup)
            processes.append({'pid':int(directory.name),'unit':match.group(1)if match else None,'repository_client':True})
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError:
            processes.append({'pid':int(directory.name),'unit':None,'repository_client':True})
    require(time.monotonic()-started<=10,'Inventory exceeded freshness bound')
    print(json.dumps(assemble(policy,files,cron,observed,processes,int(time.time()),hashlib.sha256(raw).hexdigest())))


if __name__=='__main__':
    try:main()
    except Exception as error:
        # Return no source text, argv, credentials, database or user content.
        print(json.dumps({'schema':2,'local_inventory_complete':False,'failure_type':type(error).__name__,
                          'service_or_schedule_changes':False,'environment_values_read':False,'credential_values_returned':False}))
        raise SystemExit(1)
