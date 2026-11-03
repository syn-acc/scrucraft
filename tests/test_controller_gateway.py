import importlib.util
import json
import pathlib
import os
import sys
import tempfile
import threading
import time
import types
import urllib.request
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


gateway = module('gateway_tests', 'agent-gateway/gateway.py')
controller = module('gateway_controller', 'agent-service/service.py')
broker = module('gateway_broker', 'agent-gateway/provisioner.py')
sdk = module('gateway_sdk', 'sdk/scru_minecraft/__init__.py')
runtime = module('gateway_runtime', 'agent-service/runtime.py')
AREA = {'dimension': 'minecraft:overworld', 'min': [-10, 60, -10], 'max': [10, 80, 10]}


def frame(name='Forge', tick=100):
    return {'schema': 1, 'agent': name, 'job': 'engineer', 'tick': tick,
            'dimension': 'minecraft:overworld', 'position': [.5, 64, .5], 'health': 20,
            'food': 20, 'thirst': 20, 'temperature': 20, 'survival_profile': 'vanilla',
            'night': False, 'sheltered': False, 'inventory': [], 'entities': [], 'blocks': [],
            'walkable': [{'pos': [x, 64, 0]} for x in range(5)]}


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.now = 1000.0
        (root/'internal').write_text('internal-test-secret')
        self.config = root/'config.json'
        self.config.write_text(json.dumps({'name_prefix_required': False, 'reserved_names': ['ClosedDoor'],
            'internal_token_file': str(root/'internal'), 'provision_socket': 'unused'}))
        self.calls = []
        self.members = [{'name': name, 'uuid': 'uuid-'+name} for name in ('ClosedDoor', 'Other', 'Jamil')]
        self.identity = lambda value: {'ok': True, 'members': self.members} if value['operation'] == 'whitelist' else self.calls.append(value) or {'ok': True}
        self.g = gateway.Gateway(root, self.config, clock=lambda: self.now,
            provision_fn=lambda *args: self.calls.append(args) or {'ok': True}, identity_fn=self.identity)
        self.manager = self.g.issue('ClosedDoor', 'player')
        self.headers = {'Authorization': 'Bearer '+self.manager}
        self.g.handle('POST', '/v1/agents', self.headers, {'name': 'Forge', 'area': AREA})
        self.token = self.g.issue('ClosedDoor', 'agent', 'Forge')
        self.h = {'Authorization': 'Bearer '+self.token, 'X-Syn-Agent': 'Forge'}
        self.g.frame(frame())
        self.now += .2

    def tearDown(self):
        self.g.db.close()
        self.tmp.cleanup()

    def call(self, method, path, value=None, headers=None):
        self.now += .2
        return self.g.handle(method, path, headers or self.h, value or {})

    def lease(self):
        lease = self.call('POST', '/v1/lease')
        self.h['X-Syn-Lease'] = lease['lease_id']
        return lease

    def goal(self, **overrides):
        value = {'goal': 'gather_wood', 'observation_id': self.g.frames['Forge']['id'],
                 'request_id': 'a'*32, 'ttl_seconds': 30}
        value.update(overrides)
        return self.call('PUT', '/v1/goal', value)

    def error(self, status, fn):
        with self.assertRaises(gateway.APIError) as raised:
            fn()
        self.assertEqual(raised.exception.status, status)
        return raised.exception.code

    def test_other_owner_and_body_cannot_access(self):
        stranger = self.g.issue('Other', 'player')
        self.error(403, lambda: self.call('GET', '/v1/agent', headers={'Authorization': 'Bearer '+stranger, 'X-Syn-Agent': 'Forge'}))
        token = self.g.issue('ClosedDoor', 'agent', 'Another')
        self.error(403, lambda: self.call('GET', '/v1/observation', headers={'Authorization': 'Bearer '+token, 'X-Syn-Agent': 'Forge'}))
        self.error(403, lambda: self.call('POST', '/v1/agents', {'name': 'Extra'}))

    def test_exclusive_lease_and_wrong_lease(self):
        self.lease()
        self.error(409, lambda: self.call('POST', '/v1/lease'))
        self.h['X-Syn-Lease'] = 'not-the-lease'
        self.error(409, self.goal)

    def test_primitive_is_capability_gated_and_waits_for_body_result(self):
        self.lease()
        action={'id':'navigation12345678','op':'move_to','target':[3,64,0], 'body_epoch':'epoch1'}
        self.error(409, lambda:self.call('POST','/v1/actions',action))
        observation=frame(tick=120)
        observation.update(body_epoch='epoch1',raw_capabilities=['move_to','look_at','stop'],action_results=[])
        self.g.frame(observation)
        receipt=self.call('POST','/v1/actions',action)
        self.assertEqual(receipt['state'],'accepted')
        self.assertEqual(self.call('POST','/v1/actions',action),receipt)
        self.assertEqual(self.g.frame(observation)['control']['op'],'move_to')
        observation['action_results']=[{'id':action['id'],'state':'done','reason':'arrived'}]
        self.assertNotIn('control',self.g.frame(observation))

    def test_stop_and_whitelist_removal_clear_raw_control(self):
        observation=frame(tick=120)
        observation.update(body_epoch='epoch1',raw_capabilities=['look_at'])
        self.g.frame(observation);self.lease()
        self.call('POST','/v1/actions',{'id':'look_request12345','op':'look_at','target':[3,64,0], 'body_epoch':'epoch1'})
        self.call('DELETE','/v1/goal')
        self.assertNotIn('control',self.g.frame(observation))
        self.call('POST','/v1/actions',{'id':'look_request23456','op':'look_at','target':[3,64,0], 'body_epoch':'epoch1'})
        self.members.clear()
        self.assertNotIn('control',self.g.frame(observation))

    def test_scru_headers_and_legacy_headers_work_but_cannot_conflict(self):
        modern = {'Authorization': 'Bearer '+self.token, 'X-SCRU-Agent': 'Forge'}
        self.assertEqual(self.call('GET', '/v1/agent', headers=modern)['name'], 'Forge')
        modern['X-Syn-Agent'] = 'Other'
        self.error(400, lambda: self.call('GET', '/v1/agent', headers=modern))
        self.lease()
        self.h['X-SCRU-Lease'] = 'different-lease'
        self.error(400, self.goal)

    def test_expiry_reverts_to_survival_without_inference(self):
        self.lease()
        self.goal()
        self.assertEqual(self.g.frame(frame(tick=120))['goal'], 'gather_wood')
        self.now += 31
        self.assertEqual(self.g.frame(frame(tick=140))['goal'], 'rest')

    def test_goal_expiry_even_with_active_lease(self):
        self.lease()
        self.goal(ttl_seconds=1)
        self.now += 2
        self.assertEqual(self.g.frame(frame(tick=120))['goal'], 'rest')

    def test_replay_is_idempotent_and_changed_payload_rejected(self):
        self.lease()
        result = self.goal()
        self.assertEqual(self.goal(), result)
        self.error(409, lambda: self.goal(goal='explore'))

    def test_recent_previous_frame_accepted_and_old_frame_rejected(self):
        old = self.g.frames['Forge']['id']
        self.lease()
        self.g.frame(frame(tick=120))
        self.goal(observation_id=old)
        self.now += 6
        self.g.frame(frame(tick=240))
        self.error(409, lambda: self.goal(observation_id=old, request_id='b'*32))

    def test_revocation_cancels_current_work(self):
        self.lease()
        self.goal()
        self.g.db.execute('UPDATE tokens SET enabled=0 WHERE role=?', ('agent',))
        self.g.db.commit()
        self.assertEqual(self.g.frame(frame(tick=120))['goal'], 'rest')
        self.error(401, lambda: self.call('GET', '/v1/me'))

    def test_stop_is_sticky_and_resume_requires_manager(self):
        self.lease()
        self.goal()
        o = frame(tick=120)
        o['chat'] = [{'id': 'stop1', 'text': 'Forge, stop', 'speaker': 'Jamie_Syn', 'at': self.now}]
        self.assertEqual(self.g.frame(o)['goal'], 'rest')
        self.error(423, lambda: self.call('POST', '/v1/lease'))
        self.error(403, lambda: self.call('POST', '/v1/resume'))
        h = dict(self.headers, **{'X-Syn-Agent': 'Forge'})
        self.call('POST', '/v1/resume', headers=h)
        self.g.frame(o)  # repeated snapshot must not re-apply an acknowledged stop
        self.lease()

    def test_agent_speech_cannot_stop_other_bodies(self):
        self.lease()
        o = frame()
        o['chat'] = [{'id': 'agent-stop', 'text': 'Agents stop', 'agent': True, 'at': self.now}]
        self.g.frame(o)
        self.assertFalse(self.g.body('Forge')['data']['suspended'])

    def test_sanitized_snapshot(self):
        o = frame()
        o.update(chat=[{'id': 'x', 'text': 'secret', 'at': 0}], humans=[{'name': 'Jamie'}],
                 inventory=[{'item': 'minecraft:bread', 'hydration': 0}], provider_key='secret')
        self.g.frame(o)
        result = self.call('GET', '/v1/observation')
        for field in ('chat', 'humans', 'provider_key', 'thirst', 'temperature'):
            self.assertNotIn(field, result)
        self.assertNotIn('hydration', result['inventory'][0])

    def test_invalid_names_and_human_names_rejected(self):
        for name in ('ClosedDoor', 'x\nstop', 'x'*17, '../x'):
            self.now += 6
            self.error(409 if name == 'ClosedDoor' else 400,
                       lambda: self.call('POST', '/v1/agents', {'name': name}, self.headers))

    def test_public_token_cannot_post_internal_observations(self):
        self.error(401, lambda: self.call('POST', '/internal/frame', frame()))

    def test_creation_is_idempotent_case_and_owner_safe(self):
        self.now += 6
        result = self.call('POST', '/v1/agents', {'name': 'forge', 'area': AREA}, self.headers)
        self.assertEqual(result['name'], 'Forge')
        self.assertEqual(self.g.db.execute('SELECT COUNT(*) FROM bodies').fetchone()[0], 1)

    def test_no_work_area_prevents_resource_goals(self):
        body = self.g.body('Forge')
        body['data']['area'] = None
        self.g.save(body)
        self.lease()
        self.error(403, self.goal)

    def test_removed_agent_tokens_cannot_be_reused(self):
        h = dict(self.headers, **{'X-Syn-Agent': 'Forge'})
        self.call('DELETE', '/v1/agent', headers=h)
        self.error(401, lambda: self.call('GET', '/v1/me'))
        self.error(409, lambda: self.call('POST', '/v1/agents', {'name': 'Forge', 'area': AREA}, self.headers))

    def test_restart_does_not_restore_leases(self):
        self.lease()
        other = gateway.Gateway(self.tmp.name, self.config, clock=lambda: self.now, identity_fn=self.identity)
        try:
            self.assertEqual(other.frame(frame())['goal'], 'rest')
        finally:
            other.db.close()

    def test_each_whitelisted_player_can_enroll_and_create_own_agents(self):
        for index, owner in enumerate(('ClosedDoor', 'Other', 'Jamil')):
            self.now += 61
            challenge = self.call('POST', '/v1/enroll/start', {'username': owner.lower()}, headers={})
            message = self.calls[-1]
            self.assertNotIn('code', challenge)
            self.assertEqual(message['name'], owner)
            access = self.call('POST', '/v1/enroll/finish', {'request_id': challenge['request_id'], 'code': message['code']})
            self.assertEqual(access['role'], 'player')
            result = self.call('POST', '/v1/agents', {'name': 'AnyName'+str(index)},
                               headers={'Authorization': 'Bearer '+access['token']})
            self.assertEqual(result['owner'], owner)

    def test_nonmembers_never_receive_login_codes(self):
        before = len(self.calls)
        self.error(403, lambda: self.call('POST', '/v1/enroll/start', {'username': 'NotListed'}))
        self.assertEqual(len(self.calls), before)

    def test_code_guess_limit_expiry_and_replay(self):
        challenge = self.call('POST', '/v1/enroll/start', {'username': 'ClosedDoor'})
        code = self.calls[-1]['code']
        for _ in range(5):
            self.error(401, lambda: self.call('POST', '/v1/enroll/finish', {'request_id': challenge['request_id'], 'code': 'wrong'}))
        self.error(410, lambda: self.call('POST', '/v1/enroll/finish', {'request_id': challenge['request_id'], 'code': code}))
        self.now += 61
        challenge = self.call('POST', '/v1/enroll/start', {'username': 'ClosedDoor'})
        code = self.calls[-1]['code']
        self.call('POST', '/v1/enroll/finish', {'request_id': challenge['request_id'], 'code': code})
        self.error(410, lambda: self.call('POST', '/v1/enroll/finish', {'request_id': challenge['request_id'], 'code': code}))
        self.now += 61
        challenge = self.call('POST', '/v1/enroll/start', {'username': 'ClosedDoor'})
        code = self.calls[-1]['code']
        self.now += 301
        self.error(410, lambda: self.call('POST', '/v1/enroll/finish', {'request_id': challenge['request_id'], 'code': code}))

    def test_whitelist_removal_revokes_requests_and_active_work(self):
        self.lease()
        self.goal()
        self.members[:] = [row for row in self.members if row['name'] != 'ClosedDoor']
        self.error(403, lambda: self.call('GET', '/v1/me'))
        self.assertEqual(self.g.frame(frame(tick=120))['goal'], 'rest')

    def test_same_username_with_another_uuid_cannot_inherit_access(self):
        self.members[0]['uuid'] = 'different-account'
        self.error(403, lambda: self.call('GET', '/v1/agent'))
        replacement = self.g.issue('ClosedDoor', 'player')
        self.error(403, lambda: self.call('GET', '/v1/agent', headers={
            'Authorization': 'Bearer '+replacement, 'X-SCRU-Agent': 'Forge'}))

    def test_membership_rechecked_between_challenge_and_completion(self):
        challenge = self.call('POST', '/v1/enroll/start', {'username': 'ClosedDoor'})
        code = self.calls[-1]['code']
        self.members[0]['uuid'] = 'different-account'
        self.error(403, lambda: self.call('POST', '/v1/enroll/finish', {'request_id': challenge['request_id'], 'code': code}))

    def test_gateway_restart_invalidates_pending_login_codes(self):
        challenge = self.call('POST', '/v1/enroll/start', {'username': 'ClosedDoor'})
        code = self.calls[-1]['code']
        other = gateway.Gateway(self.tmp.name, self.config, identity_fn=self.identity, clock=lambda: self.now)
        try:
            self.error(410, lambda: other.handle('POST', '/v1/enroll/finish', {},
                       {'request_id': challenge['request_id'], 'code': code}))
        finally:
            other.db.close()

    def test_legacy_manager_handoff_invalidated_by_schema_migration(self):
        self.g.db.execute('INSERT INTO tokens(hash,owner,role,enabled) VALUES(?,?,?,1)',
                          ('old-digest', 'ClosedDoor', 'manager'))
        self.g.db.commit()
        other = gateway.Gateway(self.tmp.name, self.config, identity_fn=self.identity)
        try:
            self.assertEqual(other.db.execute('SELECT enabled FROM tokens WHERE hash=?', ('old-digest',)).fetchone()[0], 0)
        finally:
            other.db.close()


