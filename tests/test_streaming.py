import importlib.util
import json
import pathlib
import threading
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
