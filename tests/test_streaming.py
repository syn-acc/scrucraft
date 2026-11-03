import importlib.util
import json
import pathlib
import threading
import time
import sys
import unittest
import test_controller_gateway as fixtures

try:
    from websockets.sync.client import connect
    from websockets.exceptions import ConnectionClosed
    AVAILABLE=True
except ImportError:
    AVAILABLE=False


@unittest.skipUnless(AVAILABLE,'Install agent-gateway/requirements.txt to test real WebSockets')
class StreamTests(unittest.TestCase):
    def test_private_observation_ack_is_scoped_to_connection_epoch(self):
        fixture=fixtures.GatewayTests();fixture.setUp();fixture.g.clock=time.monotonic
        sample=fixtures.frame(tick=101);sample.update(body_epoch='old_epoch',control_protocol=2,raw_capabilities=['look_at'],action_results=[])
        fixture.g.frame(sample)
        streaming=fixtures.module('scru_streaming_observation_ack','agent-gateway/streaming.py')
        server=streaming.make_server(fixture.g,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with connect('ws://127.0.0.1:'+str(server.socket.getsockname()[1])+'/internal/body',proxy=None,close_timeout=.2) as body:
                body.send(json.dumps({'token':'internal-test-secret','agent':'Forge','body_epoch':'new_epoch'}))
                first=json.loads(body.recv(timeout=2))
                self.assertEqual(-1,first['observed_tick']);self.assertEqual('new_epoch',first['action']['body_epoch'])
                sample.update(tick=102,body_epoch='new_epoch',captured_at_ms=time.time_ns()//1_000_000)
                body.send(json.dumps(sample))
                while True:
                    acknowledged=json.loads(body.recv(timeout=2))
                    if acknowledged['observed_tick']==102:break
                self.assertEqual('new_epoch',acknowledged['action']['body_epoch'])
                with fixture.g.changed:
                    self.assertEqual({'body_epoch':'new_epoch','tick':102},fixture.g.processed_frames['Forge'])
                    self.assertIn('body_receive_lag_ms',fixture.g.frames['Forge'])
                # A frame with a foreign epoch is rejected before processing/ACK.
                sample.update(tick=103,body_epoch='foreign_epoch');body.send(json.dumps(sample))
                with self.assertRaises(ConnectionClosed):
                    while True:
                        value=json.loads(body.recv(timeout=2));self.assertNotEqual(103,value['observed_tick'])
                self.assertEqual(102,fixture.g.processed_frames['Forge']['tick'])
        finally:
            server.shutdown();server.socket.close();thread.join(3);fixture.tearDown()

    def test_private_grant_age_includes_blocked_construction_and_keeps_action_deadline(self):
        fixture=fixtures.GatewayTests();fixture.setUp()
        sample=fixtures.frame(tick=101);sample.update(body_epoch='epoch',control_protocol=2,raw_capabilities=['look_at'],action_results=[])
        fixture.g.frame(sample);fixture.lease()
        accepted=fixture.call('POST','/v1/actions',{'id':'delayed_grant_00001','op':'look_at','body_epoch':'epoch','target':[0,65,0]})
        expected=fixture.g.actions['Forge'][accepted['id']]['control']['deadline_ms']
        original=fixture.g.realtime_control;calls=[]
        def delayed(name):
            reply=original(name);calls.append(name)
            if len(calls)==1:time.sleep(.25)
            return reply
        fixture.g.realtime_control=delayed
        streaming=fixtures.module('scru_streaming_expiring_envelope','agent-gateway/streaming.py')
        server=streaming.make_server(fixture.g,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with connect('ws://127.0.0.1:'+str(server.socket.getsockname()[1])+'/internal/body',proxy=None,close_timeout=.2) as body:
                body.send(json.dumps({'token':'internal-test-secret','agent':'Forge','body_epoch':'epoch'}))
                first=json.loads(body.recv(timeout=2))
                self.assertEqual(200,first['expires_at_ms']-first['issued_at_ms'])
                self.assertLessEqual(first['expires_at_ms'],time.time_ns()//1_000_000,
                                     'Old work was restamped fresh after construction stalled')
                second=json.loads(body.recv(timeout=2))
                self.assertGreater(second['issued_at_ms'],first['issued_at_ms'])
                self.assertEqual(200,second['expires_at_ms']-second['issued_at_ms'])
                for envelope in (first,second):
                    self.assertIs(type(envelope['issued_at_ms']),int)
                    self.assertIs(type(envelope['expires_at_ms']),int)
                    self.assertEqual(expected,envelope['action']['commands'][0]['deadline_ms'])
        finally:
            server.shutdown();server.socket.close();thread.join(3);fixture.tearDown()

    def test_mixed_case_body_name_releases_canonical_lease_on_disconnect(self):
        fixture=fixtures.GatewayTests();fixture.setUp();fixture.g.clock=time.monotonic
        sample=fixtures.frame(tick=101);sample.update(body_epoch='epoch',control_protocol=2,raw_capabilities=['look_at'],action_results=[])
        fixture.g.frame(sample)
        streaming=fixtures.module('scru_streaming_name_case','agent-gateway/streaming.py')
        server=streaming.make_server(fixture.g,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with connect('ws://127.0.0.1:'+str(server.socket.getsockname()[1])+'/v1/events',proxy=None,close_timeout=.2) as connection:
                connection.send(json.dumps({'token':fixture.token,'agent':'fOrGe'}))
                self.assertEqual('Forge',json.loads(connection.recv(timeout=2))['observation']['agent'])
                connection.send(json.dumps({'request_id':'case_lease','method':'POST','path':'/v1/lease','body':{}}))
                while True:
                    reply=json.loads(connection.recv(timeout=2))
                    if reply.get('request_id')=='case_lease':break
                self.assertEqual(200,reply['status'])
                with fixture.g.changed:self.assertIsNotNone(fixture.g.active('Forge'))
            deadline=time.monotonic()+1
            with fixture.g.changed:
                released=fixture.g.changed.wait_for(lambda:fixture.g.active('Forge') is None,timeout=max(0,deadline-time.monotonic()))
            self.assertTrue(released,'Mixed-case stream disconnect left canonical body controlled')
        finally:
            server.shutdown();server.socket.close();thread.join(3);fixture.tearDown()

    def test_socket_snapshot_is_bounded_but_old_full_receipt_remains_queryable(self):
        fixture=fixtures.GatewayTests();fixture.setUp();fixture.g.clock=time.monotonic
        sample=fixtures.frame(tick=101)
        rows=[dict(id='old_result_'+str(i).zfill(16),state='done',body_epoch='epoch',reason='oriented',tick=i) for i in range(350)]
        sample.update(body_epoch='epoch',control_protocol=2,raw_capabilities=['look_at'],action_results=rows)
        fixture.g.frame(sample)
        streaming=fixtures.module('scru_streaming_bounded_history','agent-gateway/streaming.py')
        server=streaming.make_server(fixture.g,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with connect('ws://127.0.0.1:'+str(server.socket.getsockname()[1])+'/v1/events',proxy=None,close_timeout=.2) as connection:
                connection.send(json.dumps({'token':fixture.token,'agent':'Forge'}))
                event=json.loads(connection.recv(timeout=2));observation=event['observation']
                self.assertEqual(64,len(observation['action_results']));self.assertTrue(observation['action_results_truncated'])
                self.assertNotIn(rows[0]['id'],[r['id'] for r in observation['action_results']])
                connection.send(json.dumps({'request_id':'old_history','method':'GET','path':'/v1/action-results','body':{'action_id':rows[0]['id']}}))
                while True:
                    response=json.loads(connection.recv(timeout=2))
                    if response.get('request_id')=='old_history':break
                self.assertEqual(200,response['status']);self.assertEqual('done',response['result']['results'][0]['state'])
                self.assertEqual(rows[0]['id'],response['result']['results'][0]['id'])
                self.assertEqual(350,len(fixture.g.actions['Forge']))
        finally:
            server.shutdown();server.socket.close();thread.join(3);fixture.tearDown()

    def test_body_notifications_do_not_wake_other_body_waiters(self):
        fixture=fixtures.GatewayTests();fixture.setUp()
        unrelated=fixture.g.body_condition('Other');awake=[];ready=threading.Event()
        def waiter():
            with unrelated:
                ready.set();awake.append(unrelated.wait(timeout=.15))
        worker=threading.Thread(target=waiter);worker.start();self.assertTrue(ready.wait(1))
        try:
            for _ in range(20):fixture.g.notify_body('Forge')
            worker.join(1);self.assertEqual([False],awake,'Another body notification woke this condition')
        finally:fixture.tearDown()

    def test_unrelated_body_telemetry_does_not_amplify_grants(self):
        fixture=fixtures.GatewayTests();fixture.setUp();fixture.g.clock=time.monotonic
        fixture.g.handle('POST','/v1/agents',fixture.headers,{'name':'Second','area':fixtures.AREA})
        samples=[]
        for name in ('Forge','Second'):
            sample=fixtures.frame(name=name,tick=101)
            sample.update(body_epoch='epoch_'+name,control_protocol=2,raw_capabilities=['look_at'],action_results=[])
            fixture.g.frame(sample);samples.append(sample)
        streaming=fixtures.module('scru_streaming_wakeups','agent-gateway/streaming.py')
        server=streaming.make_server(fixture.g,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='ws://127.0.0.1:'+str(server.socket.getsockname()[1])+'/internal/body'
        try:
            with connect(base,proxy=None,close_timeout=.2) as first,connect(base,proxy=None,close_timeout=.2,max_queue=None) as second:
                for connection,sample in zip((first,second),samples):
                    connection.send(json.dumps({'token':'internal-test-secret','agent':sample['agent'],'body_epoch':sample['body_epoch']}))
                    connection.send(json.dumps(sample))
                time.sleep(.12)
                while True:
                    try:first.recv(timeout=.01)
                    except TimeoutError:break
                for index in range(20):
                    samples[1]['tick']+=1;second.send(json.dumps(samples[1]));time.sleep(.01)
                received=0
                while True:
                    try:first.recv(timeout=.02);received+=1
                    except TimeoutError:break
                self.assertLessEqual(received,5,'Unrelated telemetry amplified private grant sends')
        finally:
            server.shutdown();server.socket.close();thread.join(3);fixture.tearDown()

    def test_stop_and_policy_revocation_preserve_short_grant_deadline(self):
        fixture=fixtures.GatewayTests();fixture.setUp();fixture.g.clock=time.monotonic
        sample=fixtures.frame(tick=101)
        sample.update(body_epoch='epoch',control_protocol=2,raw_capabilities=['look_at'],action_results=[])
        fixture.g.frame(sample);fixture.lease()
        streaming=fixtures.module('scru_streaming_policy','agent-gateway/streaming.py')
        server=streaming.make_server(fixture.g,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='ws://127.0.0.1:'+str(server.socket.getsockname()[1])+'/internal/body'
        try:
            with connect(url,proxy=None,close_timeout=.2) as body:
                body.send(json.dumps({'token':'internal-test-secret','agent':'Forge','body_epoch':'epoch'}))
                body.send(json.dumps(sample))
                grant=json.loads(body.recv(timeout=2))['action'];old=grant['lease_id']
                self.assertIsNotNone(old)
                started=time.monotonic();fixture.call('DELETE','/v1/goal')
                while grant.get('lease_id')==old:grant=json.loads(body.recv(timeout=1))['action']
                self.assertIsNotNone(grant['lease_id']);self.assertEqual([],grant['commands'])
                self.assertLess(time.monotonic()-started,.5)
                # A database-wide policy change has no frame/notification; heartbeat still rechecks authority.
                with fixture.g.changed:
                    digest=fixture.g.active('Forge')['token_hash']
                    fixture.g.db.execute('UPDATE tokens SET enabled=0 WHERE hash=?',(digest,));fixture.g.db.commit()
                started=time.monotonic()
                while grant.get('lease_id') is not None:grant=json.loads(body.recv(timeout=1))['action']
                self.assertLess(time.monotonic()-started,.5);self.assertIsNone(fixture.g.active('Forge'))
        finally:
            server.shutdown();server.socket.close();thread.join(3);fixture.tearDown()

    def test_malformed_primitive_types_match_http_and_websocket_400(self):
        import urllib.request,urllib.error
        fixture=fixtures.GatewayTests();fixture.setUp()
        sample=fixtures.frame(tick=101)
        sample.update(body_epoch='epoch',control_protocol=2,raw_capabilities=sorted(fixtures.gateway.PRIMITIVES),action_results=[])
        fixture.g.frame(sample);lease=fixture.lease()
        streaming=fixtures.module('scru_streaming_validation','agent-gateway/streaming.py')
        websocket=streaming.make_server(fixture.g,port=0)
        http=fixtures.gateway.Server(('127.0.0.1',0),fixture.g)
        threads=[threading.Thread(target=server.serve_forever,daemon=True) for server in (websocket,http)]
        for thread in threads:thread.start()
        base=dict(id='invalid_action_0001',body_epoch='epoch')
        bodies=[dict(base,op='use_item',hand=[]),dict(base,op='query_inventory',inventory=[],slot=0),
                dict(base,op='move_item',session_id='session',revision=0,count=1,
                     **{'from':{'inventory':[],'slot':0},'to':{'inventory':'player','slot':1}}),None]
        try:
            with connect('ws://127.0.0.1:'+str(websocket.socket.getsockname()[1])+'/v1/events',proxy=None,close_timeout=.2) as connection:
                connection.send(json.dumps({'token':fixture.token,'agent':'Forge'}))
                for index,body in enumerate(bodies):
                    with fixture.g.changed:fixture.now+=.2
                    rid='validation_'+str(index)
                    connection.send(json.dumps({'request_id':rid,'method':'POST','path':'/v1/actions','lease_id':lease['lease_id'],'body':body}))
                    while True:
                        result=json.loads(connection.recv(timeout=2))
                        if result.get('request_id')==rid:break
                    self.assertEqual((400,'invalid_request'),(result['status'],result['error']))
                    with fixture.g.changed:fixture.now+=.2
                    request=urllib.request.Request('http://127.0.0.1:'+str(http.server_address[1])+'/v1/actions',
                        data=json.dumps(body).encode(),headers={**fixture.h,'Content-Type':'application/json'},method='POST')
                    with self.assertRaises(urllib.error.HTTPError) as raised:urllib.request.urlopen(request,timeout=2)
                    self.assertEqual(400,raised.exception.code)
                    self.assertEqual('invalid_request',json.load(raised.exception)['error'])
                self.assertEqual({},fixture.g.actions.get('Forge',{}))
        finally:
            websocket.shutdown();websocket.socket.close();http.shutdown();http.server_close()
            for thread in threads:thread.join(3)
            fixture.tearDown()

    def test_protocol2_sdk_handles_async_observations_and_reconnect(self):
        import asyncio
        fixture=fixtures.GatewayTests();fixture.setUp();fixture.g.clock=time.monotonic
        streaming=fixtures.module('scru_streaming_v2','agent-gateway/streaming.py')
        server=streaming.make_server(fixture.g,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='127.0.0.1:'+str(server.socket.getsockname()[1])
        sys.path.insert(0,str(fixtures.ROOT/'sdk'))
        from scru_minecraft import AgentClient
        sample=fixtures.frame(tick=101)
        sample.update(body_epoch='epoch2',control_protocol=2,raw_capabilities=sorted(fixtures.gateway.PRIMITIVES),
                      action_results=[],control_transport='websocket')
        fixture.g.frame(sample)
        ended=threading.Event();received=[]
        def java():
            try:
                with connect('ws://'+base+'/internal/body',proxy=None) as body:
                    body.send(json.dumps({'token':'internal-test-secret','agent':'Forge','body_epoch':'epoch2'}))
                    body.send(json.dumps(sample))
                    while not ended.is_set():
                        grant=json.loads(body.recv(timeout=2))['action']
                        commands=grant.get('commands',[])
                        if commands:
                            received.extend(commands)
                            sample['tick']+=1
                            sample['action_results']=[dict(id=r['id'],state='done',body_epoch='epoch2',reason='fixture_executed') for r in commands]
                            body.send(json.dumps(sample))
            except (ConnectionClosed,TimeoutError):pass
        worker=threading.Thread(target=java,daemon=True);worker.start()
        client=AgentClient('http://'+base,fixture.token,'Forge',allow_local_http=True)
        try:
            with client.realtime() as stream:
                move=stream.move_to(1,64,0);look=stream.look_at(1,65,0)
                self.assertEqual('done',move.result(3)['state']);self.assertEqual('done',look.result(3)['state'])
                before=len(received)
                stream.reconnect(initial_delay=.01)
                self.assertEqual('done',stream.reconciled[move.id]['state'])
                self.assertEqual(before,len(received),'Reconnect replayed a mutation')
                self.assertTrue(stream.diagnostics()['connected'])
                event=next(stream.observations());self.assertTrue(event.resync)
            async def exercise():
                async with client.async_realtime() as stream:
                    action=await stream.select_slot(1)
                    self.assertEqual('done',(await action.result(3))['state'])
                    event=await anext(stream.observations())
                    self.assertGreater(event.sequence,0)
            asyncio.run(exercise())
        finally:
            ended.set();server.shutdown();server.socket.close();thread.join(3);worker.join(3);fixture.tearDown()

    def test_bidirectional_sdk_body_bridge_and_disconnect_release(self):
        fixture=fixtures.GatewayTests();fixture.setUp()
        streaming=fixtures.module('scru_streaming','agent-gateway/streaming.py')
        server=streaming.make_server(fixture.g,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='127.0.0.1:'+str(server.socket.getsockname()[1])
        sys.path.insert(0,str(fixtures.ROOT/'sdk'))
        from scru_minecraft import AgentClient
        sample=fixtures.frame(tick=101)
        sample.update(body_epoch='epoch1',raw_capabilities=['move_to','look_at','stop'],action_results=[],control_transport='websocket')
        try:
            with connect('ws://'+base+'/internal/body',proxy=None) as body:
                body.send(json.dumps({'token':'internal-test-secret','agent':'Forge','body_epoch':'epoch1'}))
                body.send(json.dumps(sample))
                deadline=time.monotonic()+3
                while fixture.g.frames['Forge'].get('body_epoch')!='epoch1':
                    if time.monotonic()>deadline:self.fail('body frame not received')
                    time.sleep(.01)
                client=AgentClient('http://'+base,fixture.token,'Forge',allow_local_http=True)
                with client.realtime() as stream:
                    fixture.now+=.1
                    accepted=stream.move_to(3,64,0)
                    self.assertEqual(accepted['state'],'accepted')
                    # No second observation is necessary to push the command to Java.
                    while True:
                        grant=json.loads(body.recv(timeout=3))['action']
                        if grant['kind']=='control':break
                    self.assertEqual(grant['id'],accepted['id'])
                    self.assertEqual(grant['valid_for_ticks'],4)
                    sample.update(tick=102,partial=True,action_results=[dict(id=accepted['id'],state='done')])
                    sample.pop('walkable');sample.pop('blocks')
                    body.send(json.dumps(sample))
                    self.assertEqual(stream.wait_action(accepted['id'],timeout=3)['state'],'done')
                    self.assertTrue(stream.observe()['walkable'])
                    fixture.now+=.1
                    stream.stop()
                    # Abrupt public disconnect must revoke the lease, without waiting 30 seconds.
                    stream.connection.close()
                    deadline=time.monotonic()+3
                    while fixture.g.active('Forge'):
                        if time.monotonic()>deadline:self.fail('disconnected stream kept its lease')
                        time.sleep(.01)
            with connect('ws://'+base+'/internal/body',proxy=None) as body:
                body.send(json.dumps({'token':fixture.token,'agent':'Forge','body_epoch':'epoch1'}))
                with self.assertRaises(ConnectionClosed):body.recv(timeout=3)
        finally:
            server.shutdown();thread.join(timeout=3);fixture.tearDown()

    def test_partial_frames_never_carry_terrain_across_body_or_dimension(self):
        fixture=fixtures.GatewayTests();fixture.setUp()
        try:
            sample=fixtures.frame(tick=101);sample['body_epoch']='epoch1'
            fixture.g.frame(sample)
            partial=dict(agent='Forge',tick=102,body_epoch='epoch1',partial=True,dimension=sample['dimension'])
            fixture.g.frame(partial)
            self.assertTrue(fixture.g.frames['Forge']['walkable'])
            partial.update(tick=103,dimension='minecraft:the_nether')
            fixture.g.frame(partial)
            self.assertNotIn('walkable',fixture.g.frames['Forge'])
            fixture.g.frame(sample)
            partial.update(tick=101,body_epoch='epoch2',dimension=sample['dimension'])
            old_id=fixture.g.frames['Forge']['id']
            fixture.g.frame(partial)
            self.assertNotIn('walkable',fixture.g.frames['Forge'])
            self.assertNotEqual(old_id,fixture.g.frames['Forge']['id'])
        finally:fixture.tearDown()

    def test_push_authorization_latest_frame_and_revocation(self):
        fixture=fixtures.GatewayTests();fixture.setUp()
        streaming=fixtures.module('scru_streaming','agent-gateway/streaming.py')
        server=streaming.make_server(fixture.g,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='ws://127.0.0.1:'+str(server.socket.getsockname()[1])+'/v1/events'
        try:
            with connect(url,proxy=None) as client:
                client.send(json.dumps({'token':fixture.token,'agent':'Forge'}))
                first=json.loads(client.recv(timeout=3))
                self.assertTrue(first['resync']);self.assertEqual(first['sequence'],1)
                with fixture.g.lock:fixture.g.frame(fixtures.frame(tick=120))
                second=json.loads(client.recv(timeout=3))
                self.assertEqual(second['observation']['tick'],120)
                self.assertEqual(second['sequence'],2)
                fixture.members.clear()
                with self.assertRaises(ConnectionClosed):client.recv(timeout=3)
            with connect(url,proxy=None) as client:
                client.send(json.dumps({'token':'not-a-valid-token','agent':'Forge'}))
                with self.assertRaises(ConnectionClosed):client.recv(timeout=3)
        finally:
            server.shutdown();thread.join(timeout=3);fixture.tearDown()
