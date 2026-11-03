"""Persistent commands and latest-state observations; no HTTP polling or command replay."""
import json
import threading
import time
import uuid
import re
from . import GatewayError, PrimitiveMethods, ActionHandle, _match_action_epoch


class RealtimeClient(PrimitiveMethods):
    def __init__(self, client):
        self.client=client
        self.changed=threading.Condition()
        self.send_lock=threading.Lock()
        self.request_lock=threading.Lock()
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
        self.submitted={}
        self.reconciled={}
        self.received_at=None
        self.sequence=0
        self.snapshots=[]
        self.last_disconnect=None
        self.renewal_failure=None

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
        failure_type=None
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
                        self.received_at=time.monotonic()
                        self.sequence+=1
                        self.snapshots.append((self.sequence,dict(self.observation),bool(event.get('resync'))))
                        self.snapshots=self.snapshots[-64:]
                    elif event.get('type')=='response' and event.get('request_id') in self.pending:
                        self.pending[event['request_id']]=event
                    self.changed.notify_all()
        except Exception as error:
            failure_type=type(error).__name__
        finally:
            with self.changed:
                code=getattr(self.connection,'close_code',None)
                reason=getattr(self.connection,'close_reason',None)
                known={'','unauthorized','stream_capacity','not_found','stream_closed_reauthenticate_or_refresh','keepalive ping timeout'}
                safe_reason=reason if reason in known or isinstance(reason,str) and re.fullmatch(r'stream_error_[A-Za-z0-9_]{1,100}',reason) else 'unrecognized_close_reason' if reason else None
                if safe_reason and self.client.token in safe_reason:safe_reason='redacted_close_reason'
                self.last_disconnect={'close_code':code,'close_reason':safe_reason,'exception_type':failure_type,
                                      'renewal_failure':self.renewal_failure}
                self.error=ConnectionError('Stream disconnected '+json.dumps(self.last_disconnect,sort_keys=True)+'; commands are never automatically replayed')
                self.stopped.set();self.changed.notify_all()

    def request(self,method,path,body=None):
        # ACK ordering matters to the gateway's per-token pacing. Safety release bypasses
        # this lock (and the server rate limit), so it never waits behind an ordinary ACK.
        if (method,path) in {('DELETE','/v1/goal'),('DELETE','/v1/lease')}:
            return self._request(method,path,body)
        with self.request_lock:
            return self._request(method,path,body)

    def _request(self,method,path,body=None):
        rid=uuid.uuid4().hex
        with self.changed:
            if self.error:raise self.error
            if self.stopped.is_set():raise ConnectionError('Stream closed')
            self.pending[rid]=None
        started=time.perf_counter_ns()
        try:
            # Safety stop uses only this short send lock, never the ordinary request lock.
            with self.send_lock:
                while not self.stopped.is_set():
                    delay=self.next_request-time.monotonic()
                    if delay<=0:break
                    self.stopped.wait(delay)  # An in-flight ACK may move this deadline while we wait.
                if self.stopped.is_set():raise ConnectionError('Stream closed')
                self.connection.send(json.dumps({'request_id':rid,'method':method,'path':path,
                    'lease_id':self.lease or '', 'body':body or {}},allow_nan=False))
                self.next_request=time.monotonic()+.006
            with self.changed:
                arrived=self.changed.wait_for(lambda:self.pending[rid] is not None or self.error,self.client.timeout)
                if self.error:raise self.error
                if not arrived:
                    self.connection.close()
                    raise TimeoutError('Command acknowledgement unknown; reconnect and inspect results before retrying')
                response=self.pending[rid]
                self.next_request=max(self.next_request,time.monotonic()+.006)
                self.last_timing={'round_trip_ms':(time.perf_counter_ns()-started)/1e6,
                                  'gateway_processing_us':response.get('gateway_processing_us')}
                if response['status']!=200:raise GatewayError(response['status'],response['error'],response.get('retry_after'))
                return response['result']
        finally:
            with self.changed:self.pending.pop(rid,None)

    def observe(self):
        with self.changed:
            if not self.changed.wait_for(lambda:self.observation is not None or self.error,self.client.timeout):
                raise TimeoutError('No body snapshot received')
            if self.error:raise self.error
            return dict(self.observation)

    def action(self,op,*,target=None,ttl_seconds=30,request_id=None,**fields):
        value={'id':request_id or uuid.uuid4().hex,'op':op,'body_epoch':self.observe().get('body_epoch'),
               'ttl_seconds':ttl_seconds}
        if set(fields)&set(value):raise ValueError('Reserved action fields')
        value.update(fields)
        if target is not None:value['target']=list(target)
        self.submitted[value['id']]={'body_epoch':value['body_epoch'],
            'deadline':time.monotonic()+(ttl_seconds if type(ttl_seconds) is int and 1<=ttl_seconds<=30 else 30)}
        while len(self.submitted)>512:self.submitted.pop(next(iter(self.submitted)))
        return ActionHandle(self,self.request('POST','/v1/actions',value))

    def move_to(self,x,y,z,**kwargs):return self.action('move_to',target=[x,y,z],**kwargs)
    def look_at(self,x,y,z,**kwargs):return self.action('look_at',target=[x,y,z],**kwargs)
    def stop(self):return self.request('DELETE','/v1/goal')

    def wait_action(self,action_id,timeout=30,*,body_epoch=None):
        def cached():
            rows=(self.observation or {}).get('action_results',[])+list(self.reconciled.values())
            return next((r for r in rows if r['id']==action_id),None)
        def terminal(row):
            return row is not None and ((body_epoch is not None and row.get('body_epoch') not in (None,body_epoch))
                or row['state'] in {'done','failed','cancelled','unknown'} and not row.get('details_pending'))
        def authoritative():return _match_action_epoch(self.action_results(action_id)[0],body_epoch)
        deadline=time.monotonic()+timeout
        with self.changed:
            row=cached()
            submitted=self.submitted.get(action_id)
            query_missing=row is None and (not submitted or time.monotonic()>=submitted['deadline'])
        # New accepted work normally waits on push only. Old/unknown handles reconcile once,
        # and a final authoritative read distinguishes expired evidence from pending execution.
        if query_missing:
            result=authoritative()
            if terminal(result):return result
        with self.changed:
            self.changed.wait_for(lambda:terminal(cached()) or self.error,max(0,deadline-time.monotonic()))
            if self.error:raise self.error
            row=cached()
            result=dict(row) if terminal(row) else None
        if result is None or result.get('details_available') or (body_epoch is not None and result.get('body_epoch') not in (None,body_epoch)):
            result=authoritative()
        if terminal(result):return _match_action_epoch(result,body_epoch)
        raise TimeoutError('Action is still pending according to the gateway')

    def action_results(self,action_id=None):
        return self.request('GET','/v1/action-results',{'action_id':action_id} if action_id else None)['results']

    def reconnect(self,attempts=3,initial_delay=.1):
        """Explicit bounded reconnect. Reconcile IDs, never replay actions or resume a human stop."""
        if type(attempts) is not int or not 1<=attempts<=5:raise ValueError('attempts must be 1..5')
        if not 0<=initial_delay<=5:raise ValueError('initial_delay must be 0..5 seconds')
        from websockets.exceptions import WebSocketException
        outstanding=dict(self.submitted)
        try:self.close()
        except (OSError,GatewayError,TimeoutError):pass
        for attempt in range(attempts):
            self.__init__(self.client)
            try:
                self.connect()
                self.submitted=dict(outstanding)
                for rid in outstanding:
                    self.reconciled[rid]=self.action_results(rid)[0]
                return self
            except GatewayError as error:
                self.close()
                if error.status in {401,403,423}:raise
                if attempt==attempts-1:raise
            except (OSError,TimeoutError,WebSocketException):
                self.close()
                if attempt==attempts-1:raise
            time.sleep(min(2,initial_delay*2**attempt))

    def diagnostics(self):
        return {'connected':not self.stopped.is_set() and self.connection is not None,
                'observation_age_seconds':None if self.received_at is None else time.monotonic()-self.received_at,
                'pending_requests':len(self.pending),'sequence':self.sequence,
                'last_disconnect':self.last_disconnect,'renewal_failure':self.renewal_failure,**self.last_timing}

    def observations(self):
        """Yield typed latest-state events. Slow consumers receive a resync, never stale queued commands."""
        cursor=0
        while True:
            with self.changed:
                self.changed.wait_for(lambda:self.sequence>cursor or self.error or self.stopped.is_set())
                if self.error:raise self.error
                if self.stopped.is_set():return
                sequence,observation,resync=self.snapshots[-1]
                gap=cursor!=0 and sequence>cursor+1
                cursor=sequence
            yield SnapshotEvent(sequence,observation,resync or gap,gap)

    def chat_events(self):
        """Deduplicated public messages from bounded snapshots; gaps may omit older messages."""
        seen=[]
        for event in self.observations():
            for row in event.observation.get('public_chat',[]):
                if row.get('id') and row['id'] not in seen:
                    seen.append(row['id']);seen=seen[-512:]
                    yield PublicChatEvent(row['id'],row.get('speaker',''),row.get('text',''),row.get('at'),event.gap)

    def _renew(self):
        while not self.stopped.wait(8):
            try:self.request('PUT','/v1/lease')
            except Exception as error:
                self.renewal_failure={'exception_type':type(error).__name__}
                if isinstance(error,GatewayError):
                    self.renewal_failure['status']=error.status
                    self.renewal_failure['code']=error.code if isinstance(error.code,str) and re.fullmatch(r'[a-z_]{1,80}',error.code) else 'unrecognized_error'
                self.connection.close();return

    def close(self):
        from websockets.exceptions import ConnectionClosed
        try:
            if self.lease and not self.stopped.is_set():self.request('DELETE','/v1/lease')
        except (OSError,TimeoutError,ConnectionClosed):
            pass  # Closing the stream revokes its lease even if the release ACK was lost.
        except GatewayError as error:
            if error.status not in {401,403,409,423}:raise
        finally:
            self.stopped.set()
            if self.connection:self.connection.close()
            for thread in (self.reader,self.renewal):
                if thread and thread is not threading.current_thread():thread.join(timeout=2)
            self.lease=None

    def __enter__(self):return self.connect()
    def __exit__(self,kind,value,tb):self.close()


