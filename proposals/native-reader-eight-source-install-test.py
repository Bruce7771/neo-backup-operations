#!/usr/bin/env python3
import importlib.util,json,os,stat,tempfile,time,unittest
from unittest.mock import patch
from pathlib import Path
spec=importlib.util.spec_from_file_location('install',Path(__file__).with_name('native-reader-eight-source-install.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Installation(unittest.TestCase):
 def setup_tree(self,root):
  lib=root/'lib';lib.mkdir(mode=0o700);rollback=root/'rollback';rollback.mkdir(mode=0o700)
  old={n:('original:'+n).encode()for n in m.BEFORE};modes={n:0o755 for n in old};new={n:('candidate:'+n).encode()for n in old}
  for n,b in old.items():(lib/n).write_bytes(b);(lib/n).chmod(0o755)
  return lib,rollback,old,modes,new
 def test_exact_all8_replaced_and_preserved700(self):
  with tempfile.TemporaryDirectory(prefix='neo-installer-fixture-',dir='/var/tmp')as d:
   root=Path(d);root.chmod(0o700);lib,rollback,old,modes,new=self.setup_tree(root)
   state=m.replace_batch(old,modes,new,rollback,root/'receipt',lib=lib)
   self.assertEqual(state['status'],'INSTALLED');self.assertEqual(state['before_modes'],modes)
   self.assertEqual(len(list(rollback.iterdir())),8)
   for n,b in old.items():
    backup=rollback/('native-reader-before-'+n+'.'+m.digest(b)+'.txt');self.assertEqual(backup.read_bytes(),b);self.assertEqual(backup.stat().st_mode&0o777,0o700)
    self.assertEqual((lib/n).read_bytes(),new[n]);self.assertEqual((lib/n).stat().st_mode&0o777,0o700)
 def test_partial_failure_rolls_back_ALL8_bytes_and_modes(self):
  with tempfile.TemporaryDirectory(prefix='neo-installer-fixture-',dir='/var/tmp')as d:
   root=Path(d);root.chmod(0o700);lib,rollback,old,modes,new=self.setup_tree(root)
   with self.assertRaises(RuntimeError):m.replace_batch(old,modes,new,rollback,root/'receipt',lib=lib,fail_after=3)
   self.assertEqual(json.loads((root/'receipt').read_text())['status'],'ROLLED_BACK')
   for n,b in old.items():self.assertEqual((lib/n).read_bytes(),b);self.assertEqual((lib/n).stat().st_mode&0o777,modes[n])
 def test_postrename_directory_fsync_failure_restores_ALL8_and_modes(self):
  with tempfile.TemporaryDirectory(prefix='neo-installer-fixture-',dir='/var/tmp')as d:
   root=Path(d);root.chmod(0o700);lib,rollback,old,modes,new=self.setup_tree(root)
   third=list(new)[2];real_fsync=os.fsync;injected=[]
   def fail_directory_fsync_after_third_rename(fd):
    if not injected and stat.S_ISDIR(os.fstat(fd).st_mode) and (lib/third).read_bytes()==new[third]:
     injected.append(True);raise OSError('Synthetic postrename fsync failure')
    return real_fsync(fd)
   with patch.object(m.os,'fsync',side_effect=fail_directory_fsync_after_third_rename):
    with self.assertRaises(OSError):m.replace_batch(old,modes,new,rollback,root/'receipt',lib=lib)
   self.assertEqual(injected,[True]);self.assertEqual(json.loads((root/'receipt').read_text())['status'],'ROLLED_BACK')
   for n,b in old.items():self.assertEqual((lib/n).read_bytes(),b);self.assertEqual((lib/n).stat().st_mode&0o777,modes[n])
 def test_mode_is_set_on_fd_before_payload_fsync(self):
  with tempfile.TemporaryDirectory(prefix='neo-installer-fixture-',dir='/var/tmp')as d:
   root=Path(d);root.chmod(0o700);seen=[];real_fsync=os.fsync
   def verify_mode_then_fsync(fd):
    info=os.fstat(fd)
    if stat.S_ISREG(info.st_mode):seen.append(stat.S_IMODE(info.st_mode));self.assertEqual(stat.S_IMODE(info.st_mode),0o700)
    return real_fsync(fd)
   with patch.object(m.os,'fsync',side_effect=verify_mode_then_fsync):m.atomic(root/'control',b'synthetic-control',0o700)
   self.assertEqual(seen,[0o700])
 def test_expired_deadline_writes_no_candidate(self):
  with tempfile.TemporaryDirectory(prefix='neo-installer-fixture-',dir='/var/tmp')as d:
   root=Path(d);root.chmod(0o700);lib,rollback,old,modes,new=self.setup_tree(root)
   with self.assertRaises(ValueError):m.replace_batch(old,modes,new,rollback,root/'receipt',lib=lib,deadline=time.monotonic()-1)
   self.assertTrue(all((lib/n).read_bytes()==v for n,v in old.items()))
 def test_wrong_candidate_package_rejected(self):
  with self.assertRaises(ValueError):m.decoded({'unexpected':'YWJj'})
 def test_bad_symlink_rollback_refused(self):
  with tempfile.TemporaryDirectory(prefix='neo-installer-fixture-',dir='/var/tmp')as d:
   root=Path(d);root.chmod(0o700);lib,rollback,old,modes,new=self.setup_tree(root)
   first=next(iter(old));p=rollback/('native-reader-before-'+first+'.'+m.digest(old[first])+'.txt');p.symlink_to(lib/first)
   with self.assertRaises(ValueError):m.replace_batch(old,modes,new,rollback,root/'receipt',lib=lib)
if __name__=='__main__':unittest.main()
