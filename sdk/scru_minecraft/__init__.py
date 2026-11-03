"""Small synchronous SDK for the SCRU Industrial Survival SMP HTTPS gateway. No model dependency."""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

__version__ = '0.3.0.dev2'


class GatewayError(RuntimeError):
    def __init__(self, status, code, retry_after=None):
        self.status, self.code, self.retry_after = status, code, retry_after
        super().__init__(f'{status}: {code}')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward bearer credentials to a different endpoint.
        return None


class ActionFailed(RuntimeError):
    def __init__(self, outcome):
        self.outcome=outcome
        super().__init__(f"{outcome['id']}: {outcome['state']}: {outcome.get('reason','')}")


def _match_action_epoch(outcome, body_epoch):
    if body_epoch is not None and outcome.get('state')!='unknown' and outcome.get('body_epoch')!=body_epoch:
        return {'id':outcome['id'],'state':'unknown','reason':'body_epoch_mismatch',
                'body_epoch':body_epoch,'observed_body_epoch':outcome.get('body_epoch')}
    return outcome


class ActionHandle(dict):
    """A backwards-compatible receipt with explicit completion and cancellation."""
    def __init__(self, client, receipt):
        super().__init__(receipt);self.client=client
    @property
    def id(self):return self['id']
    def wait(self, timeout=30):
        epoch=self.get('body_epoch')
        return self.client.wait_action(self.id,timeout,body_epoch=epoch) if epoch is not None else self.client.wait_action(self.id,timeout)
    def result(self, timeout=30):
        outcome=self.wait(timeout)
        if outcome['state']!='done':raise ActionFailed(outcome)
        return outcome
    def cancel(self):return self.client.cancel(self.id)