from dataclasses import dataclass

@dataclass(frozen=True)
class SnapshotEvent:
    sequence: int
    observation: dict
    resync: bool
    gap: bool = False


@dataclass(frozen=True)
class PublicChatEvent:
    id: str
    speaker: str
    text: str
    at: float | None
    gap: bool = False


class AsyncActionHandle:
    def __init__(self,handle):self.handle=handle
    @property
    def id(self):return self.handle.id
    def __getitem__(self,key):return self.handle[key]
    async def wait(self,timeout=30):
        import asyncio
        return await asyncio.to_thread(self.handle.wait,timeout)
    async def result(self,timeout=30):
        import asyncio
        return await asyncio.to_thread(self.handle.result,timeout)
    async def cancel(self):
        import asyncio
        return AsyncActionHandle(await asyncio.to_thread(self.handle.cancel))


class AsyncRealtimeClient:
    """Async facade over the same proven stream reader/lease machinery; no event-loop blocking I/O."""
    def __init__(self,client):self.sync=RealtimeClient(client)
    def __getattr__(self,name):
        value=getattr(self.sync,name)
        if not callable(value):return value
        async def invoke(*args,**kwargs):
            import asyncio
            result=await asyncio.to_thread(value,*args,**kwargs)
            return AsyncActionHandle(result) if isinstance(result,ActionHandle) else result
        return invoke
    async def observations(self):
        import asyncio
        events=self.sync.observations()
        sentinel=object()
        while True:
            event=await asyncio.to_thread(next,events,sentinel)
            if event is sentinel:return
            yield event
    async def chat_events(self):
        import asyncio
        events=self.sync.chat_events();sentinel=object()
        while True:
            event=await asyncio.to_thread(next,events,sentinel)
            if event is sentinel:return
            yield event
    async def __aenter__(self):
        import asyncio
        await asyncio.to_thread(self.sync.connect)
        return self
    async def __aexit__(self,kind,value,tb):
        import asyncio
        await asyncio.to_thread(self.sync.close)
