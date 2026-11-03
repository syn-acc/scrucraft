"""Run after Gradle testClasses, with the compiled main/test classes and Gson on --classpath."""
import argparse
import json
import subprocess
import threading
import time
from websockets.sync.server import serve
from websockets.exceptions import ConnectionClosed

parser=argparse.ArgumentParser();parser.add_argument('--classpath',required=True);args=parser.parse_args()
failures=[]
connections = 0
connection_lock = threading.Lock()

def grant(action, issued=None, observed_tick=-1):
    issued = time.time_ns() // 1_000_000 if issued is None else issued
    return json.dumps({'type': 'control', 'issued_at_ms': issued, 'expires_at_ms': issued + 200,
                       'observed_tick': observed_tick, 'action': action})
def peer(connection):
    global connections
    try:
        auth=json.loads(connection.recv(timeout=3))
        assert auth=={'agent':'Probe','body_epoch':'probe-epoch','token':'test-secret'}
        with connection_lock:
            connections += 1
            attempt = connections
        if attempt == 2:
            frame=json.loads(connection.recv(timeout=3))
            assert frame['tick']==5, 'Old queued observation replayed after reconnect'
            connection.send(grant({'id':'probe-reconnected','body_epoch':'probe-epoch','kind':'controls','commands':[]}, observed_tick=5))
            try:
                for _ in connection:pass
            except ConnectionClosed:pass
            return
        assert attempt == 1, 'Unexpected repeated reconnect'
        frame=json.loads(connection.recv(timeout=3));assert frame['agent']=='Probe' and frame['tick']==1
        connection.send(grant({'id':'stale-first','body_epoch':'probe-epoch','kind':'controls','commands':[]},time.time_ns()//1_000_000-500))
        time.sleep(.05)
        connection.send(grant({'id':'probe-action','body_epoch':'probe-epoch','kind':'controls','commands':[]}, observed_tick=1))
        assert json.loads(connection.recv(timeout=3))['tick']==2
        queued = grant({'id':'stale-delayed','body_epoch':'probe-epoch','kind':'controls','commands':[]}, observed_tick=2)
        time.sleep(.25)
        connection.send(queued)
        assert json.loads(connection.recv(timeout=3))['tick']==3
        connection.send(grant({'id':'probe-stop','body_epoch':'probe-epoch','kind':'controls','lease_id':None,'commands':[]}, observed_tick=3))
        assert json.loads(connection.recv(timeout=3))['tick']==4
        # Keep the socket and grant heartbeat alive but withhold frame4's ACK.
        # The two-second native watchdog must close it and reset the pending slot.
        try:
            while True:
                connection.send(grant({'id':'probe-stop','body_epoch':'probe-epoch','kind':'controls','lease_id':None,'commands':[]}, observed_tick=3))
                time.sleep(.05)
        except ConnectionClosed:pass
    except Exception as error:failures.append(str(error))
server=serve(peer,'127.0.0.1',0,compression=None)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    subprocess.run(['java','-cp',args.classpath,'gl.syn.minecraft.BodyStreamProbe',
                    'ws://127.0.0.1:'+str(server.socket.getsockname()[1])+'/internal/body'],check=True,timeout=25)
    assert connections == 2, connections
    if failures:raise AssertionError(failures)
finally:server.shutdown();thread.join(timeout=3)