class PrimitiveMethods:
    def dig(self,x,y,z,**kw):return self.action('dig',target=[x,y,z],**kw)
    def place(self,x,y,z,face,**kw):return self.action('place',target=[x,y,z],face=face,**kw)
    def use_item(self,**kw):return self.action('use_item',**kw)
    def release_use(self,**kw):return self.action('release_use',**kw)
    def use_on(self,target=None,face='up',*,entity_id=None,**kw):
        if entity_id is not None:
            if target is not None:raise ValueError('Choose a block or entity target')
            return self.action('use_on',entity_id=entity_id,**kw)
        return self.action('use_on',target=target,face=face,**kw)
    def attack(self,entity_id,**kw):return self.action('attack',entity_id=entity_id,**kw)
    def select_slot(self,slot,**kw):return self.action('select_slot',slot=slot,**kw)
    def swap_hands(self,**kw):return self.action('swap_hands',**kw)
    def drop(self,slot,count,**kw):return self.action('drop',slot=slot,count=count,**kw)
    def jump(self,enabled=True,**kw):return self.action('jump',enabled=enabled,**kw)
    def sneak(self,enabled=True,**kw):return self.action('sneak',enabled=enabled,**kw)
    def sprint(self,enabled=True,**kw):return self.action('sprint',enabled=enabled,**kw)
    def chat(self,text,**kw):return self.action('chat',text=text,**kw)
    def cancel(self,action_id,**kw):return self.action('cancel',action_id=action_id,**kw)
    def open_container(self,x,y,z,**kw):return self.action('open_container',target=[x,y,z],**kw)
    def current_container(self):return self.observe().get('container') or {}
    def _session(self,session_id,revision):
        container=self.current_container()
        if session_id is None:session_id=container.get('session_id')
        if revision is None:revision=container.get('revision')
        if session_id is None or revision is None:raise ValueError('Open a container and await its observation first')
        return {'session_id':session_id,'revision':revision}
    def move_item(self,from_slot,to_slot,count,*,session_id=None,revision=None,**kw):
        return self.action('move_item',**{'from':from_slot,'to':to_slot,'count':count},
                           **self._session(session_id,revision),**kw)
    def close_container(self,*,session_id=None,revision=None,**kw):
        return self.action('close_container',**self._session(session_id,revision),**kw)
    def query_recipes(self,offset=0,limit=32,**kw):return self.action('query_recipes',offset=offset,limit=limit,**kw)
    def query_inventory(self,slot,*,inventory='player',offset=0,limit=16384,stack_revision=None,session_id=None,revision=None,**kw):
        fields={'slot':slot,'inventory':inventory,'offset':offset,'limit':limit}
        if stack_revision is not None:fields['stack_revision']=stack_revision
        if inventory=='container':fields.update(self._session(session_id,revision))
        elif session_id is not None or revision is not None:raise ValueError('Container session fields require inventory=container')
        return self.action('query_inventory',**fields,**kw)

    def query_recipe(self,recipe_id,*,offset=0,limit=16384,recipe_revision=None,**kw):
        fields={'recipe_id':recipe_id,'offset':offset,'limit':limit}
        if recipe_revision is not None:fields['recipe_revision']=recipe_revision
        return self.action('query_recipe',**fields,**kw)

    def _read_metadata(self,request,*,revision_key,chunk_key,encoding_key,identity,prefix,timeout,max_bytes):
        import base64,hashlib
        if type(max_bytes) is not int or not 1<=max_bytes<=16777216:raise ValueError('max_bytes must be 1..16777216')
        if type(timeout) not in (int,float) or not 0<timeout<=300:raise ValueError('timeout must be positive and at most 300 seconds')
        deadline=time.monotonic()+timeout
        offset=0;revision=None;epoch=None;total=None;chunks=[];first=None
        while True:
            if time.monotonic()>=deadline:raise TimeoutError('Metadata read timed out')
            handle=request(offset,revision)
            if epoch is None:epoch=handle['body_epoch']
            elif handle['body_epoch']!=epoch:raise ValueError('Body changed during metadata read; inspect again')
            page=handle.result(timeout=max(.001,deadline-time.monotonic()))
            if not identity(page) or page.get('offset')!=offset:raise ValueError('Invalid metadata page')
            if page.get(encoding_key)!='utf-8/base64':raise ValueError('Unsupported metadata encoding')
            if revision is None:
                revision=page.get(revision_key);total=page.get('total_bytes');first=page
                if not isinstance(revision,str) or len(revision)!=64 or type(total) is not int or not 0<total<=max_bytes:
                    raise ValueError('Invalid or oversized metadata result')
            elif page.get(revision_key)!=revision or page.get('total_bytes')!=total:
                raise ValueError('Stack or recipe changed during metadata read; inspect again')
            chunk=base64.b64decode(page.get(chunk_key,''),validate=True)
            if not chunk or page.get('next_offset',total)!=offset+len(chunk):raise ValueError('Invalid metadata continuation')
            if len(chunk)!=min(16384,total-offset):raise ValueError('Invalid metadata chunk size')
            chunks.append(chunk);offset+=len(chunk)
            if offset==total:
                if 'next_offset' in page:raise ValueError('Unexpected metadata continuation')
                break
        serialized=b''.join(chunks)
        if hashlib.sha256(prefix(first)+serialized).hexdigest()!=revision:raise ValueError('Metadata checksum mismatch')
        return first,json.loads(serialized.decode('utf-8'))

    def inventory_slot(self,slot,*,inventory='player',session_id=None,revision=None,timeout=30,max_bytes=4194304):
        """Read a full stack with bounded component pagination; never retry a changed stack."""
        session=self._session(session_id,revision) if inventory=='container' else {}
        def request(offset,stack_revision):
            return self.query_inventory(slot,inventory=inventory,offset=offset,stack_revision=stack_revision,**session)
        def identity(page):return page.get('inventory')==inventory and page.get('slot')==slot and isinstance(page.get('stack'),dict)
        def prefix(page):return (str(page['stack'].get('item'))+'\0'+str(page['stack'].get('count'))+'\0').encode('utf-8')
        page,components=self._read_metadata(request,revision_key='stack_revision',chunk_key='components_chunk',
            encoding_key='components_encoding',identity=identity,prefix=prefix,timeout=timeout,max_bytes=max_bytes)
        result=dict(page['stack'],components=components,stack_revision=page['stack_revision'])
        result.pop('components_truncated',None);result.pop('components_unavailable',None)
        return result

    def recipe(self,recipe_id,*,timeout=30,max_bytes=4194304):
        """Read the complete recipe descriptor, checking bounded chunks and SHA-256."""
        def request(offset,revision):return self.query_recipe(recipe_id,offset=offset,recipe_revision=revision)
        page,descriptor=self._read_metadata(request,revision_key='recipe_revision',chunk_key='recipe_chunk',
            encoding_key='encoding',identity=lambda p:p.get('recipe_id')==recipe_id,prefix=lambda p:b'',timeout=timeout,max_bytes=max_bytes)
        if not isinstance(descriptor,dict):raise ValueError('Invalid recipe descriptor')
        return descriptor
    def craft(self,recipe_id,count=1,**kw):return self.action('craft',recipe_id=recipe_id,count=count,**kw)
    def query_blocks(self,target=None,radius=1,*,positions=None,**kw):
        if positions is not None:
            if target is not None:raise ValueError('Choose radius or explicit positions')
            return self.action('query_blocks',positions=[list(p) for p in positions],**kw)
        return self.action('query_blocks',target=target,radius=radius,**kw)


