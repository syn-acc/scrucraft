"""Pacing/stop concurrency and diagnostics must not hide closure or reveal credentials."""
import json
import pathlib
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).parents[1]/'sdk'))
from scru_minecraft import AgentClient
from scru_minecraft.realtime import RealtimeClient


class RealtimeDiagnosticsTests(unittest.TestCase):
    def stream(self):return RealtimeClient(AgentClient('https://example.invalid','synthetic-private-token-123456','Body',timeout=2))
    def test_pacing_rechecks_deadline_moved_while_waiting(self):
        stream=self.stream();clock=[0.0];waits=[];sent=[]
        class Stopped:
            def is_set(self):return False
            def wait(self,delay):
                waits.append(delay);clock[0]+=delay
                if len(waits)==1:stream.next_request=.020
        class Connection:
            def send(self,message):
                sent.append(clock[0]);request=json.loads(message)
                with stream.changed:stream.pending[request['request_id']]={'status':200,'result':{'ok':True}}
        stream.stopped=Stopped();stream.connection=Connection();stream.next_request=.006
        with patch('scru_minecraft.realtime.time.monotonic',side_effect=lambda:clock[0]):
            self.assertTrue(stream.request('PUT','/v1/lease')['ok'])
        self.assertEqual(2,len(waits));self.assertAlmostEqual(.020,sent[0])
    def test_stop_bypasses_an_ordinary_request_waiting_for_ack(self):
        stream=self.stream();sent=[];started=threading.Event();results=[]
        class Connection:
            def send(self,message):
                request=json.loads(message);sent.append(request)
                if request['method']=='POST':started.set();return
                with stream.changed:
                    stream.pending[request['request_id']]={'status':200,'result':{'status':'stopped'}}
                    stream.changed.notify_all()
        stream.connection=Connection()
        worker=threading.Thread(target=lambda:results.append(stream.request('POST','/v1/actions',{'op':'look_at'})))
        worker.start();self.assertTrue(started.wait(1))
        before=time.monotonic();self.assertEqual('stopped',stream.stop()['status'])
        self.assertLess(time.monotonic()-before,.2);self.assertTrue(worker.is_alive())
        with stream.changed:
            stream.pending[sent[0]['request_id']]={'status':200,'result':{'state':'accepted'}}
            stream.changed.notify_all()
        worker.join(1);self.assertFalse(worker.is_alive());self.assertEqual('accepted',results[0]['state'])
    def test_safe_diagnostics_preserve_type_code_and_redact_payload(self):
        stream=self.stream();secret=stream.client.token
        class Connection:
            close_code=1011
            close_reason='stream_error_'+secret.replace('-','_')
            def __iter__(self):raise RuntimeError('private request '+secret)
        # Unrecognized remote reasons must not pass through merely because they are printable.
        Connection.close_reason='payload '+secret
        stream.connection=Connection();stream._read()
        self.assertEqual('RuntimeError',stream.last_disconnect['exception_type'])
        self.assertEqual(1011,stream.last_disconnect['close_code'])
        self.assertNotIn(secret,str(stream.error));self.assertNotIn('private request',str(stream.error))
        self.assertEqual('unrecognized_close_reason',stream.last_disconnect['close_reason'])

    def test_expired_handle_reconciles_unknown_without_waiting_or_replay(self):
        from scru_minecraft import ActionHandle
        stream=self.stream();rid='expired_action_0001';calls=[]
        stream.observation={'action_results':[]}
        stream.submitted[rid]={'body_epoch':'old','deadline':time.monotonic()-1}
        def read(action_id):
            calls.append(action_id);return [{'id':action_id,'state':'unknown','reason':'result_not_retained'}]
        stream.action_results=read
        outcome=ActionHandle(stream,{'id':rid,'body_epoch':'old','state':'accepted'}).wait(.5)
        self.assertEqual('unknown',outcome['state']);self.assertEqual([rid],calls)

    def test_old_handle_cannot_accept_reused_id_from_new_body_epoch(self):
        from scru_minecraft import ActionHandle,ActionFailed
        stream=self.stream();rid='reused_action_0001';calls=[]
        newer={'id':rid,'state':'done','body_epoch':'new','reason':'dropped'}
        stream.observation={'action_results':[newer]}
        def read(action_id):calls.append(action_id);return [dict(newer)]
        stream.action_results=read
        with self.assertRaises(ActionFailed) as raised:
            ActionHandle(stream,{'id':rid,'body_epoch':'old','state':'accepted'}).result(.1)
        self.assertEqual('unknown',raised.exception.outcome['state'])
        self.assertEqual('body_epoch_mismatch',raised.exception.outcome['reason'])
        self.assertEqual('old',raised.exception.outcome['body_epoch']);self.assertEqual([rid],calls)

    def test_wait_timeout_reads_authoritative_result_once(self):
        stream=self.stream();rid='terminal_action_0001';calls=[]
        stream.observation={'action_results':[]}
        stream.submitted[rid]={'body_epoch':'epoch','deadline':time.monotonic()+30}
        def read(action_id):calls.append(action_id);return [{'id':action_id,'state':'done','body_epoch':'epoch'}]
        stream.action_results=read
        self.assertEqual('done',stream.wait_action(rid,.001,body_epoch='epoch')['state'])
        self.assertEqual([rid],calls)

    def test_missing_from_bounded_push_window_reads_once_without_waiting(self):
        stream=self.stream();rid='older_finished_0001';calls=[]
        stream.observation={'action_results':[],'action_results_truncated':True}
        stream.submitted[rid]={'body_epoch':'epoch','deadline':time.monotonic()+30}
        def read(action_id):calls.append(action_id);return [{'id':action_id,'state':'done','body_epoch':'epoch'}]
        stream.action_results=read
        with patch.object(stream.changed,'wait_for',side_effect=AssertionError('Old result should reconcile immediately')):
            self.assertEqual('done',stream.wait_action(rid,30,body_epoch='epoch')['state'])
        self.assertEqual([rid],calls)
