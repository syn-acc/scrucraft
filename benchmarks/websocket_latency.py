"""Loopback transport benchmark with a simulated 20 Hz body, NOT a live-game measurement."""
import json
import pathlib
import statistics
import sys
import threading
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'sdk')]
import test_controller_gateway as fixtures
from scru_minecraft import AgentClient
from websockets.sync.client import connect


def run(count=100):
    fixture=fixtures.GatewayTests();fixture.setUp();fixture.g.clock=time.time
    streaming=fixtures.module('scru_benchmark_stream','agent-gateway/streaming.py')
    server=streaming.make_server(fixture.g,port=0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='127.0.0.1:'+str(server.socket.getsockname()[1])
    stopped=threading.Event();ready=threading.Event();received={};latest={};results={}
    guard=threading.Lock();errors=[]
    def simulate():
        try:
            with connect('ws://'+base+'/internal/body',proxy=None) as body:
                body.send(json.dumps({'token':'internal-test-secret','agent':'Forge','body_epoch':'benchmark'}))
                def read():
                    try:
                        for message in body:
                            grant=json.loads(message)['action']
                            with guard:
                                latest.clear();latest.update(grant)
                                if grant['kind']=='control':received.setdefault(grant['id'],time.perf_counter_ns())
                    except Exception:pass
                reader=threading.Thread(target=read,daemon=True);reader.start()
                tick=101;deadline=time.monotonic()
                while not stopped.is_set():
                    with guard:
                        if latest.get('kind')=='control':
                            results[latest['id']]={'id':latest['id'],'state':'done','body_epoch':'benchmark'}
                    sample=fixtures.frame(tick=tick)
                    sample.update(body_epoch='benchmark',raw_capabilities=['look_at','move_to','stop'],
                                  action_results=list(results.values())[-64:],control_transport='websocket')
                    body.send(json.dumps(sample));ready.set();tick+=1
                    deadline+=.05;stopped.wait(max(0,deadline-time.monotonic()))
                body.close();reader.join(timeout=2)
        except Exception as error:errors.append(str(error));ready.set()
    simulator=threading.Thread(target=simulate,daemon=True);simulator.start()
    receipts=[];dispatch=[];completion=[]
    try:
        if not ready.wait(3):raise RuntimeError('simulated body startup timed out')
        deadline=time.monotonic()+3
        while fixture.g.frames['Forge'].get('body_epoch')!='benchmark':
            if errors or time.monotonic()>deadline:raise RuntimeError('simulated body did not connect')
            time.sleep(.005)
        client=AgentClient('http://'+base,fixture.token,'Forge',allow_local_http=True)
        with client.realtime() as stream:
            for _ in range(count):
                time.sleep(.061)  # Keep requests below the 20 commands/sec body cap.
                began=time.perf_counter_ns()
                accepted=stream.look_at(3,64,0)
                receipts.append(stream.last_timing['round_trip_ms'])
                stream.wait_action(accepted['id'],timeout=3)
                completion.append((time.perf_counter_ns()-began)/1e6)
                with guard:dispatch.append((received[accepted['id']]-began)/1e6)
        def percentiles(values):
            values=sorted(values)
            return {key:round(values[min(len(values)-1,int(len(values)*p))],3)
                    for key,p in [('p50',.50),('p95',.95),('p99',.99)]}
        return {'scenario':'loopback; simulated 20 Hz body; in-memory whitelist; no TLS or real game',
                'samples':count,'ack_ms':percentiles(receipts),'dispatch_ms':percentiles(dispatch),
                'simulated_completion_ms':percentiles(completion)}
    finally:
        stopped.set();simulator.join(timeout=3);server.shutdown();thread.join(timeout=3);fixture.tearDown()


if __name__=='__main__':print(json.dumps(run(),indent=2))