class ExternalControllerTests(unittest.TestCase):
    def test_storage_and_unobserved_blocks_never_mined(self):
        for block in ('minecraft:chest', 'minecraft:barrel', 'minecraft:oak_planks'):
            o = frame()
            o['blocks'] = [{'pos': [1, 64, 0], 'block': block, 'mature': True}]
            self.assertNotEqual(controller.external_action(o, {'goal': 'gather_wood', 'area': AREA})['kind'], 'mine')

    def test_resource_inside_area_can_be_mined(self):
        o = frame()
        o['blocks'] = [{'pos': [1, 64, 0], 'block': 'minecraft:oak_log'}]
        self.assertEqual(controller.external_action(o, {'goal': 'gather_wood', 'area': AREA})['kind'], 'mine')
        o['blocks'][0]['pos'] = [11, 64, 0]
        self.assertNotEqual(controller.external_action(o, {'goal': 'gather_wood', 'area': AREA})['kind'], 'mine')

    def test_final_path_and_work_target_validation(self):
        for action in ({'kind': 'move', 'target': [1, 64, 0], 'path': [[11, 64, 0]]},
                       {'kind': 'move', 'target': [1, 64, 0], 'work_target': [11, 64, 0]},
                       {'kind': 'place', 'pos': [1, 64, 0]}, {'kind': 'use', 'slot': 0}):
            with patch.object(controller, 'choose', return_value=action):
                self.assertEqual(controller.external_action(frame(), {'goal': 'explore', 'area': AREA})['kind'], 'idle')

    def test_wrong_dimension_cannot_mine(self):
        o = frame()
        o['dimension'] = 'minecraft:the_nether'
        o['blocks'] = [{'pos': [1, 64, 0], 'block': 'minecraft:oak_log'}]
        self.assertNotEqual(controller.external_action(o, {'goal': 'gather_wood', 'area': AREA})['kind'], 'mine')

    def test_survival_eating_overrides_external_work(self):
        o = frame()
        o['food'] = 6
        o['inventory'] = [{'slot': 0, 'item': 'minecraft:bread', 'count': 1, 'food': True}]
        self.assertEqual(controller.external_action(o, {'goal': 'gather_wood', 'area': AREA}), {'kind': 'eat'})

    def test_external_mode_does_not_submit_inference_or_ingest_tasks(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(controller, 'ROOT', pathlib.Path(tmp)):
            c = controller.Controller()
            try:
                with patch.object(controller, 'external_decision', return_value={'action': {'kind': 'idle'}}), \
                     patch.object(c.pool, 'submit', side_effect=AssertionError('paid inference')), \
                     patch.object(c, 'ingest_chat', side_effect=AssertionError('task ingestion')):
                    c.decide(frame())
            finally:
                c.pool.shutdown()
                c.db.close()

    def test_bad_gateway_config_fails_to_survival(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(controller, 'ROOT', pathlib.Path(tmp)):
            (pathlib.Path(tmp)/'gateway.json').write_text('{bad-json')
            self.assertEqual(controller.external_decision(frame())['action']['kind'], 'idle')


class BrokerTests(unittest.TestCase):
    def test_private_code_delivery_is_fixed_and_whitelist_uuid_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root/'whitelist.json').write_text('[{"name":"Player","uuid":"player-uuid"}]')
            request = {'operation': 'enroll', 'name': 'Player', 'uuid': 'player-uuid', 'code': '12345678'}
            command = broker.enrollment_message(request, root)
            self.assertTrue(command.startswith('tellraw Player '))
            self.assertEqual(command.count('\n'), 1)
            for change in ({'name': 'Player\nstop'}, {'uuid': 'other'}, {'code': 'hello world'}, {'extra': 'message'}):
                with self.assertRaises(ValueError):
                    broker.enrollment_message(dict(request, **change), root)

    def test_only_strict_lifecycle_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root/'config').mkdir()
            (root/'config/syn-agents.json').write_text('{"agents":[]}')
            (root/'whitelist.json').write_text('[{"name":"ClosedDoor"}]')
            (root/'ops.json').write_text('[]')
            self.assertEqual(broker.command({'operation': 'spawn', 'name': 'Forge', 'job': 'miner'}, root), 'synagent spawn Forge miner\n')
            for value in ({'operation': 'spawn', 'name': 'X\nstop', 'job': 'miner'},
                          {'operation': 'spawn', 'name': 'closeddoor', 'job': 'miner'},
                          {'operation': 'op', 'name': 'Forge', 'job': 'miner'}):
                with self.assertRaises(ValueError):
                    broker.command(value, root)


