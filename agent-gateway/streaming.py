"""Authenticated latest-snapshot push; slow readers never queue unbounded terrain frames."""
import json
import threading
from websockets.sync.server import serve
from websockets.protocol import State


def make_server(gateway, host='127.0.0.1', port=8769):
    slots=threading.BoundedSemaphore(24)
    def handler(connection):
        if not slots.acquire(blocking=False):
            connection.close(1013,'stream_capacity');return
        try:
            if connection.request.path!='/v1/events':
                connection.close(1008,'not_found');return
            # First-message authentication keeps bearer credentials out of URL/access logs.
            auth=json.loads(connection.recv(timeout=5))
            if not isinstance(auth,dict) or not isinstance(auth.get('token'),str):
                connection.close(1008,'unauthorized');return
            name=auth.get('agent');previous=None;sequence=0
            while connection.state is State.OPEN:
                with gateway.changed:
                    principal=gateway.authenticate('Bearer '+auth['token'])
                    body=gateway.body(name,principal)
                    if body['data'].get('removed'):
                        connection.close(1008,'agent_removed');return
                    frame=gateway.snapshot(body)
                    frame_id=frame['id']
                    event=None
                    if frame_id!=previous:
                        sequence+=1
                        event={'type':'snapshot','sequence':sequence,'resync':previous is None,'observation':frame}
                        previous=frame_id
                    if event is None:
                        gateway.changed.wait(timeout=.25)
                        continue
                # Send outside the gateway lock; TCP backpressure cannot block controller frames.
                connection.send(json.dumps(event,allow_nan=False))
        except Exception:
            connection.close(1008,'stream_closed_reauthenticate_or_refresh')
        finally:
            slots.release()
    return serve(handler,host,port,max_size=16384,max_queue=4,open_timeout=5,
                 close_timeout=2,ping_interval=10,ping_timeout=10,compression=None,server_header=None)
