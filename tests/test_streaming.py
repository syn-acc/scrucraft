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