class SDKTests(unittest.TestCase):
    def test_scru_environment_precedes_legacy_without_losing_compatibility(self):
        with patch.dict(os.environ, {'SCRU_AGENT_TOKEN': 'scru-token', 'SYN_AGENT_TOKEN': 'old-token',
                                     'SCRU_AGENT_ID': 'Forge', 'SYN_AGENT_ID': 'Other'}, clear=True):
            client = sdk.AgentClient.from_env()
            self.assertEqual((client.token, client.agent), ('scru-token', 'Forge'))
        with patch.dict(os.environ, {'SYN_AGENT_TOKEN': 'old-token', 'SYN_AGENT_ID': 'Forge'}, clear=True):
            self.assertEqual(sdk.AgentClient.from_env().token, 'old-token')
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'SCRU_AGENT_TOKEN'):
                sdk.AgentClient.from_env()

    def test_refuses_remote_plaintext_and_credential_urls(self):
        for url in ('http://example.com', 'https://name:password@example.com', 'https://example.com?token=bad'):
            with self.assertRaises(ValueError):
                sdk.AgentClient(url, 'secret')

    def test_real_http_sdk_connect_observe_goal_stop_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root/'config').write_text(json.dumps({'name_prefix_required': False}))
            delivered = []
            def identity(value):
                if value['operation'] == 'enroll':
                    delivered.append(value)
                    return {'ok': True}
                return {'ok': True, 'members': [{'name': 'ClosedDoor', 'uuid': 'uuid-ClosedDoor'}]}
            g = gateway.Gateway(root, root/'config', identity_fn=identity)
            g.db.execute('INSERT INTO bodies VALUES(?,?,?)', ('Forge', 'ClosedDoor', json.dumps({'job': 'engineer', 'area': AREA, 'created_at': time.time(), 'owner_uuid': 'uuid-ClosedDoor'})))
            g.db.commit()
            g.frame(frame())
            server = gateway.Server(('127.0.0.1', 0), g)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                login = sdk.AgentClient(f'http://127.0.0.1:{server.server_port}', 'pending', allow_local_http=True)
                challenge = login._request('POST', '/v1/enroll/start', {'username': 'ClosedDoor'}, authenticated=False)
                access = login._request('POST', '/v1/enroll/finish',
                    {'request_id': challenge['request_id'], 'code': delivered[0]['code']}, authenticated=False)
                self.assertEqual(access['role'], 'player')
                login.token = access['token']
                login.agent = 'Forge'
                token = login.issue_token()['token']
                with sdk.AgentClient(f'http://127.0.0.1:{server.server_port}', token, 'Forge', allow_local_http=True) as client:
                    o = client.observe()
                    receipt = client.set_goal('gather_wood', o['id'])
                    self.assertEqual(receipt['status'], 'accepted')
                    self.assertEqual(client.set_goal('gather_wood', o['id']), receipt)
                    self.assertEqual(g.frame(frame(tick=120))['goal'], 'gather_wood')
                    client.stop()
                    self.assertEqual(g.frame(frame(tick=140))['goal'], 'rest')
                self.assertFalse(g.active('Forge'))
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                g.db.close()


class RuntimeNameTests(unittest.TestCase):
    def test_bridge_accepts_prefix_free_name_with_private_authentication(self):
        host = types.SimpleNamespace(controller=types.SimpleNamespace(token='private-bridge-test'),
            decide=lambda o: {'agent': o['agent'], 'tick': o['tick'], 'schema': 1, 'action': {'kind': 'idle'}})
        with patch.object(runtime, 'runtime', host, create=True):
            server = runtime.ThreadingHTTPServer(('127.0.0.1', 0), runtime.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/v1/decide',
                    data=json.dumps(frame('Forge')).encode(), headers={'Authorization': 'Bearer private-bridge-test'})
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertEqual(json.load(response)['agent'], 'Forge')
                request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/v1/decide',
                    data=json.dumps(frame('invalid name')).encode(), headers={'Authorization': 'Bearer private-bridge-test'})
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request, timeout=3)
                self.assertEqual(raised.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
