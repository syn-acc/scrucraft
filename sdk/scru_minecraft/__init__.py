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

__version__ = '0.2.0.dev1'


class GatewayError(RuntimeError):
    def __init__(self, status, code, retry_after=None):
        self.status, self.code, self.retry_after = status, code, retry_after
        super().__init__(f'{status}: {code}')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward bearer credentials to a different endpoint.
        return None


class AgentClient:
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

    def action(self, op, *, target=None, ttl_seconds=30, request_id=None):
        """Submit a primitive; accepted is not evidence of execution or completion."""
        if not self._lease:
            raise ValueError('Acquire control first')
        observation=self.observe()
        value={'op':op,'id':request_id or uuid.uuid4().hex,
               'body_epoch':observation.get('body_epoch'),'ttl_seconds':ttl_seconds}
        if target is not None:value['target']=list(target)
        with self._lock:
            receipt=self._request('POST','/v1/actions',value)
            self._desired=None
            return receipt

    def move_to(self,x,y,z,**kwargs):
        return self.action('move_to',target=[x,y,z],**kwargs)

    def look_at(self,x,y,z,**kwargs):
        return self.action('look_at',target=[x,y,z],**kwargs)

    def action_results(self):
        return self._request('GET','/v1/action-results')['results']

    def events(self):
        """Yield pushed snapshots. Reconnection starts a new resync sequence, never replays commands."""
        from websockets.sync.client import connect
        url='wss://'+self.url.split('://',1)[1]+'/v1/events'
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
