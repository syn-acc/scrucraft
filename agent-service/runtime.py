"""Stable HTTP host: swap controller methods while retaining tasks, budget and workers.

SIGHUP selects root-owned immutable code. Candidate import and smoke validation
run off the request path; the atomic swap never waits for model HTTP responses.
"""
from __future__ import annotations
import hashlib,hmac,importlib.util,json,os,pathlib,re,signal,tempfile,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

DATA=pathlib.Path('/data/minecraft-syn-smp/agent-service')
RELEASES=pathlib.Path('/usr/local/lib/minecraft-syn-smp/agent-releases')
ACTIONS={'idle','move','mine','clear_site','craft_planks','craft','place','place_workstation','furnace_insert','furnace_extract','eat','drink','attack','interact','use','control'}

def load_candidate(releases,data):
    digest=json.loads((releases/'current.json').read_text())['sha512']
    if not re.fullmatch('[a-f0-9]{128}',digest):raise ValueError('invalid_release_digest')
    path=releases/digest/'service.py'
    for p in (releases,releases/digest,path,releases/'current.json'):
        info=p.lstat()
        if info.st_uid!=0 or info.st_mode&0o022 or p.is_symlink():raise ValueError('release_permissions')
    if hashlib.sha512(path.read_bytes()).hexdigest()!=digest:raise ValueError('release_checksum')
    spec=importlib.util.spec_from_file_location('syn_release_'+digest,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if getattr(module,'HOT_STATE_VERSION',None)!=1:raise ValueError('incompatible_state_version')
    # Execute a real controller decision against isolated state, with inference off.
    with tempfile.TemporaryDirectory(prefix='.validate-',dir=data) as temporary:
        module.ROOT=pathlib.Path(temporary);probe=module.Controller();probe.key=''
        try:
            frame={'schema':1,'agent':'Syn_Check','job':'builder','tick':1,'position':[.5,64,.5],'health':20,'food':20,'thirst':20,'temperature':20,'night':False,'sheltered':False,'inventory':[],'entities':[],'blocks':[],'walkable':[{'pos':[0,64,0]},{'pos':[1,64,0]}]}
            result=probe.decide(frame);module.REQUIRED_STATE_FIELDS=frozenset(probe.__dict__)
            if result.get('schema')!=1 or result['action'].get('kind') not in ACTIONS:raise ValueError('decision_contract')
        finally:probe.pool.shutdown(wait=True);probe.db.close()
    module.ROOT=data
    return digest,module

class Runtime:
    def __init__(self,releases=RELEASES,data=DATA):
        self.releases=releases;self.data=data;self.lock=threading.RLock()
        self.digest,self.module=load_candidate(releases,data)
        self.controller=self.module.Controller();self.reloads=0;self.error=None;self.changed=time.time()
    def reload(self):
        try:
            digest,module=load_candidate(self.releases,self.data)
            with self.lock,self.controller.lock:
                missing=getattr(module,'REQUIRED_STATE_FIELDS',set())-self.controller.__dict__.keys()
                defaults=getattr(module,'HOT_DEFAULTS',{})
                if missing-defaults.keys():raise ValueError('incompatible_live_fields:'+','.join(sorted(missing-defaults.keys())))
                additions={k:json.loads(json.dumps(defaults[k],allow_nan=False)) for k in missing}
                # The dictionary, SQLite connection, mutex and executor survive.
                # Already-running inference retains its original method globals.
                self.controller.__class__=module.Controller
                self.controller.__dict__.update(additions)
                self.digest=digest;self.module=module;self.reloads+=1;self.error=None;self.changed=time.time()
            return True
        except Exception as exc:
            with self.lock:self.error=type(exc).__name__+':'+str(exc)[:160];self.changed=time.time()
            return False
    def health(self):
        with self.lock:
            result=self.controller.health()
            result['runtime']={'pid':os.getpid(),'sha512':self.digest,'reloads':self.reloads,'last_error':self.error,'changed_at':self.changed}
            return result
    def decide(self,o):
        with self.lock:return self.controller.decide(o)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,value):
        data=json.dumps(value,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):self.send(200,runtime.health()) if self.path=='/health' else self.send(404,{'error':'not_found'})
    def do_POST(self):
        if self.path!='/v1/decide':return self.send(404,{'error':'not_found'})
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+runtime.controller.token):return self.send(401,{'error':'unauthorized'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 1<=size<=262144:return self.send(413,{'error':'size'})
            o=json.loads(self.rfile.read(size),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite')))
            if o.get('schema')!=1 or not isinstance(o.get('agent'),str) or not re.fullmatch(r'[A-Za-z0-9_]{1,16}',o['agent']) or type(o['tick']) is not int or len(o['position'])!=3:raise ValueError('schema')
            self.send(200,runtime.decide(o))
        except (ValueError,KeyError,TypeError):self.send(400,{'error':'invalid_observation'})

if __name__=='__main__':
    runtime=Runtime();requested=threading.Event()
    signal.signal(signal.SIGHUP,lambda *_:requested.set())
    def reloader():
        while True:
            requested.wait();requested.clear();runtime.reload()
    threading.Thread(target=reloader,daemon=True,name='controller-reloader').start()
    ThreadingHTTPServer(('127.0.0.1',8767),Handler).serve_forever()
