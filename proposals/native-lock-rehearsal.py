#!/usr/bin/env python3
"""Actual restic operations on a tiny LOCAL synthetic encrypted repository.

Never loads B2/SSH/Neo configuration or credentials. No cloud repository used.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time


def main():
    with tempfile.TemporaryDirectory(prefix='native-restic-fixture-',dir=os.environ.get('RUNNER_TEMP'))as tmp:
        root=Path(tmp);root.chmod(0o700);password=root/'password';password.write_text('synthetic-fixture-only');password.chmod(0o600)
        home=root/'home';home.mkdir(mode=0o700)
        env={'PATH':os.defpath,'HOME':str(home),'RESTIC_REPOSITORY':str(root/'repo'),'RESTIC_PASSWORD_FILE':str(password)}
        binary=shutil.which('restic');assert binary is not None
        def call(args,ok=True):
            result=subprocess.run([binary,'--no-cache']+args,env=env,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
            if ok and result.returncode:raise RuntimeError('Local native fixture command failed')
            return result
        assert call(['version']).stdout.startswith(b'restic 0.16.4 ')
        call(['init'])
        source=root/'source';source.mkdir();database=source/'fixture.db'
        with closing(sqlite3.connect(database))as db:
            db.execute('CREATE TABLE records(value TEXT)');db.execute("INSERT INTO records VALUES('first')");db.commit()
        def backup():
            lines=call(['backup','--json','--host','fixture','--tag','fixture',str(source)]).stdout.splitlines()
            sid=next(json.loads(line)['snapshot_id']for line in lines if json.loads(line).get('message_type')=='summary')
            assert re.fullmatch('[0-9a-f]{64}',sid);return sid
        first=backup()
        with closing(sqlite3.connect(database))as db:
            db.execute("UPDATE records SET value='retained'");db.commit()
        retained=backup()
        held=subprocess.Popen([binary,'--no-cache','backup','--stdin','--stdin-filename','held.txt','--host','fixture-held'],
            env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                if call(['--no-lock','list','locks']).stdout.strip():break
                if held.poll()is not None:raise RuntimeError('Shared lock fixture exited too soon')
                time.sleep(.05)
            else:raise RuntimeError('Shared lock fixture did not acquire a native lock')
            refused=call(['--retry-lock','0s','forget',first],ok=False)
            assert refused.returncode!=0,'Native forget must not bypass an active backup lock'
            out,error=held.communicate(b'synthetic-held-input',timeout=10)
            assert held.returncode==0
        finally:
            if held.poll()is None:held.kill();held.communicate(timeout=3)
        assert not call(['--no-lock','list','locks']).stdout.strip()
        call(['--retry-lock','0s','forget',first])
        rows=json.loads(call(['--no-lock','snapshots','--json']).stdout)
        assert first not in{r['id']for r in rows}and retained in{r['id']for r in rows}
        call(['--retry-lock','0s','prune','--max-repack-size','16M'])
        call(['--no-lock','check'])
        target=root/'restore';target.mkdir()
        call(['--no-lock','restore','--verify','--target',str(target),retained])
        restored=target/str(database).lstrip('/')
        with closing(sqlite3.connect(restored))as db:
            assert db.execute('PRAGMA quick_check').fetchall()==[('ok',)]
            assert db.execute('SELECT value FROM records').fetchone()==('retained',)
        print(json.dumps({'scope':'LOCAL-synthetic-native-lock-rehearsal','cloud_repository_used':False,
            'actual_busy_backup_forget_refused':True,'shared_backup_completed':True,'exact_fixture_snapshot_forgotten':True,
            'native_prune_and_check_passed':True,'retained_sqlite_actual_restore_passed':True,
            'application_or_backup_services_changed':False}))


if __name__=='__main__':main()
