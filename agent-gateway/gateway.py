"""Authenticated, owner-scoped Minecraft goal gateway. Python standard library only."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import pathlib
import re
import secrets
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = '0.3.0.dev2'
TERMINAL = {'done', 'failed', 'cancelled'}
RESULT_CORE = {'id','state','reason','body_epoch','tick','expires_at'}


def unfinished(record):
    return record['result']['state'] not in TERMINAL or bool(record['result'].get('details_pending'))


def settle(record, state, reason):
    record['result'].update(state=state, reason=reason)
    record['result'].pop('details_pending', None)
    record['result'].pop('details_retained_by_gateway', None)


PRIMITIVES = {'move_to','look_at','stop','cancel','dig','place','use_item','release_use','use_on',
              'attack','select_slot','swap_hands','drop','jump','sneak','sprint',
              'open_container','move_item','close_container','craft','chat','query_blocks','query_recipes','query_inventory','query_recipe'}
GOALS = {'rest', 'eat', 'gather_food', 'gather_wood', 'gather_ore',
         'collect_items', 'shelter', 'guard', 'explore'}
JOBS = {'farmer', 'miner', 'builder', 'guard', 'medic', 'engineer'}
NAME = re.compile(r'[A-Za-z0-9_]{1,16}\Z')
STATE = pathlib.Path(os.getenv('SYN_GATEWAY_STATE', '/data/minecraft-syn-smp/gateway'))
CONFIG = pathlib.Path(os.getenv('SYN_GATEWAY_CONFIG', '/etc/minecraft-syn-gateway/config.json'))


class APIError(Exception):
    def __init__(self, status, code, retry=None):
        self.status, self.code, self.retry = status, code, retry


def require(condition, code='invalid_request', status=400):
    if not condition:
        raise APIError(status, code)


def client_header(headers, suffix):
    """SCRU is canonical; reject ambiguous mixed-version identity headers."""
    current = headers.get('X-SCRU-'+suffix)
    legacy = headers.get('X-Syn-'+suffix)
    require(not (current is not None and legacy is not None and current != legacy), 'conflicting_headers')
    return current if current is not None else legacy or ''


def area(value):
    if value is None:
        return None
    require(isinstance(value, dict) and set(value) == {'dimension', 'min', 'max'})
    require(value['dimension'] in {'minecraft:overworld', 'minecraft:the_nether', 'minecraft:the_end'})
    for key in ('min', 'max'):
        require(isinstance(value[key], list) and len(value[key]) == 3)
        require(all(type(n) is int and abs(n) <= 30000000 for n in value[key]))
    require(all(a < b for a, b in zip(value['min'], value['max'])))
    return value


def inside(position, bounds, dimension):
    valid = (isinstance(position, list) and len(position) == 3
             and all(type(n) in (int, float) and math.isfinite(n) for n in position))
    return valid and (bounds is None or bounds['dimension'] == dimension
                     and all(lo <= n < hi for n, lo, hi in zip(position, bounds['min'], bounds['max'])))


def broker_request(value, socket_path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(4)
        channel.connect(str(socket_path))
        channel.sendall((json.dumps(value)+'\n').encode())
        data = channel.makefile('rb').readline(65536)
    result = json.loads(data)
    require(result.get('ok'), result.get('error', 'provision_failed'), 503)
    return result


def provision(operation, name, job, socket_path):
    return broker_request({'operation': operation, 'name': name, 'job': job}, socket_path)


class Gateway:
    def __init__(self, state=STATE, config=CONFIG, clock=time.time, provision_fn=provision, identity_fn=None):
        self.state, self.config, self.clock = pathlib.Path(state), pathlib.Path(config), clock
        self.provision = provision_fn
        self.identity = identity_fn or (lambda value: broker_request(value, self.settings()['provision_socket']))
        self.state.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.db = sqlite3.connect(self.state/'gateway.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, owner TEXT NOT NULL,
                role TEXT NOT NULL, agent TEXT, enabled INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS bodies(name TEXT PRIMARY KEY COLLATE NOCASE,
                owner TEXT NOT NULL, data TEXT NOT NULL);
        ''')
        if 'player_uuid' not in {row[1] for row in self.db.execute('PRAGMA table_info(tokens)')}:
            self.db.execute('ALTER TABLE tokens ADD COLUMN player_uuid TEXT')
        # Pre-enrollment owner handoff credentials must not bypass Minecraft identity proof.
        self.db.execute('UPDATE tokens SET enabled=0 WHERE player_uuid IS NULL')
        self.db.commit()
        # Leases intentionally do not survive a gateway restart.
        self.leases, self.frames, self.receipts, self.rates = {}, {}, {}, {}
        self.frame_ids = {}
        self.processed_frames = {}  # Internal observation ACKs: only fully processed frames.
        self.last_chat = 0
        self.enrollments = {}
        self.body_connections = {}
        self.stream_revision = 0
        self.body_revisions = {}
        self.body_conditions = {}
        self.actions = {}  # Bounded, epoch-scoped receipts, including commands not seen by Java yet.
        self.native_acks = {}
        self.result_sequence = 0
        self.stream_windows = {}

    def body_condition(self, name):
        with self.lock:
            return self.body_conditions.setdefault(name, threading.Condition(self.lock))

    def notify_body(self, name):
        with self.changed:
            self.stream_revision += 1
            self.body_revisions[name] = self.body_revisions.get(name,0)+1
            self.body_condition(name).notify_all()
            self.changed.notify_all()

    def result_changed(self, name, record):
        self.result_sequence += 1
        record['change_sequence'] = self.result_sequence
        record['stream_result'] = self.compact_results([record['result']])[0]
        self.stream_windows.pop(name, None)

    def stream_results(self, name):
        """Push recent transitions and all unfinished work; full history remains queryable."""
        if name not in self.stream_windows:
            records = sorted(self.actions.get(name, {}).values(), key=lambda r:r.get('change_sequence',0))
            recent = records[-64:]
            selected = [r for r in records[:-64] if unfinished(r)] + recent
            self.stream_windows[name] = [r.get('stream_result') or self.compact_results([r['result']])[0] for r in selected]
        return self.stream_windows[name]

    def update_results(self, name, observation=None):
        records = self.actions.setdefault(name, {})
        now = self.clock()
        if observation:
            epoch = observation.get('body_epoch')
            acknowledgements=self.native_acks.setdefault(name,{'epoch':epoch,'ids':{}})
            if acknowledgements['epoch']!=epoch:
                acknowledgements={'epoch':epoch,'ids':{}};self.native_acks[name]=acknowledgements
            for record in records.values():
                if unfinished(record) and record['control']['body_epoch'] != epoch:
                    settle(record, 'cancelled', 'body_changed')
                    self.result_changed(name, record)
            for result in observation.get('action_results', []):
                rid=result.get('id')
                full_native=(result.get('state') in TERMINAL and not result.get('details_pending')
                             and not result.get('details_retained_by_gateway')
                             and result.get('body_epoch',epoch)==epoch)
                if full_native and isinstance(rid,str):
                    acknowledgements['ids'][rid]=None
                    while len(acknowledgements['ids'])>512:acknowledgements['ids'].pop(next(iter(acknowledgements['ids'])))
                elif (result.get('details_retained_by_gateway') and result.get('state') in TERMINAL
                      and result.get('body_epoch',epoch)==epoch):
                    # A compact native receipt proves the previous ACK arrived. Full replay re-adds it.
                    acknowledgements['ids'].pop(rid, None)
                record = records.get(rid)
                if record is None and full_native and isinstance(epoch,str) and isinstance(rid,str) and re.fullmatch(r'[A-Za-z0-9_-]{16,80}',rid):
                    # A gateway restart may lose acceptance history while Java still has a full result.
                    # Recover evidence without inventing a retryable request payload or original lease.
                    record={'control':{'id':rid,'body_epoch':epoch},'payload':None,'receipt':dict(result),
                            'result':dict(result,recovered=True),'lease_id':None,'created_at':now,
                            'expires_at':now,'acknowledged':True,'full_result':True,'last_native':dict(result)}
                    record['size']=len(json.dumps(record['result']));records[rid]=record
                    self.result_changed(name, record)
                if record and record['control']['body_epoch'] == epoch and result.get('body_epoch', epoch) == epoch:
                    if result.get('state') in TERMINAL | {'started'}:
                        # Native terminal receipts supersede a conservative disconnect/timeout result.
                        if (record['result']['state'] not in TERMINAL or result['state'] in TERMINAL) and result != record.get('last_native'):
                            previous_result=record['result']
                            if result.get('details_pending') or result.get('details_retained_by_gateway'):
                                if not record.get('full_result'):
                                    record['result']=dict(result,body_epoch=epoch)
                            else:
                                record['result']=dict(result,body_epoch=epoch)
                                record['full_result']=result['state'] in TERMINAL
                            record['size']=len(json.dumps(record['result']))
                            record['last_native']=dict(result)
                            if record['result'] != previous_result:self.result_changed(name, record)
                        record['acknowledged'] = True
        for record in records.values():
            if unfinished(record) and now >= record['expires_at']:
                reason='result_details_timeout' if record['result'].get('details_pending') else 'outcome_unknown_timeout'
                settle(record, 'failed', reason)
                self.result_changed(name, record)
        while len(records)>512:
            oldest=next((rid for rid,record in records.items() if not unfinished(record)),None)
            if oldest is None:break
            del records[oldest]
            self.stream_windows.pop(name,None)
        # Terminal results remain available for ten minutes, and at most 512 per body.
        for rid in list(records):
            if not unfinished(records[rid]) and now-records[rid]['created_at'] > 600:
                del records[rid]
                self.stream_windows.pop(name,None)
                if name in self.frames:
                    self.frames[name]['action_results']=[r for r in self.frames[name].get('action_results',[]) if r.get('id')!=rid]
        # An additional memory bound protects against retained recipe/component payloads.
        size=sum(r.get('size',512) for r in records.values())
        for rid in list(records):
            if size<=8*1024*1024:break
            if not unfinished(records[rid]):
                size-=records[rid].get('size',512)
                del records[rid]
                self.stream_windows.pop(name,None)
                if name in self.frames:
                    self.frames[name]['action_results']=[r for r in self.frames[name].get('action_results',[]) if r.get('id')!=rid]
        return [dict(record['result']) for record in records.values()]

    def cancel_actions(self, name, reason, lease_id=None):
        for record in self.actions.get(name, {}).values():
            if (lease_id is None or record['lease_id'] == lease_id) and unfinished(record):
                settle(record, 'cancelled', reason)
                self.result_changed(name, record)
        frame = self.frames.get(name)
        if frame:
            frame['action_results'] = self.update_results(name)
            frame['id'] = secrets.token_urlsafe(18)
        self.notify_body(name)

    def release(self, name, reason):
        lease = self.leases.pop(name, None)
        if lease:
            self.cancel_actions(name, reason, lease['id'])

    def primitive(self, value, frame, body):
        op = value.get('op')
        require(isinstance(op,str) and op in PRIMITIVES, 'unsupported_operation', 422)
        require(op in frame.get('raw_capabilities',[]), 'adapter_upgrade_required', 409)
        require(isinstance(frame.get('body_epoch'),str) and value.get('body_epoch') == frame['body_epoch'], 'body_changed', 409)
        fields = {'id','op','body_epoch','ttl_seconds'}
        control = {'id':value.get('id'),'op':op,'body_epoch':frame['body_epoch']}
        require(isinstance(control['id'],str) and re.fullmatch(r'[A-Za-z0-9_-]{16,80}',control['id']))
        ttl = value.get('ttl_seconds',30)
        require(type(ttl) is int and 1 <= ttl <= 30)
        control['timeout_ticks'] = ttl*20
        target_ops = {'move_to','look_at','dig','place','use_on','open_container','query_blocks'}
        if (op in target_ops and not (op=='use_on' and 'entity_id' in value)
                and not (op=='query_blocks' and 'positions' in value)) or op == 'craft' and 'target' in value:
            fields.add('target'); target=value.get('target')
            require(isinstance(target,list) and len(target)==3 and all(type(n) in (int,float) and math.isfinite(n) and abs(n)<=30000000 for n in target))
            if op not in {'move_to','look_at'}:require(all(type(n) is int for n in target), 'block_coordinates_required')
            control['target']=target
            if op in {'dig','place','use_on','open_container','craft'}:
                require(inside(target,body['data'].get('area'),frame.get('dimension')), 'outside_work_area',403)
        def integer(key,lo,hi):
            fields.add(key); number=value.get(key)
            require(type(number) is int and lo <= number <= hi)
            control[key]=number
        if op=='place' or op=='use_on' and 'target' in control or op=='open_container' and 'face' in value:
            fields.add('face'); face=value.get('face')
            require(face in {'up','down','north','south','east','west'} if isinstance(face,str) else False)
            control['face']=face
        if op=='select_slot':integer('slot',0,8)
        if op=='drop':integer('slot',0,40);integer('count',1,99)
        if op=='attack' or op=='use_on' and 'entity_id' in value:integer('entity_id',0,2147483647)
        if op in {'place','use_item','use_on'} and 'hand' in value:
            fields.add('hand');require(isinstance(value['hand'],str) and value['hand'] in {'main','off'});control['hand']=value['hand']
        if op in {'jump','sneak','sprint'}:
            fields.add('enabled');require(type(value.get('enabled')) is bool);control['enabled']=value['enabled']
        if op=='query_blocks':
            if 'positions' in value:
                fields.add('positions');positions=value['positions']
                require(isinstance(positions,list) and 1<=len(positions)<=64)
                require(all(isinstance(p,list) and len(p)==3 and all(type(n) is int and abs(n)<=30000000 for n in p) for p in positions))
                control['positions']=positions
            else:integer('radius',0,4)
        if op=='query_recipes':
            if 'offset' in value:integer('offset',0,2147483647)
            if 'limit' in value:integer('limit',1,64)
        if op=='query_inventory':
            fields.add('inventory');inventory=value.get('inventory','player')
            require(isinstance(inventory,str) and inventory in {'player','container'});control['inventory']=inventory
            integer('slot',-1 if inventory=='player' else 0,40 if inventory=='player' else 255)
            if 'offset' in value:integer('offset',0,16777216)
            if 'limit' in value:integer('limit',1,16384)
            if 'stack_revision' in value or value.get('offset',0)>0:
                fields.add('stack_revision');revision=value.get('stack_revision')
                require(isinstance(revision,str) and re.fullmatch(r'[0-9a-f]{64}',revision))
                control['stack_revision']=revision
        if op=='query_recipe':
            fields.add('recipe_id');recipe=value.get('recipe_id')
            require(isinstance(recipe,str) and len(recipe)<=256 and re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+',recipe));control['recipe_id']=recipe
            if 'offset' in value:integer('offset',0,16777216)
            if 'limit' in value:integer('limit',1,16384)
            if 'recipe_revision' in value or value.get('offset',0)>0:
                fields.add('recipe_revision');revision=value.get('recipe_revision')
                require(isinstance(revision,str) and re.fullmatch(r'[0-9a-f]{64}',revision));control['recipe_revision']=revision
        if op=='cancel':
            fields.add('action_id');require(isinstance(value.get('action_id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{16,80}',value['action_id']));control['action_id']=value['action_id']
        if op in {'move_item','close_container'} or op=='query_inventory' and control['inventory']=='container':
            fields.add('session_id');require(isinstance(value.get('session_id'),str) and 1<=len(value['session_id'])<=80)
            control['session_id']=value['session_id'];integer('revision',0,2147483647)
        if op=='move_item':
            integer('count',1,64)
            for key in ('from','to'):
                fields.add(key); slot=value.get(key)
                require(isinstance(slot,dict) and set(slot)=={'inventory','slot'})
                require(isinstance(slot['inventory'],str) and slot['inventory'] in {'player','container'} and type(slot['slot']) is int and 0<=slot['slot']< (36 if slot['inventory']=='player' else 256))
                control[key]=dict(slot)
        if op=='craft':
            fields.add('recipe_id');require(isinstance(value.get('recipe_id'),str) and len(value['recipe_id'])<=256 and re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+',value['recipe_id']))
            control['recipe_id']=value['recipe_id'];integer('count',1,64)
        if op=='chat':
            fields.add('text');text=value.get('text')
            require(isinstance(text,str) and bool(text.strip()) and all(ord(c)>=32 and ord(c)!=127 and c!='§'
                    and not 0xD800<=ord(c)<=0xDFFF for c in text))
            require(sum(2 if ord(c)>0xFFFF else 1 for c in text)<=220,'chat_too_long')
            require(not text.startswith('/'),'commands_not_supported');control['text']=text
        require(set(value)<=fields,'unknown_action_fields')
        return control,ttl

    def settings(self):
        return json.loads(self.config.read_text())

    def member(self, name, player_uuid=None):
        rows = self.identity({'operation': 'whitelist'})['members']
        found = next((row for row in rows if row['name'].lower() == name.lower()
                      and (player_uuid is None or row['uuid'] == player_uuid)), None)
        require(found is not None, 'not_whitelisted', 403)
        return found

    def issue(self, owner, role='agent', agent=None, player_uuid=None):
        require(isinstance(owner, str) and NAME.fullmatch(owner))
        require(role in {'player', 'agent'} and (role == 'player' or agent))
        member = self.member(owner, player_uuid)
        owner, player_uuid = member['name'], member['uuid']
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        self.db.execute('INSERT INTO tokens(hash,owner,role,agent,player_uuid) VALUES(?,?,?,?,?)',
                        (digest, owner, role, agent, player_uuid))
        self.db.commit()
        return token

    def authenticate(self, authorization):
        require(isinstance(authorization, str) and authorization.startswith('Bearer '), 'unauthorized', 401)
        token = authorization[7:]
        require(20 <= len(token) <= 128, 'unauthorized', 401)
        row = self.db.execute('SELECT * FROM tokens WHERE hash=? AND enabled=1',
                              (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        require(row is not None, 'unauthorized', 401)
        self.member(row['owner'], row['player_uuid'])
        return dict(row)

    def body(self, name, principal=None):
        require(isinstance(name, str) and NAME.fullmatch(name), 'agent_required')
        row = self.db.execute('SELECT * FROM bodies WHERE name=?', (name,)).fetchone()
        require(row is not None, 'agent_not_found', 404)
        if principal:
            require(row['owner'] == principal['owner']
                    and json.loads(row['data']).get('owner_uuid') == principal['player_uuid']
                    and (principal['role'] == 'player' or principal['agent'] == row['name']), 'forbidden', 403)
        return dict(row) | {'data': json.loads(row['data'])}

    def save(self, body):
        self.db.execute('UPDATE bodies SET data=? WHERE name=?', (json.dumps(body['data']), body['name']))
        self.db.commit()

    def manager(self, principal):
        require(principal['role'] == 'player', 'player_access_required', 403)

    def enroll(self, path, value):
        now = self.clock()
        self.enrollments = {key: row for key, row in self.enrollments.items() if row['expires_at'] > now}
        if path == '/v1/enroll/start':
            name = value.get('username')
            require(isinstance(name, str) and NAME.fullmatch(name), 'invalid_username')
            self.limit(('enroll', 'global'), .5)
            member = self.member(name)
            self.limit(('enroll', member['uuid']), 60)
            require(len(self.enrollments) < 128, 'enrollment_capacity', 503)
            request_id = secrets.token_urlsafe(24)
            code = ''.join(secrets.choice('0123456789') for _ in range(8))
            row = dict(member, code_hash=hashlib.sha256(code.encode()).hexdigest(), attempts=0, expires_at=now+300)
            self.identity({'operation': 'enroll', 'name': member['name'], 'uuid': member['uuid'], 'code': code})
            self.enrollments[request_id] = row
            return {'request_id': request_id, 'expires_at': row['expires_at'],
                    'message': 'Join the Minecraft server, then enter the private code from in-game chat.'}
        request_id, code = value.get('request_id'), value.get('code')
        require(isinstance(request_id, str) and isinstance(code, str), 'invalid_enrollment')
        row = self.enrollments.get(request_id)
        require(row is not None, 'enrollment_expired', 410)
        row['attempts'] += 1
        matches = hmac.compare_digest(row['code_hash'], hashlib.sha256(code.encode()).hexdigest())
        if row['attempts'] >= 5 or matches:
            self.enrollments.pop(request_id, None)
        require(matches, 'invalid_code', 401)
        member = self.member(row['name'], row['uuid'])
        token = self.issue(member['name'], 'player', player_uuid=member['uuid'])
        return {'owner': member['name'], 'role': 'player', 'token': token}

    def limit(self, key, seconds):
        now = self.clock()
        deadline = self.rates.get(key, 0)
        if deadline > now:
            raise APIError(429, 'rate_limited', max(1, math.ceil(deadline-now)))
        self.rates[key] = now+seconds

    def active(self, name):
        lease = self.leases.get(name)
        if lease and lease['expires_at'] <= self.clock():
            self.release(name, 'lease_expired')
            lease = None
        return lease

    def lease(self, body, principal, lease_id):
        lease = self.active(body['name'])
        require(not body['data'].get('suspended'), 'human_stop_requires_resume', 423)
        require(lease and lease['token_hash'] == principal['hash']
                and isinstance(lease_id, str) and hmac.compare_digest(lease['id'], lease_id), 'lease_lost', 409)
        return lease

    def snapshot(self, body):
        frame = self.frames.get(body['name'])
        require(frame is not None, 'agent_not_observed', 503)
        require(self.clock()-frame['captured_at'] <= 5, 'observation_stale', 503)
        return frame

    def handle(self, method, path, headers, value):
        with self.lock:
            require(isinstance(value,dict),'invalid_request')
            if path == '/internal/frame' and method == 'POST':
                expected = pathlib.Path(self.settings()['internal_token_file']).read_text().strip()
                require(hmac.compare_digest(headers.get('Authorization', ''), 'Bearer '+expected), 'unauthorized', 401)
                return self.frame(value)
            if method == 'POST' and path in {'/v1/enroll/start', '/v1/enroll/finish'}:
                return self.enroll(path, value)
            if method == 'GET' and path == '/v1/access':
                return {'version': VERSION, 'registration': 'whitelist_in_game_code', 'role': 'player',
                        'name_prefix_required': self.settings().get('name_prefix_required', True),
                        'max_agents': 10, 'agent_ownership': 'creating_player'}
            p = self.authenticate(headers.get('Authorization', ''))
            # Bound all authenticated work, including failed mutations.
            # Safety release must never sit behind ordinary traffic's rate limit.
            if (method,path) not in {('DELETE','/v1/goal'),('DELETE','/v1/lease')}:
                self.limit(('request', p['hash']), .005)
            if path == '/v1/me' and method == 'GET':
                return {'version': VERSION, 'owner': p['owner'], 'role': p['role'], 'agent': p['agent'],
                        'goals': sorted(GOALS), 'lease_seconds': 30, 'observation_max_age_seconds': 5,
                        'name_prefix_required': self.settings().get('name_prefix_required', True),
                        'max_agents': 10, 'chat': 'capability_gated_public_stream', 'model_billing': 'bring_your_own',
                        'limits': {'request_interval_ms':5,'outstanding_actions':32,'result_retention_seconds':600,'retained_results':512}}
            if path == '/v1/agents' and method == 'GET':
                rows = self.db.execute('SELECT * FROM bodies WHERE owner=? ORDER BY name', (p['owner'],)).fetchall()
                return {'agents': [self.describe(dict(row) | {'data': json.loads(row['data'])}) for row in rows
                                   if json.loads(row['data']).get('owner_uuid') == p['player_uuid']
                                   and (p['role'] == 'player' or row['name'] == p['agent'])]}
            if path == '/v1/agents' and method == 'POST':
                return self.create(p, value)
            name = client_header(headers, 'Agent')
            body = self.body(name, p)
            name = body['name']
            if path == '/v1/agent' and method == 'GET':
                return self.describe(body)
            if path == '/v1/action-results' and method == 'GET':
                self.update_results(name)
                rows=self.result_rows(name)
                if 'action_id' in value:
                    rid=value['action_id']
                    require(isinstance(rid,str) and re.fullmatch(r'[A-Za-z0-9_-]{16,80}',rid))
                    rows=[r for r in rows if r['id']==rid] or [{'id':rid,'state':'unknown','reason':'result_not_retained'}]
                else:rows=self.compact_results(rows)
                return {'results': rows, 'retention_seconds':600, 'maximum_results':512}
            if path == '/v1/agent' and method == 'DELETE':
                self.manager(p)
                self.release(name, 'control_revoked')
                body['data']['suspended'] = True
                self.save(body)
                self.provision('remove', name, body['data']['job'], self.settings()['provision_socket'])
                # Keep the name reserved so stale tokens cannot inherit a recreated body.
                body['data']['removed'] = True
                self.save(body)
                self.db.execute('UPDATE tokens SET enabled=0 WHERE agent=?', (name,))
                self.db.commit()
                return {'status': 'removal_requested', 'agent': name}
            if path == '/v1/token' and method == 'POST':
                self.manager(p)
                require(not body['data'].get('removed'), 'agent_removed', 409)
                self.db.execute('UPDATE tokens SET enabled=0 WHERE agent=?', (name,))
                self.release(name, 'control_revoked')
                token = self.issue(p['owner'], 'agent', name, player_uuid=p['player_uuid'])
                return {'agent': name, 'token': token}
            if path == '/v1/resume' and method == 'POST':
                self.manager(p)
                require(not body['data'].get('removed'), 'agent_removed', 409)
                body['data']['suspended'] = False
                self.save(body)
                return {'status': 'resumed', 'agent': name}
            require(not body['data'].get('removed'), 'agent_removed', 409)
            if path == '/v1/observation' and method == 'GET':
                self.limit(('observation', p['hash'], name), .9)
                frame = dict(self.snapshot(body))
                frame['action_results']=self.compact_results(self.result_rows(name))
                lease = self.active(name)
                frame['control'] = {'suspended': body['data'].get('suspended', False),
                                    'goal': self.goal(lease), 'lease_active': bool(lease)}
                return frame
            if path == '/v1/lease' and method == 'POST':
                require(not body['data'].get('suspended'), 'human_stop_requires_resume', 423)
                self.snapshot(body)
                require(not self.active(name), 'lease_already_held', 409)
                lease = {'id': secrets.token_urlsafe(24), 'token_hash': p['hash'],
                         'expires_at': self.clock()+30, 'goal': None, 'chat': None}
                self.leases[name] = lease
                self.notify_body(name)
                return {'lease_id': lease['id'], 'expires_at': lease['expires_at']}
            lease = self.lease(body, p, client_header(headers, 'Lease'))
            if path == '/v1/actions' and method == 'POST':
                frame = self.snapshot(body)
                control,ttl = self.primitive(value,frame,body)
                rid=control['id'];op=control['op']
                payload=json.dumps(value,sort_keys=True,allow_nan=False)
                records=self.actions.setdefault(name,{})
                self.update_results(name)
                if rid in records:
                    previous=records[rid]
                    require(previous['payload']==payload,'request_id_reused',409)
                    require(previous['lease_id']==lease['id'],'action_belongs_to_previous_lease',409)
                    return dict(previous['receipt'])
                require(sum(unfinished(r) for r in records.values())<32,'action_queue_full',429)
                while len(records)>=512:
                    oldest=next((key for key,r in records.items() if not unfinished(r)),None)
                    require(oldest is not None,'result_capacity',503)
                    del records[oldest]
                # Protocol 2 carries a deduplicated queue; legacy bodies have only one mailbox.
                protocol=frame.get('control_protocol',1)
                if protocol>=2:
                    # Fixed at original acceptance, independent of later grant
                    # retransmission or the injectable lease/retention test clock.
                    control['deadline_ms']=time.time_ns()//1_000_000+ttl*1000
                if protocol<2:
                    require(op in {'move_to','look_at','stop'},'adapter_upgrade_required',409)
                    self.cancel_actions(name,'replaced_before_completion',lease['id'])
                if op=='chat':
                    self.limit(('chat',name),2)
                    self.limit(('chat','global'),.2)
                receipt={'id':rid,'state':'accepted','body_epoch':frame['body_epoch'],'expires_at':self.clock()+ttl}
                records[rid]={'control':control,'payload':payload,'receipt':dict(receipt),'result':dict(receipt),
                              'lease_id':lease['id'],'created_at':self.clock(),'expires_at':self.clock()+ttl,'acknowledged':False}
                self.result_changed(name, records[rid])
                if protocol<2:lease.update(control=control,control_until=self.clock()+ttl)
                lease['goal']=None
                frame['action_results']=self.result_rows(name);frame['id']=secrets.token_urlsafe(18)
                self.notify_body(name)
                return receipt
            if path == '/v1/lease' and method == 'PUT':
                lease['expires_at'] = self.clock()+30
                self.notify_body(name)
                return {'lease_id': lease['id'], 'expires_at': lease['expires_at']}
            if (path, method) in {('/v1/lease', 'DELETE'), ('/v1/goal', 'DELETE')}:
                lease['goal'], lease['chat'] = None, None
                lease.pop('control',None)
                lease['generation']=lease.get('generation',0)+1
                self.cancel_actions(name,'owner_stop',lease['id'])
                if path == '/v1/lease':
                    self.release(name, 'control_revoked')
                return {'status': 'stopped', 'agent': name}
            if (path, method) not in {('/v1/goal', 'PUT'), ('/v1/chat', 'POST')}:
                raise APIError(404, 'not_found')
            request_id = value.get('request_id')
            require(isinstance(request_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{16,80}', request_id))
            key = (lease['id'], path, request_id)
            payload = json.dumps(value, sort_keys=True)
            if key in self.receipts:
                old_payload, receipt = self.receipts[key]
                require(payload == old_payload, 'request_id_reused', 409)
                return receipt
            if path == '/v1/goal':
                require(self.snapshot(body).get('control_transport') != 'websocket', 'use_primitive_stream', 409)
                self.limit(('goal', name), 1)
                frame = self.snapshot(body)
                observed = self.frame_ids.get(name, {}).get(value.get('observation_id'))
                require(observed is not None and self.clock()-observed <= 5, 'observation_stale', 409)
                goal = value.get('goal')
                require(isinstance(goal, str) and goal in GOALS, 'goal_not_supported')
                ttl = value.get('ttl_seconds', 30)
                require(type(ttl) is int and 1 <= ttl <= 30)
                lease['goal'] = {'goal': goal, 'request_id': request_id, 'expires_at': self.clock()+ttl}
                lease.pop('control',None)
                receipt = {'status': 'accepted', **lease['goal']}
            else:
                require(self.snapshot(body).get('control_transport') != 'websocket', 'use_chat_primitive',409)
                text = value.get('text')
                require(isinstance(text, str) and 1 <= len(text) <= 256
                        and all(ord(c) >= 32 and c != '§' for c in text))
                require(not text.startswith('/'), 'commands_not_supported')
                self.limit(('chat', name), 120)
                self.limit(('chat', 'global'), 45)
                lease['chat'] = {'say': text, 'announcement_id': request_id, 'expires_at': self.clock()+15}
                receipt = {'status': 'queued', 'request_id': request_id}
            # Memory is bounded. Idempotency is guaranteed for the active 30s lease window.
            if len(self.receipts) >= 4096:
                live = {x['id'] for x in self.leases.values() if x['expires_at'] > self.clock()}
                self.receipts = {k: v for k, v in self.receipts.items() if k[0] in live}
                require(len(self.receipts) < 4096, 'receipt_capacity', 503)
            self.receipts[key] = (payload, receipt)
            return receipt

    def describe(self, body):
        data = body['data']
        frame = self.frames.get(body['name'])
        return {'name': body['name'], 'owner': body['owner'], 'job': data['job'],
                'raw_capabilities': frame.get('raw_capabilities',[]) if frame else [],
                'area': data.get('area'), 'suspended': data.get('suspended', False),
                'removed': data.get('removed', False),
                'observed': bool(frame and self.clock()-frame['captured_at'] <= 5)}

    def create(self, principal, value):
        self.manager(principal)
        name, job = value.get('name'), value.get('job', 'engineer')
        require(isinstance(name, str) and NAME.fullmatch(name), 'invalid_name')
        require(isinstance(job, str) and job in JOBS, 'invalid_job')
        config = self.settings()
        if config.get('name_prefix_required', True):
            require(re.fullmatch(r'Syn_[A-Za-z0-9_]{1,12}', name), 'prefix_removal_pending_maintenance', 409)
        humans = [row['name'] for row in self.identity({'operation': 'whitelist'})['members']]
        require(name.lower() not in {n.lower() for n in config.get('reserved_names', [])+humans}, 'name_reserved', 409)
        bounds = area(value.get('area'))
        existing = self.db.execute('SELECT * FROM bodies WHERE name=?', (name,)).fetchone()
        if existing:
            body = self.body(name, principal)
            require(body['data']['job'] == job and body['data'].get('area') == bounds
                    and not body['data'].get('removed'), 'name_reserved', 409)
            # Retry a provisioning failure safely; provisioner independently checks the live roster.
            if not self.frames.get(body['name']):
                self.provision('spawn', body['name'], job, config['provision_socket'])
            return self.describe(body)
        count = sum(not json.loads(r[0]).get('removed') for r in self.db.execute('SELECT data FROM bodies'))
        require(count < 10, 'agent_cap', 409)
        self.limit(('create', principal['owner']), 5)
        data = {'job': job, 'area': bounds, 'suspended': False, 'seen_chat': [], 'created_at': self.clock(),
                'owner_uuid': principal['player_uuid']}
        self.db.execute('INSERT INTO bodies(name,owner,data) VALUES(?,?,?)', (name, principal['owner'], json.dumps(data)))
        self.db.commit()
        self.provision('spawn', name, job, config['provision_socket'])
        return self.describe(self.body(name, principal)) | {'status': 'spawn_requested'}

    def goal(self, lease):
        if lease and lease.get('goal') and lease['goal']['expires_at'] > self.clock():
            return lease['goal']
        return None

    def frame(self, observation):
        received_at_ms=time.time_ns()//1_000_000
        name = observation.get('agent')
        try:
            body = self.body(name)
        except APIError:
            return {'goal': 'rest', 'area': None, 'status': 'unassigned'}
        require(type(observation.get('tick')) is int, 'invalid_frame')
        data = body['data']
        seen = data.get('seen_chat', [])
        changed = False
        for row in observation.get('chat', [])[-24:]:
            rid = row.get('id')
            if not rid or rid in seen:
                continue
            seen.append(rid)
            changed = True
            text = str(row.get('text', '')).lower()
            aliases = [name.lower()] + ([name[4:].lower()] if name.startswith('Syn_') else [])
            addressed = any(re.search(r'\b'+re.escape(alias)+r'\b', text) for alias in aliases)
            addressed = addressed or bool(re.search(r'\b(agents|all|everyone|team)\b', text))
            if (not row.get('agent') and addressed and re.search(r'\b(stop|wait|pause|stay)\b', text)
                    and row.get('at', 0) >= data['created_at']-2):
                data['suspended'] = True
                self.release(name, 'control_revoked')
        if changed:
            data['seen_chat'] = seen[-128:]
            self.save(body)
        # Deliberate whitelist: no humans, shared inventories, private/admin state or chat.
        fields = ('agent', 'tick', 'dimension', 'position', 'health', 'food', 'inventory',
                  'night', 'raining', 'sheltered', 'blocks', 'walkable', 'entities', 'entity_range', 'entities_truncated', 'last_action',
                  'adapter_version', 'survival_profile', 'advancements', 'deaths')
        fields += ('body_epoch','world_tick','average_tick_ms','raw_capabilities','action_results','control_transport','selected_slot','observation_ms',
                   'control_protocol','inventory_revision','container','recipes','queried_blocks','public_chat',
                   'active_actions','movement','hands','cursor','execution','sneaking','sprinting','jumping')
        snapshot = {k: observation[k] for k in fields if k in observation}
        old = self.frames.get(name)
        if observation.get('partial') and old and old.get('body_epoch') == observation.get('body_epoch') and old.get('dimension') == observation.get('dimension'):
            snapshot = {**old, **snapshot}
        else:
            snapshot['terrain_captured_at'] = self.clock()
        # Native timestamps are same-host diagnostics, distinct from the gateway's
        # own captured_at freshness. Partial frames must not inherit an old sample.
        for key in ('captured_at_ms','gateway_received_at_ms','body_receive_lag_ms','body_receive_clock_skew_ms'):
            snapshot.pop(key,None)
        native_capture=observation.get('captured_at_ms')
        if type(native_capture) is int and native_capture>=0:
            lag=received_at_ms-native_capture
            snapshot.update(captured_at_ms=native_capture,gateway_received_at_ms=received_at_ms,
                            body_receive_lag_ms=lag if lag>=0 else None)
            if lag<0:snapshot['body_receive_clock_skew_ms']=-lag
        snapshot['inventory'] = [{k: v for k, v in row.items() if k != 'hydration'}
                                 for row in snapshot.get('inventory', [])]
        # Opaque per-tick IDs stay stable if the controller retries the same frame.
        old = self.frames.get(name)
        snapshot['id'] = old['id'] if old and old.get('tick') == observation['tick'] and old.get('body_epoch') == observation.get('body_epoch') else secrets.token_urlsafe(18)
        snapshot['captured_at'] = old['captured_at'] if old and old['id'] == snapshot['id'] else self.clock()
        self.update_results(name, observation)
        snapshot['action_results'] = self.result_rows(name, observation.get('action_results',[]))
        self.frames[name] = snapshot
        self.notify_body(name)
        history = self.frame_ids.setdefault(name, {})
        history[snapshot['id']] = snapshot['captured_at']
        self.frame_ids[name] = {key: at for key, at in history.items() if self.clock()-at <= 5}
        lease = self.active(name)
        try:
            self.member(body['owner'], data.get('owner_uuid'))
            require(data.get('owner_uuid') is not None, 'identity_required', 403)
        except (APIError, OSError, KeyError):
            self.release(name, 'control_revoked')
            lease = None
        if data.get('suspended') or data.get('removed'):
            lease = None
        if lease and not self.db.execute('SELECT 1 FROM tokens WHERE hash=? AND enabled=1', (lease['token_hash'],)).fetchone():
            self.release(name, 'control_revoked')
            lease = None
        goal = self.goal(lease)
        result = {'goal': goal['goal'] if goal else 'rest', 'area': data.get('area'),
                  'status': 'active' if goal else 'survival_only'}
        if lease and lease.get('control') and lease.get('control_until',0)>self.clock():
            control=lease['control']
            done=any(row.get('id')==control['id'] and row.get('state') in {'done','failed','cancelled'}
                     for row in observation.get('action_results',[]))
            if control['body_epoch']==observation.get('body_epoch') and not done:
                result['control']=control
            else:lease.pop('control',None)
        if lease and lease.get('chat') and lease['chat']['expires_at'] > self.clock():
            result.update({k: lease['chat'][k] for k in ('say', 'announcement_id')})
        self.processed_frames[name]={'body_epoch':observation.get('body_epoch'),'tick':observation['tick']}
        return result

    def result_rows(self, name, native=None):
        rows={r.get('id'):dict(r) for r in (native if native is not None else self.frames.get(name,{}).get('action_results',[]))
              if not r.get('details_retained_by_gateway') or r.get('id') in self.actions.get(name,{})}
        rows.update({r['result']['id']:dict(r['result']) for r in self.actions.get(name,{}).values()})
        return list(rows.values())[-512:]

    @staticmethod
    def compact_results(rows):
        return [{**{key:value for key,value in row.items() if key in RESULT_CORE},
                 **({'details_available':True} if set(row)-RESULT_CORE else {}),
                 **({'details_pending':True} if row.get('details_pending') else {})}
                for row in rows]

    def realtime_control(self, name):
        """Short renewable grants; commands persist until acknowledged by the body."""
        body=self.body(name);frame=self.snapshot(body)
        modern=frame.get('control_protocol',1)>=2
        reply={'kind':'controls' if modern else 'idle','body_epoch':frame.get('body_epoch'),'valid_for_ticks':4}
        if modern:
            self.update_results(name)
            acknowledgements=self.native_acks.get(name,{})
            reply.update(commands=[],lease_id=None,area=body['data'].get('area'),
                         acknowledged_results=list(acknowledgements.get('ids',{})) if acknowledgements.get('epoch')==frame.get('body_epoch') else [])
        lease=self.active(name)
        if not lease or body['data'].get('suspended') or body['data'].get('removed'):return reply
        token=self.db.execute('SELECT * FROM tokens WHERE hash=? AND enabled=1',(lease['token_hash'],)).fetchone()
        if not token:
            self.release(name,'credential_revoked');return reply
        try:self.member(token['owner'],token['player_uuid'])
        except (APIError,OSError,KeyError):
            self.release(name,'membership_revoked');return reply
        if modern:
            reply['lease_id']=lease['id']+':'+str(lease.get('generation',0))
            reply['commands']=[dict(r['control'],timeout_ticks=max(1,min(r['control']['timeout_ticks'],int((r['expires_at']-self.clock())*20)))) for r in self.actions.get(name,{}).values()
                if r['lease_id']==lease['id'] and not r['acknowledged'] and r['result']['state']=='accepted'
                and r['control']['body_epoch']==frame.get('body_epoch')][:16]
        else:
            control=lease.get('control')
            if control and lease.get('control_until',0)>self.clock() and control['body_epoch']==frame.get('body_epoch'):
                done=any(row.get('id')==control['id'] and row.get('state') in TERMINAL for row in self.result_rows(name))
                if not done:reply.update(control,kind='control')
        return reply


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, address, gateway):
        self.gateway = gateway
        self.slots = threading.BoundedSemaphore(24)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'SCRUGateway/'+VERSION

    def log_message(self, *args):
        pass  # Tokens and request payloads never enter access logs.

    def handle_one_request(self):
        self.connection.settimeout(5)
        super().handle_one_request()

    def dispatch(self):
        status, retry = 200, None
        try:
            require(not self.headers.get('Transfer-Encoding'), 'chunked_not_supported')
            length = int(self.headers.get('Content-Length', '0'))
            require(0 <= length <= (262144 if self.path == '/internal/frame' else 16384), 'request_too_large', 413)
            value = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError())) if length else {}
            require(isinstance(value, dict))
            result = self.server.gateway.handle(self.command, self.path, self.headers, value)
        except APIError as exc:
            status, result, retry = exc.status, {'error': exc.code}, exc.retry
        except (ValueError, TypeError, KeyError):
            status, result = 400, {'error': 'invalid_request'}
        except Exception:
            status, result = 503, {'error': 'service_unavailable'}
        data = json.dumps(result, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        if retry:
            self.send_header('Retry-After', str(retry))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = dispatch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revoke-owner')
    args = parser.parse_args()
    gateway = Gateway()
    if args.revoke_owner:
        gateway.db.execute('UPDATE tokens SET enabled=0 WHERE owner=?', (args.revoke_owner,))
        gateway.db.commit()
        print('Owner tokens revoked.')
    else:
        if gateway.settings().get('websocket_enabled',False):
            from streaming import make_server
            websocket=make_server(gateway)
            threading.Thread(target=websocket.serve_forever,daemon=True,name='scru-streams').start()
        Server(('127.0.0.1', 8768), gateway).serve_forever()


if __name__ == '__main__':
    main()