class AgentClient(PrimitiveMethods):
    def __init__(self, url, token, agent=None, *, timeout=8, allow_local_http=False):
        parts = urllib.parse.urlsplit(url)
        if (parts.scheme != 'https' and not (allow_local_http and parts.scheme == 'http'
                and parts.hostname in {'127.0.0.1', 'localhost'})) or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('Use an HTTPS gateway URL without credentials, query or fragment')
        if not parts.hostname or not token or any(c in token for c in '\r\n'):
            raise ValueError('Gateway URL and private token are required')
        self.url, self.token, self.agent, self.timeout = url.rstrip('/'), token, agent, timeout
        self.opener = urllib.request.build_opener(NoRedirect())
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._lease = None
        self._error = None
        self._next_request = 0
        self._desired = None
        self._refreshed = 0
        self._observation = None
        self._observed_at = 0

    @classmethod
    def from_env(cls, agent=None):
        def env(name, default=None):
            return os.environ.get('SCRU_'+name, os.environ.get('SYN_'+name, default))
        token = env('AGENT_TOKEN')
        if not token:
            raise ValueError('Set SCRU_AGENT_TOKEN to your private gateway token')
        return cls(env('AGENT_URL', 'https://uk.syn.gl/minecraft-agents'),
                   token, agent or env('AGENT_ID'))

    @classmethod
    def from_file(cls, path='.scru-player.env', agent=None):
        """Read a private login file without displaying its token or executing shell code."""
        from pathlib import Path
        values = dict(line.split('=', 1) for line in Path(path).read_text().splitlines()
                      if line and not line.startswith('#') and '=' in line)
        return cls(values.get('SCRU_AGENT_URL', 'https://uk.syn.gl/minecraft-agents'),
                   values['SCRU_AGENT_TOKEN'], agent or values.get('SCRU_AGENT_ID'))

    @classmethod
    def start_login(cls, username, url='https://uk.syn.gl/minecraft-agents'):
        client = cls(url, 'enrollment-pending')
        return client._request('POST', '/v1/enroll/start', {'username': username}, authenticated=False)

    @classmethod
    def finish_login(cls, request_id, code, url='https://uk.syn.gl/minecraft-agents'):
        client = cls(url, 'enrollment-pending')
        return client._request('POST', '/v1/enroll/finish',
                               {'request_id': request_id, 'code': code}, authenticated=False)

    def _request(self, method, path, value=None, *, lease=True, authenticated=True):
        with self._lock:
            delay = self._next_request-time.monotonic()
            if delay > 0:
                time.sleep(delay)
            headers = {'Accept': 'application/json'}
            if authenticated:
                headers['Authorization'] = 'Bearer '+self.token
            if self.agent:
                headers['X-SCRU-Agent'] = self.agent
            if lease and self._lease:
                headers['X-SCRU-Lease'] = self._lease
            data = None
            if value is not None:
                data = json.dumps(value, allow_nan=False).encode()
                headers['Content-Type'] = 'application/json'
            request = urllib.request.Request(self.url+path, data=data, headers=headers, method=method)
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                try:
                    result = json.load(error)
                except (ValueError, OSError):
                    result = {}
                raise GatewayError(error.code, result.get('error', 'http_error'), error.headers.get('Retry-After')) from None
            finally:
                self._next_request = time.monotonic()+.11

    def capabilities(self):
        return self._request('GET', '/v1/me')

    def action(self, op, *, target=None, ttl_seconds=30, request_id=None, **fields):
        """Submit a primitive; accepted is not evidence of execution or completion."""
        if not self._lease:
            raise ValueError('Acquire control first')
        observation=self.observe()
        value={'op':op,'id':request_id or uuid.uuid4().hex,
               'body_epoch':observation.get('body_epoch'),'ttl_seconds':ttl_seconds}
        if set(fields) & set(value):raise ValueError('Reserved action fields')
        value.update(fields)
        if target is not None:value['target']=list(target)
        with self._lock:
            receipt=self._request('POST','/v1/actions',value)
            self._desired=None
            return ActionHandle(self,receipt)

    def move_to(self,x,y,z,**kwargs):
        return self.action('move_to',target=[x,y,z],**kwargs)

    def look_at(self,x,y,z,**kwargs):
        return self.action('look_at',target=[x,y,z],**kwargs)

    def action_results(self,action_id=None):
        return self._request('GET','/v1/action-results',{'action_id':action_id} if action_id else None)['results']

    def wait_action(self,action_id,timeout=30,*,body_epoch=None):
        deadline=time.monotonic()+timeout
        while True:
            result=_match_action_epoch(self.action_results(action_id)[0],body_epoch)
            if result['state'] in {'done','failed','cancelled','unknown'} and not result.get('details_pending'):return result
            if time.monotonic()>=deadline:raise TimeoutError('Action still pending')
            time.sleep(min(.15,max(0,deadline-time.monotonic())))

    def await_ready(self,timeout=30,required=()):
        deadline=time.monotonic()+timeout
        while True:
            body=self._request('GET','/v1/agent')
            if body['removed']:raise GatewayError(409,'agent_removed')
            if body['suspended']:raise GatewayError(423,'human_stop_requires_resume')
            if body['observed']:
                missing=set(required)-set(body['raw_capabilities'])
                if missing:raise GatewayError(409,'missing_capabilities:'+','.join(sorted(missing)))
                return body
            if time.monotonic()>=deadline:raise TimeoutError('Body not ready; check that Minecraft is online')
            time.sleep(min(.5,max(0,deadline-time.monotonic())))

    def prepare(self,name=None,*,create=False,area=None,job='engineer',timeout=30,required=()):
        if name is not None:self.agent=name
        if not self.agent:raise ValueError('Choose an owned agent name')
        if create:self.create_agent(self.agent,job,area)
        self.await_ready(timeout,required)
        return self

    def async_realtime(self):
        from .realtime import AsyncRealtimeClient
        return AsyncRealtimeClient(self)

    def events(self):
        """Yield pushed snapshots. Reconnection starts a new resync sequence, never replays commands."""
        from websockets.sync.client import connect
        url=('wss://' if self.url.startswith('https://') else 'ws://')+self.url.split('://',1)[1]+'/v1/events'
        with connect(url,max_size=1048576,max_queue=4,compression=None) as connection:
            connection.send(json.dumps({'token':self.token,'agent':self.agent}))
            for message in connection:
                yield json.loads(message)

    def realtime(self):
        """Use with client.realtime() as body for bidirectional low-latency control."""
        from .realtime import RealtimeClient
        return RealtimeClient(self)

    def list_agents(self):
        return self._request('GET', '/v1/agents')['agents']

    def create_agent(self, name, job='engineer', area=None):
        return self._request('POST', '/v1/agents', {'name': name, 'job': job, 'area': area})

    def issue_token(self):
        """Owner-only: rotate this body's scoped token; previous tokens are revoked."""
        return self._request('POST', '/v1/token', {})

    def remove_agent(self):
        return self._request('DELETE', '/v1/agent')

    def resume(self):
        """Owner-only: acknowledge a human stop before a new lease can be acquired."""
        return self._request('POST', '/v1/resume', {})

    def observe(self):
        with self._lock:
            if self._observation is not None and time.monotonic()-self._observed_at < 1.05:
                return self._observation
            self._observation = self._request('GET', '/v1/observation')
            self._observed_at = time.monotonic()
            return self._observation

    def current_container(self):
        # HTTP reads are intentionally slower; avoid accidentally reusing a pre-transfer revision.
        with self._lock:
            delay=1.05-(time.monotonic()-self._observed_at)
            if delay>0:time.sleep(delay)
            self._observation=None
            return self.observe().get('container') or {}

    def observations(self, interval=1.1):
        previous = None
        while not self._stop.is_set():
            if self._error:
                raise self._error
            observation = self.observe()
            if observation['id'] != previous:
                previous = observation['id']
                yield observation
            if self._stop.wait(max(1.1, interval)):
                break

    def connect(self):
        if not self.agent:
            raise ValueError('Select an agent name before acquiring control')
        if self._lease:
            return self
        result = self._request('POST', '/v1/lease', {}, lease=False)
        self._lease = result['lease_id']
        self._stop.clear()
        self._error = None
        self._thread = threading.Thread(target=self._maintain, daemon=True, name='scru-control-lease')
        self._thread.start()
        return self

    def set_goal(self, goal, observation_id, ttl_seconds=30, request_id=None):
        if not self._lease:
            raise ValueError('Call connect() or use a with block first')
        if self._error:
            raise self._error
        # Dedupe identical goals while keeping a finite renewal deadline.
        with self._lock:
            if self._desired and self._desired[0:2] == (goal, ttl_seconds) and time.monotonic()-self._refreshed < min(10, ttl_seconds/2):
                return self._desired[2]
            receipt = self._request('PUT', '/v1/goal', {'goal': goal, 'observation_id': observation_id,
                'ttl_seconds': ttl_seconds, 'request_id': request_id or uuid.uuid4().hex})
            self._desired = (goal, ttl_seconds, receipt)
            self._refreshed = time.monotonic()
            return receipt

    def say(self, text, request_id=None):
        return self._request('POST', '/v1/chat', {'text': text, 'request_id': request_id or uuid.uuid4().hex})

    def stop(self):
        with self._lock:
            self._desired = None
            return self._request('DELETE', '/v1/goal')

    def _maintain(self):
        while not self._stop.wait(8):
            try:
                self._request('PUT', '/v1/lease', {})
                # Keep the lease alive while models think, but never extend work on a stale frame.
                with self._lock:
                    desired = self._desired
                    if desired and time.monotonic()-self._refreshed >= min(10, desired[1]/2):
                        try:
                            observation = self.observe()
                            self.set_goal(desired[0], observation['id'], desired[1])
                        except GatewayError as error:
                            if error.status not in {409, 429, 503}:
                                raise
            except Exception as error:
                self._error = error
                self._stop.set()
                # Finite server lease and goal TTL bound work after a network failure.
                return

    def close(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=self.timeout+2)
        try:
            if self._lease:
                self._request('DELETE', '/v1/lease')
        finally:
            self._lease, self._desired = None, None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        try:
            self.close()
        except (GatewayError, OSError):
            if exc_type is None:
                raise
