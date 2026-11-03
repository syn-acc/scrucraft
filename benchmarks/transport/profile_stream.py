"""Synthetic transport experiment only; not Minecraft latency acceptance."""
import argparse, concurrent.futures, importlib.util, json, pathlib, sys, threading, time
from collections import OrderedDict

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'sdk')]
import test_controller_gateway as fixtures
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed
from scru_minecraft import AgentClient

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def run(directory,seconds,history):
    fixtures.gateway=module('profile_gateway',directory/'gateway.py')
    streaming=module('profile_streaming',directory/'streaming.py')
    f=fixtures.GatewayTests();f.setUp();g=f.g
    for i in range(1,10):
        f.now+=6;g.handle('POST','/v1/agents',f.headers,{'name':'Load'+str(i),'area':fixtures.AREA})
    g.clock=time.monotonic
    names=['Forge']+['Load'+str(i) for i in range(1,10)]
    samples=[]
    for i,name in enumerate(names):
        sample=fixtures.frame(name);sample.update(body_epoch='epoch_'+name,control_protocol=2,raw_capabilities=['look_at'])
        sample['action_results']=[dict(id='prefill_'+str(n).zfill(24),state='done',reason='oriented',body_epoch=sample['body_epoch'],tick=n) for n in range(history)]
        g.frame(sample)
        for row in sample['action_results']:row['details_retained_by_gateway']=True
        sample['tick']+=1;g.frame(sample);samples.append(sample)
    server=streaming.make_server(g,port=0);base='127.0.0.1:'+str(server.socket.getsockname()[1])
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    end=threading.Event();metrics={'grant_bytes':0,'grants':0,'wait_wakeups':0};errors=[];streams=[]
    def instrument(condition):
        original_wait=condition.wait
        def wait(*args,**kwargs):
            result=original_wait(*args,**kwargs);metrics['wait_wakeups']+=1;return result
        condition.wait=wait
    for condition in [g.changed]+list(getattr(g,'body_conditions',{}).values()):instrument(condition)
    def native(sample):
        rows=OrderedDict((r['id'],r) for r in sample['action_results'])
        try:
            with connect('ws://'+base+'/internal/body',proxy=None,close_timeout=.2) as ws:
                ws.send(json.dumps({'agent':sample['agent'],'body_epoch':sample['body_epoch'],'token':'internal-test-secret'}))
                next_frame=0
                while not end.is_set():
                    now=time.monotonic()
                    if now>=next_frame:
                        sample['tick']+=1;sample['action_results']=list(rows.values())[-64:]
                        ws.send(json.dumps(sample));next_frame=now+.05
                    try:message=ws.recv(timeout=max(.001,next_frame-time.monotonic()))
                    except TimeoutError:continue
                    metrics['grants']+=1;metrics['grant_bytes']+=len(message)
                    grant=json.loads(message)['action']
                    for rid in grant.get('acknowledged_results',[]):
                        if rid in rows:rows[rid]['details_retained_by_gateway']=True
                    for command in grant.get('commands',[]):
                        rows[command['id']]=dict(id=command['id'],body_epoch=sample['body_epoch'],state='done',reason='oriented',tick=sample['tick'])
                    while len(rows)>512:rows.popitem(last=False)
        except Exception as error:
            if not end.is_set():errors.append('native:'+type(error).__name__)
    workers=[threading.Thread(target=native,args=(sample,),daemon=True) for sample in samples]
    for worker in workers:worker.start()
    values=[]
    try:
        for name in names:
            with g.changed:token=g.issue('ClosedDoor','agent',name)
            streams.append(AgentClient('http://'+base,token,name,allow_local_http=True,timeout=3).realtime().connect())
        metrics.update(grant_bytes=0,grants=0,wait_wakeups=0)
        began=time.monotonic();cpu=time.process_time()
        def drive(stream):
            while time.monotonic()-began<seconds and not end.is_set():
                start=time.monotonic()
                try:stream.look_at(2,65,2).result(3);values.append((time.monotonic()-start)*1000)
                except Exception as error:errors.append('sdk:'+type(error).__name__);end.set();return
                end.wait(max(0,.2-(time.monotonic()-start)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:list(executor.map(drive,streams))
        elapsed=time.monotonic()-began;cpu=time.process_time()-cpu
        values.sort()
        report=dict(experiment='synthetic_python_transport_not_minecraft',seconds=round(elapsed,3),cpu_seconds=round(cpu,3),history_per_body=history,actions=len(values),errors=errors,
                    completion_ms={k:round(values[min(len(values)-1,int(q*len(values)))],3) for k,q in [('p50',.5),('p95',.95),('max',1)]} if values else {},**metrics)
        return report
    finally:
        for stream in streams:
            try:stream.close()
            except Exception:pass
        end.set()
        for worker in workers:worker.join(3)
        server.shutdown();server.socket.close();thread.join(3);f.tearDown()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=pathlib.Path,default=ROOT/'agent-gateway');parser.add_argument('--seconds',type=int,default=8);parser.add_argument('--history',type=int,default=350)
    args=parser.parse_args();print(json.dumps(run(args.source,args.seconds,args.history),indent=2))
