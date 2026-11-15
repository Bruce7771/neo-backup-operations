"""Advancing-clock worst-case timings; real ExistingSSH budgeting, no network."""
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('deadline_wiring', HERE/'publication-existing-coordinator.proposed.py')
wiring = importlib.util.module_from_spec(spec); spec.loader.exec_module(wiring)


class Tests(unittest.TestCase):
    def exercise(self, fresh_at=45, failure=None, acquire_latency=15):
        clock=[0.]; events=[]; sid='a'*64
        candidate=dict(remove_snapshot_ids=[sid],protected_snapshot_ids=[],retained_snapshot_ids=[],
                       inventory_stable_for_admission=True,apply_ready=False)
        def bounded(argv,env,timeout,input):
            verb=argv[-1]; before=clock[0]
            # Every successful RPC takes its full allowed 15 seconds.
            clock[0]+=min(timeout,acquire_latency) if verb=='publication-acquire' else timeout
            events.append((verb,before,clock[0],timeout,json.loads(input)))
            if failure==verb:
                clock[0]+=4 # Existing bounded executor's TERM/KILL/reap allowance.
                raise TimeoutError('synthetic bounded child timeout')
            return b'{"ok":true}'
        rpc=wiring.ExistingSSH(['ssh','fixed-synthetic-target'],{},bounded,now=lambda:clock[0])
        def fresh(deadline):
            self.assertEqual(deadline,45);self.assertGreaterEqual(fresh_at,clock[0]);clock[0]=fresh_at
            return candidate,[{'id':sid}]
        def native(ids,timeout):
            begin=[e for e in events if e[0]=='publication-begin-forget'][-1]
            self.assertLessEqual(timeout,begin[4]['native_timeout_seconds'])
            self.assertLessEqual(timeout,116-clock[0]-41)
            events.append(('native',clock[0],clock[0]+timeout,timeout,{}));clock[0]+=timeout
            if failure=='native':
                clock[0]+=4;raise TimeoutError('synthetic bounded native timeout')
        def inventory(timeout):
            self.assertLessEqual(timeout,10);self.assertLessEqual(timeout,116-clock[0]-31)
            events.append(('inventory',clock[0],clock[0]+timeout,timeout,{}));clock[0]+=timeout
            if failure=='inventory':
                clock[0]+=4;raise TimeoutError('synthetic bounded inventory timeout')
            return []
        def post(c):
            events.append(('post',clock[0],clock[0],0,{}));return {'checked':True}
        result=None;error=None
        try:
            result=wiring.core.execute(candidate,sid,lambda c:c['remove_snapshot_ids'][0],'b'*64,
                rpc,fresh,native,inventory,post,now=lambda:clock[0])
        except (TimeoutError,ValueError) as exc:error=exc
        return result,error,clock[0],events

    def test_latest_fresh_and_all_maximal_rpcs_finish_115(self):
        result,error,end,events=self.exercise()
        self.assertIsNone(error);self.assertEqual(end,115);self.assertTrue(result['checked'])
        self.assertEqual([e[0]for e in events],['publication-acquire','publication-begin-forget','native',
            'inventory','publication-acknowledge','publication-release','post'])
        self.assertEqual(next(e[3]for e in events if e[0]=='native'),15)
        self.assertEqual(len({e[4].get('native_timeout_seconds')for e in events if e[0]=='publication-begin-forget'}),1)

    def test_early_fresh_max_native_60_also_finishes_115(self):
        result,error,end,events=self.exercise(fresh_at=0,acquire_latency=0)
        self.assertIsNone(error);self.assertEqual(end,115)
        self.assertEqual(next(e[3]for e in events if e[0]=='native'),60)

    def test_native_timeout_four_second_reap_no_release(self):
        result,error,end,events=self.exercise(failure='native')
        self.assertIsNone(result);self.assertIsNotNone(error);self.assertLessEqual(end,120)
        self.assertNotIn('publication-release',[e[0]for e in events])
        self.assertFalse(events[-1][4]['native_exit_zero'])

    def test_inventory_timeout_no_unbounded_failure_ack(self):
        result,error,end,events=self.exercise(failure='inventory')
        self.assertIsNotNone(error);self.assertLessEqual(end,120)
        self.assertNotIn('publication-release',[e[0]for e in events])

    def test_ack_timeout_second_unknown_ack_clipped_to_deadline(self):
        result,error,end,events=self.exercise(failure='publication-acknowledge')
        self.assertIsNotNone(error);self.assertLessEqual(end,120)
        ack=[e for e in events if e[0]=='publication-acknowledge']
        self.assertEqual(len(ack),2);self.assertLess(ack[-1][3],15)
        self.assertNotIn('publication-release',[e[0]for e in events])

    def test_release_timeout_known_ack_not_overwritten(self):
        result,error,end,events=self.exercise(failure='publication-release')
        self.assertIsNotNone(error);self.assertLessEqual(end,120)
        self.assertEqual(len([e for e in events if e[0]=='publication-acknowledge']),1)
        self.assertNotIn('post',[e[0]for e in events])

    def test_expired_ssh_deadline_never_spawns(self):
        def forbidden(*a,**k):raise AssertionError('expired RPC spawned')
        rpc=wiring.ExistingSSH(['ssh','fixture'],{},forbidden,now=lambda:100)
        with self.assertRaisesRegex(ValueError,'deadline exhausted'):rpc.release('a'*64,deadline=99)

    def test_slow_begin_recomputes_remaining_before_native(self):
        result,error,end,events=self.exercise(fresh_at=44)
        begin=next(e for e in events if e[0]=='publication-begin-forget')
        native=next(e for e in events if e[0]=='native')
        self.assertEqual(begin[2],59);self.assertEqual(native[3],16)
        self.assertIsNone(error);self.assertEqual(end,115)


if __name__=='__main__':unittest.main()
