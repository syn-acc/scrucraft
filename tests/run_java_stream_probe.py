"""Run after Gradle testClasses, with the compiled main/test classes and Gson on --classpath."""
import argparse
import json
import subprocess
import threading
from websockets.sync.server import serve
from websockets.exceptions import ConnectionClosed

parser=argparse.ArgumentParser();parser.add_argument('--classpath',required=True);args=parser.parse_args()
failures=[]
def peer(connection):
    try:
        auth=json.loads(connection.recv(timeout=3))
        assert auth=={'agent':'Probe','body_epoch':'probe-epoch','token':'test-secret'}
        frame=json.loads(connection.recv(timeout=3));assert frame['agent']=='Probe' and frame['tick']==1
        connection.send(json.dumps({'type':'control','action':{'id':'probe-action','body_epoch':'probe-epoch','kind':'control'}}))
        # Remain connected but stop renewing: the Java mailbox must expire independently.
        try:
            for _ in connection:pass
        except ConnectionClosed:pass
    except Exception as error:failures.append(str(error))
server=serve(peer,'127.0.0.1',0,compression=None)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    subprocess.run(['java','-cp',args.classpath,'gl.syn.minecraft.BodyStreamProbe',
                    'ws://127.0.0.1:'+str(server.socket.getsockname()[1])+'/internal/body'],check=True,timeout=15)
    if failures:raise AssertionError(failures)
finally:server.shutdown();thread.join(timeout=3)
