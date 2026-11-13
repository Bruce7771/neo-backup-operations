#!/usr/bin/env python3
"""Synthetic LOCAL repository only: does default restic dump enroll a lock?

No cloud credentials, real repository, services or application data are used.
The dump remains blocked on its stdout pipe so lock absence is observable.
"""
import json,os,select,shutil,subprocess,tempfile,time
from pathlib import Path

def main():
    with tempfile.TemporaryDirectory(prefix='neo-native-reader-fixture-',dir='/var/tmp')as temp:
        root=Path(temp);root.chmod(0o700)
        if shutil.disk_usage(root).free<2_064_000_000:raise RuntimeError('Fixture reserve unavailable')
        password=root/'password';password.write_text('synthetic-local-only');password.chmod(0o600)
        data=root/'fixture.bin';data.write_bytes(os.urandom(4*1024*1024))
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(root),
             'RESTIC_REPOSITORY':str(root/'repo'),'RESTIC_PASSWORD_FILE':str(password)}
        def run(args):return subprocess.run(['/usr/bin/restic',*args],env=env,stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,check=True,timeout=15).stdout
        if not run(['version']).startswith(b'restic 0.16.4 '):raise RuntimeError('Wrong fixture restic version')
        run(['init']);log=run(['backup','--json',str(data)])
        snapshot=next(json.loads(line)['snapshot_id']for line in log.splitlines()if json.loads(line).get('message_type')=='summary')
        observations=[]
        for nolock in(False,True):
            run(['unlock'])
            if run(['--no-lock','list','locks']).splitlines():raise RuntimeError('Fixture lock baseline not empty')
            command=['/usr/bin/restic']+(['--no-lock']if nolock else[])+['dump',snapshot,str(data)]
            process=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            try:
                if not select.select([process.stdout],[],[],5)[0]:raise RuntimeError('Dump did not reach output')
                time.sleep(.1)
                if process.poll()is not None:raise RuntimeError('Fixture dump was not held by pipe')
                locks=run(['--no-lock','list','locks']).splitlines()
                observations.append({'explicit_no_lock':nolock,'dump_actually_active':True,
                                     'native_lock_count':len(locks)})
            finally:
                process.terminate()
                try:process.wait(3)
                except subprocess.TimeoutExpired:process.kill();process.wait(3)
                process.stdout.close()
        print(json.dumps({'scope':'local-native-default-dump-lock-observation','restic_version':'0.16.4',
            'observations':observations,'cloud_calls':0,'real_repository_mutations':0,'services_changed':False}))

if __name__=='__main__':main()
