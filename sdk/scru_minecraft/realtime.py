"""Persistent commands and latest-state observations; no HTTP polling or command replay."""
import json
import threading
import time
import uuid
from . import GatewayError


class RealtimeClient:
    def __init__(self, client):
        self.client=client
        self.changed=threading.Condition()
        self.send_lock=threading.Lock()
        self.pending={}
        self.observation=None
        self.lease=None
        self.connection=None
        self.error=None
        self.stopped=threading.Event()
        self.reader=None
        self.renewal=None
        self.next_request=0
        self.last_timing={}

    def connect(self):
        from websockets.sync.client import connect
        if not self.client.agent:raise ValueError('Select an agent name')
        if self.connection is not None:raise ValueError('Already connected; create a new stream to reconnect')
        scheme='wss://' if self.client.url.startswith('https://') else 'ws://'
        url=scheme+self.client.url.split('://',1)[1]+'/v1/events'
        self.connection=connect(url,max_size=1048576,max_queue=4,compression=None,
                                open_timeout=self.client.timeout,close_timeout=2,proxy=None)
        self.connection.send(json.dumps({'token':self.client.token,'agent':self.client.agent}))
        self.reader=threading.Thread(target=self._read,daemon=True,name='scru-realtime-reader')
        self.reader.start()
        try:
            self.observe()
            self.lease=self.request('POST','/v1/lease')['lease_id']
            self.renewal=threading.Thread(target=self._renew,daemon=True,name='scru-realtime-lease')
            self.renewal.start()
            return self
        except Exception:
            self.close();raise

    def _read(self):
        try:
            for message in self.connection:
                event=json.loads(message)
                with self.changed:
                    if event.get('type')=='snapshot':
                        value=event['observation']
                        previous=self.observation or {}
                        if event.get('resync') or previous.get('body_epoch')!=value.get('body_epoch') or previous.get('dimension')!=value.get('dimension'):
                            previous={}
                        self.observation={**previous,**value}
                    elif event.get('type')=='response' and event.get('request_id') in self.pending:
                        self.pending[event['request_id']]=event
                    self.changed.notify_all()
        except Exception:
            pass
        finally:
            with self.changed:
                self.error=ConnectionError('Stream disconnected; commands are never automatically replayed')
                self.stopped.set();self.changed.notify_all()

    def request(self,method,path,body=None):
        # Serialize outgoing requests, with only a 6 ms flood-control floor, not the HTTP SDK delay.
        with self.send_lock:
            delay=self.next_request-time.monotonic()
            if delay>0:self.stopped.wait(delay)
            rid=uuid.uuid4().hex
            with self.changed:
                if self.error:raise self.error
                if self.stopped.is_set():raise ConnectionError('Stream closed')
                self.pending[rid]=None
            started=time.perf_counter_ns()
            try:
                self.connection.send(json.dumps({'request_id':rid,'method':method,'path':path,
                    'lease_id':self.lease or '', 'body':body or {}},allow_nan=False))
                with self.changed:
                    arrived=self.changed.wait_for(lambda:self.pending[rid] is not None or self.error, self.client.timeout)
                    if self.error:raise self.error
                    if not arrived:
                        self.connection.close()
                        raise TimeoutError('Command acknowledgement unknown; reconnect and inspect results before retrying')
                    response=self.pending[rid]
                    self.last_timing={'round_trip_ms':(time.perf_counter_ns()-started)/1e6,
                                      'gateway_processing_us':response.get('gateway_processing_us')}
                    if response['status']!=200:raise GatewayError(response['status'],response['error'])
                    return response['result']
            finally:
                with self.changed:self.pending.pop(rid,None)
                self.next_request=time.monotonic()+.006

    def observe(self):
        with self.changed:
            if not self.changed.wait_for(lambda:self.observation is not None or self.error,self.client.timeout):
                raise TimeoutError('No body snapshot received')
            if self.error:raise self.error
            return dict(self.observation)

    def action(self,op,*,target=None,ttl_seconds=30,request_id=None):
        value={'id':request_id or uuid.uuid4().hex,'op':op,'body_epoch':self.observe().get('body_epoch'),
               'ttl_seconds':ttl_seconds}
        if target is not None:value['target']=list(target)
        return self.request('POST','/v1/actions',value)

    def move_to(self,x,y,z,**kwargs):return self.action('move_to',target=[x,y,z],**kwargs)
    def look_at(self,x,y,z,**kwargs):return self.action('look_at',target=[x,y,z],**kwargs)
    def stop(self):return self.request('DELETE','/v1/goal')

    def wait_action(self,action_id,timeout=30):
        def terminal():
            rows=(self.observation or {}).get('action_results',[])
            return next((r for r in rows if r['id']==action_id and r['state'] in {'done','failed','cancelled'}),None)
        with self.changed:
            if not self.changed.wait_for(lambda:terminal() or self.error,timeout):raise TimeoutError('Action still pending')
            if self.error:raise self.error
            return dict(terminal())

    def _renew(self):
        while not self.stopped.wait(8):
            try:self.request('PUT','/v1/lease')
            except Exception:
                self.connection.close();return

    def close(self):
        try:
            if self.lease and not self.stopped.is_set():self.request('DELETE','/v1/lease')
        finally:
            self.stopped.set()
            if self.connection:self.connection.close()
            for thread in (self.reader,self.renewal):
                if thread and thread is not threading.current_thread():thread.join(timeout=2)
            self.lease=None

    def __enter__(self):return self.connect()
    def __exit__(self,kind,value,tb):self.close()
