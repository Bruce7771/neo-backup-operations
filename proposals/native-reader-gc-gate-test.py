#!/usr/bin/env python3
"""LOCAL synthetic native-repository reader/GC gate fixture. Never production."""
import fcntl,hashlib,json,os,select,shutil,subprocess,tempfile,time
from pathlib import Path

def main():
    with tempfile.TemporaryDirectory(prefix='neo-native-reader-gate-',dir='/var/tmp') as temp:
        root=Path(temp);root.chmod(0o700)
        if shutil.disk_usage(root).free<2_064_000_000:raise RuntimeError('Fixture reserve unavailable')
        password=root/'password';password.write_text('synthetic-only');password.chmod(0o600)
        data=root/'fixture.bin';data.write_bytes(os.urandom(4*1024*1024))
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(root),'RESTIC_REPOSITORY':str(root/'repo'),'RESTIC_PASSWORD_FILE':str(password)}
        def run(args):return subprocess.run(['/usr/bin/restic',*args],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=30).stdout
        def backup():return next(json.loads(x)['snapshot_id'] for x in run(['backup','--json',str(data)]).splitlines() if json.loads(x).get('message_type')=='summary')
        if not run(['version']).startswith(b'restic 0.16.4 '):raise RuntimeError('Wrong restic version')
        run(['init']);old=backup();data.write_bytes(os.urandom(4*1024*1024));retained=backup();expected=hashlib.sha256(data.read_bytes()).hexdigest()
        lock=root/'cooperative.lock';readerfd=os.open(lock,os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(readerfd,fcntl.LOCK_SH)
        reader=subprocess.Popen(['/usr/bin/restic','--no-lock','dump',retained,str(data)],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        exfd=None
        try:
            if not select.select([reader.stdout],[],[],5)[0] or reader.poll() is not None:raise RuntimeError('Reader not active')
            if run(['--no-lock','list','locks']).splitlines():raise RuntimeError('No-lock reader unexpectedly native locked')
            exfd=os.open(lock,os.O_RDWR);start=time.monotonic()
            try:fcntl.flock(exfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:denied=True
            else:raise RuntimeError('GC admitted during no-lock reader')
            refusal=time.monotonic()-start
            if reader.poll() is not None:raise RuntimeError('Reader interrupted')
            payload=reader.communicate(timeout=10)[0]
            if reader.returncode or hashlib.sha256(payload).hexdigest()!=expected:raise RuntimeError('Active reader result corrupt')
        finally:
            if reader.poll() is None:reader.kill();reader.wait(3)
            os.close(readerfd)
        fcntl.flock(exfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        writerfd=os.open(lock,os.O_RDWR)
        try:
            try:fcntl.flock(writerfd,fcntl.LOCK_SH|fcntl.LOCK_NB)
            except BlockingIOError:future_writer_waits=True
            else:raise RuntimeError('Future producer bypassed GC')
            start=time.monotonic();run(['--retry-lock','0s','forget',old]);run(['--retry-lock','0s','prune']);run(['check']);gc_seconds=time.monotonic()-start
        finally:os.close(exfd)
        fcntl.flock(writerfd,fcntl.LOCK_SH|fcntl.LOCK_NB);os.close(writerfd)
        restored=run(['dump',retained,str(data)])
        if hashlib.sha256(restored).hexdigest()!=expected:raise RuntimeError('Retained data failed after native prune')
        # Kernel releases a controller's EX when the owning process exits.
        child=subprocess.Popen(['/usr/bin/flock','-F','-x',str(lock),'/bin/sleep','10'])
        probe=os.open(lock,os.O_RDWR)
        try:
            until=time.monotonic()+2
            while True:
                try:fcntl.flock(probe,fcntl.LOCK_SH|fcntl.LOCK_NB)
                except BlockingIOError:break
                else:fcntl.flock(probe,fcntl.LOCK_UN)
                if time.monotonic()>until:raise RuntimeError('Crash fixture did not acquire EX')
                time.sleep(.01)
            child.terminate();child.wait(3)
            fcntl.flock(probe,fcntl.LOCK_SH|fcntl.LOCK_NB)
        finally:
            os.close(probe)
            if child.poll() is None:child.kill();child.wait(3)
        print(json.dumps({'scope':'local-native-no-lock-reader-cooperative-gc-fixture','restic_version':'0.16.4','active_no_lock_reader_denied_gc':denied,'active_reader_completed_sha256_match':True,'gc_refusal_seconds':round(refusal,6),'future_writer_waited_then_admitted':future_writer_waits,'native_forget_prune_check_seconds':round(gc_seconds,6),'native_retry_lock_zero_supported':True,'retained_actual_restore_sha256_match':True,'controller_exit_released_ex':True,'cloud_calls':0,'real_repository_mutations':0,'runtime_installed':False}))
if __name__=='__main__':main()
