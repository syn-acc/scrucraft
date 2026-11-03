"""Pacing/stop concurrency and diagnostics must not hide closure or reveal credentials."""
import json
import pathlib
import sys
import threading
import time
import unittest
import traceback
import concurrent.futures
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).parents[1]/'sdk'))
from scru_minecraft import AgentClient
from scru_minecraft.realtime import RealtimeClient


class RealtimeDiagnosticsTests(unittest.TestCase):
    def stream(self):return RealtimeClient(AgentClient('https://example.invalid','synthetic-private-token-123456','Body',timeout=2))
    def test_failed_reconnect_preserves_original_ids_for_later_reconciliation(self):
        stream=self.stream();rid='uncertain_mutation_01';attempts=[];reads=[]
        original={rid:{'body_epoch':'original_epoch','deadline':time.monotonic()+30}}
        stream.submitted=dict(original);stream.close=lambda:None
        def fail():attempts.append('attempt');raise ConnectionError('fixture network unavailable')
        stream.connect=fail
        with self.assertRaises(ConnectionError):stream.reconnect(attempts=2,initial_delay=0)
        self.assertEqual(2,len(attempts));self.assertEqual(original,stream.submitted)
        stream.connect=lambda:stream
        stream.action_results=lambda action_id:reads.append(action_id) or [{'id':action_id,'state':'unknown','reason':'result_not_retained'}]
        self.assertIs(stream,stream.reconnect(initial_delay=0));self.assertEqual([rid],reads)
        self.assertEqual('unknown',stream.reconciled[rid]['state']);self.assertEqual(original,stream.submitted)

    def test_paused_observation_and_chat_iterators_resume_after_high_cursor_reconnect(self):
        stream=self.stream();stream.close=lambda:None
        def message(rid):return {'id':rid,'speaker':'Fixture','text':rid,'at':1}
        stream.sequence=100000
        stream.observation={'body_epoch':'same','dimension':'minecraft:overworld','public_chat':[message('old')]}
        stream.snapshots=[(stream.sequence,dict(stream.observation),False)]
        observations=stream.observations();chat=stream.chat_events()
        self.assertEqual(100000,next(observations).sequence);self.assertEqual('old',next(chat).id)
        # Exercise the actual reader without a network or sleep. A completed
        # fixture iterator closes it; clear that synthetic close to model an open socket.
        attempts=[]
        def connect():
            attempts.append(1)
            row={'body_epoch':'same','dimension':'minecraft:overworld','public_chat':[message('old'),message('new')]}
            stream.connection=iter([json.dumps({'type':'snapshot','observation':row})])
            stream._read();stream.error=None;stream.stopped.clear()
            if len(attempts)==1:raise ConnectionError('fixture first attempt failed after receiving snapshot')
            return stream
        stream.connect=connect;stream.reconnect(attempts=2,initial_delay=0)
        def ready(predicate,timeout=None):
            self.assertTrue(predicate(),'Paused iterator waited for the old cursor after reconnect')
            return True
        with patch.object(stream.changed,'wait_for',side_effect=ready):
            event=next(observations);self.assertEqual(100002,event.sequence);self.assertTrue(event.resync)
            self.assertTrue(event.gap);self.assertEqual('new',next(chat).id)
        self.assertEqual(2,len(attempts));self.assertEqual({},stream.pending)

    def test_policy_closed_reconnect_does_not_retry_or_resume(self):
        stream=self.stream();calls=[];stream.close=lambda:None
        def rejected():
            calls.append('connect');stream.last_disconnect={'close_code':1008,'close_reason':'stream_error_APIError_not_whitelisted'}
            raise ConnectionError('fixture policy rejection')
        stream.connect=rejected
        with self.assertRaises(ConnectionError):stream.reconnect(attempts=5,initial_delay=0)
        self.assertEqual(['connect'],calls)

    def test_invalid_reconnect_arguments_leave_existing_control_untouched(self):
        stream=self.stream();stream.close=lambda:self.fail('Invalid reconnect options closed current control')
        for options in ({'attempts':True},{'attempts':0},{'attempts':6},{'initial_delay':None},
                        {'initial_delay':True},{'initial_delay':float('nan')},{'initial_delay':float('inf')}):
            with self.subTest(options=options),self.assertRaises(ValueError):stream.reconnect(**options)

    def test_repeated_concurrent_failure_reads_have_bounded_tracebacks_and_original_cause(self):
        stream=self.stream();rid='pending_action_000001'
        stream.observation={'action_results':[{'id':rid,'state':'accepted','body_epoch':'epoch'}]}
        try:raise ConnectionError('Transport closed; action outcome unknown; commands are never automatically replayed')
        except ConnectionError as error:original=error
        stream.error=original
        origin_depth=len(traceback.extract_tb(original.__traceback__))
        operations=[stream.observe,lambda:stream.request('POST','/v1/actions',{'op':'drop'}),
                    lambda:stream.wait_action(rid,.01),lambda:next(stream.observations())]
        def read(index):
            try:operations[index%len(operations)]()
            except ConnectionError as error:
                self.assertIsNot(original,error);self.assertIs(original,error.__cause__)
                self.assertIn('outcome unknown',str(error));self.assertIn('never automatically replayed',str(error))
                return len(traceback.extract_tb(error.__traceback__)),len(''.join(traceback.format_exception(error)))
            self.fail('Disconnected access returned success')
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:results=list(executor.map(read,range(200)))
        self.assertEqual(origin_depth,len(traceback.extract_tb(original.__traceback__)))
        self.assertLessEqual(max(depth for depth,_ in results),6)
        self.assertLess(max(size for _,size in results),3000)
        self.assertEqual({},stream.pending,'No failed read may submit or replay a command')

    def test_http_background_error_preserves_gateway_fields_without_traceback_growth(self):
        from scru_minecraft import GatewayError
        client=self.stream().client;client._lease='synthetic-lease'
        try:raise GatewayError(429,'rate_limited',3)
        except GatewayError as error:original=error
        client._error=original;depth=len(traceback.extract_tb(original.__traceback__))
        for index in range(100):
            try:
                if index%2:next(client.observations())
                else:client.set_goal('rest','synthetic-frame')
            except GatewayError as error:
                self.assertIsNot(error,original);self.assertIs(error.__cause__,original)
                self.assertEqual((429,'rate_limited',3),(error.status,error.code,error.retry_after))
            else:self.fail('Background error was lost')
        self.assertEqual(depth,len(traceback.extract_tb(original.__traceback__)))

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
