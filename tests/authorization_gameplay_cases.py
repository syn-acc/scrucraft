"""EXEC-03/06, SDK-02, VERIFY-03/04: native work during fixture policy changes.

All gameplay commands use the SDK. Identity/database/bounds changes are explicit
fault injection into the disposable fixture only. These cases do not simulate a
real human ServerChatEvent or prove participating-player enrollment.
"""
import copy
import hashlib
import math
import time
import uuid

from gameplay_cases import done, quantity
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    name = stream.client.agent

    def observed():
        # Revoked clients cannot read through their public connection. The fixture
        # reads incoming native telemetry while unauthorized, then uses SDK queries
        # after exact policy restoration to reconcile world/inventory state.
        with fixture.gateway.changed:
            return copy.deepcopy(fixture.gateway.frames[name])

    def inventory(observation):
        return [{key: row[key] for key in ('slot', 'item', 'count', 'damage', 'components') if key in row}
                for row in observation['inventory']]

    def reset():
        if stream.stopped.is_set():
            stream.reconnect()
        stream.stop()
        tick = observed()['world_tick']
        for command in (f'tp {name} 0.5 64 0.5', f'effect clear {name}',
                        f'effect give {name} saturation 1 255 true', f'clear {name}',
                        'kill @e[type=!minecraft:player]', 'fill -16 64 -16 26 72 16 air',
                        'fill -16 63 -16 26 63 16 stone', 'setblock 2 64 2 chest'):
            fixture.console(command)
        wait_for(lambda: observed()['world_tick'] >= tick + 6, description='fixture reset reached native observations')
        wait_for(lambda: not any(row.get('count', 0) for row in stream.observe()['inventory']),
                 description='empty initial survival inventory')
        done(stream, stream.select_slot(0))

    def started(receipt):
        return wait_for(lambda: next((row for row in observed()['action_results']
                        if row['id'] == receipt['id'] and row['state'] == 'started'), None),
                        description='native action start before authority change')

    def inactive(observation):
        execution = observation.get('execution', {})
        return (not execution.get('active_actions') and not execution.get('using_item')
                and not any(execution.get(key) for key in ('jump_requested', 'sneak_requested', 'sprint_requested'))
                and not observation.get('container', {}).get('open'))

    def revoke_during_work(policy, operation):
        reset()
        if operation == 'dig':
            fixture.console('setblock 2 64 0 oak_log')
        elif operation == 'use':
            fixture.console(f'item replace entity {name} hotbar.0 with bow 1')
            fixture.console(f'item replace entity {name} hotbar.1 with arrow 1')
            wait_for(lambda: quantity(stream, 'minecraft:bow') == 1 and quantity(stream, 'minecraft:arrow') == 1)
        opened = done(stream, stream.open_container(2, 64, 2))
        before = inventory(stream.observe())
        if operation == 'dig':
            receipt = stream.dig(2, 64, 0)
        elif operation == 'navigation':
            receipt = stream.move_to(8.5, 64, .5)
        else:
            # Two-second native deadline gives a finite original use duration to
            # wait beyond. Aborting a drawn bow must not behave like release_use.
            receipt = stream.use_item(ttl_seconds=2)
        begin = started(receipt)
        original_members = copy.deepcopy(fixture.members)
        digest = hashlib.sha256(stream.client.token.encode()).hexdigest()
        with fixture.gateway.changed:
            original_enabled = fixture.gateway.db.execute('SELECT enabled FROM tokens WHERE hash=?', (digest,)).fetchone()[0]
            owner = fixture.gateway.body(name)['owner']
        start = time.monotonic()
        stopped_at = None
        settled = None
        final = None
        try:
            with fixture.gateway.changed:
                if policy == 'whitelist_removed':
                    fixture.members[:] = [row for row in fixture.members if row['name'] != owner]
                elif policy == 'owner_uuid_changed':
                    fixture.members[:] = [dict(row, uuid=str(uuid.uuid5(uuid.NAMESPACE_DNS, 'scrucraft.fixture.replacement')))
                                          if row['name'] == owner else row for row in fixture.members]
                else:
                    fixture.gateway.db.execute('UPDATE tokens SET enabled=0 WHERE hash=?', (digest,))
                    fixture.gateway.db.commit()
            # No direct release/stop/notification: normal authority rechecks and
            # the <=200 ms native grant lifetime must end the actual work.
            wait_for(lambda: inactive(observed()), timeout=2, description='revoked native controls released')
            stopped_at = time.monotonic()-start
            assert stopped_at < 1, {'policy': policy, 'operation': operation, 'stop_seconds': stopped_at}
            with fixture.gateway.changed:
                assert fixture.gateway.active(name) is None, 'Revoked identity retained a control lease'
            stop_tick = observed()['world_tick']
            wait_for(lambda: observed()['world_tick'] >= stop_tick + 10, description='post-stop movement settled')
            settled = observed()
            wait_for(lambda: observed()['world_tick'] >= max(begin['tick'] + 100, stop_tick + 90),
                     timeout=12, description='past original dig/use completion and revoked grant lifetime')
            final = observed()
            assert inactive(final), final.get('execution')
            assert inventory(final) == before, {'before': before, 'after': inventory(final)}
            if operation == 'navigation':
                displacement = math.dist([settled['position'][i] for i in (0, 2)], [final['position'][i] for i in (0, 2)])
                assert displacement < .2, {'post_stop_horizontal_displacement': displacement}
                assert math.dist(final['position'], [8.5, 64, .5]) > 2, 'Revoked navigator reached its old target'
            assert not any(entity['type'] == 'minecraft:arrow' for entity in final.get('entities', [])), 'Abort fired a bow'
        finally:
            with fixture.gateway.changed:
                fixture.members[:] = original_members
                fixture.gateway.db.execute('UPDATE tokens SET enabled=? WHERE hash=?', (original_enabled, digest))
                fixture.gateway.db.commit()
            # Explicit new control after restoring the exact fixture identity;
            # neither this test nor reconnect calls owner resume or replays work.
            stream.reconnect()
        result = stream.wait_action(receipt['id'], timeout=5, body_epoch=receipt['body_epoch'])
        assert result['state'] == 'cancelled', result
        assert result['reason'] in {'lease_changed', 'control_released', 'control_expired', 'control_revoked',
                                    'credential_revoked', 'membership_revoked', 'stream_disconnected'}, result
        assert inventory(stream.observe()) == before
        assert not stream.observe()['container'].get('open')
        if operation == 'dig':
            block = done(stream, stream.query_blocks(positions=[[2, 64, 0]]))['blocks'][0]
            assert block['block'] == 'minecraft:oak_log', (result, block)
            assert quantity(stream, 'minecraft:oak_log') == 0
            assert not any(entity.get('stack', {}).get('item') == 'minecraft:oak_log'
                           for entity in stream.observe()['entities']), 'Late unauthorized dig spawned a drop'
        stale = stream.move_item({'inventory': 'player', 'slot': 0}, {'inventory': 'container', 'slot': 0}, 1,
                                 session_id=opened['session_id'], revision=opened['revision']).wait(5)
        assert stale['state'] == 'failed' and stale['reason'] in {'container_closed', 'stale_container_session'}, stale
        assert inventory(stream.observe()) == before
        assert done(stream, stream.look_at(-2, 65, 2))['state'] == 'done'
        return {'policy_fault': policy, 'operation': operation, 'native_stop_seconds': stopped_at,
                'waited_world_ticks_after_start': final['world_tick']-begin['tick'],
                'terminal_state': result['state'], 'terminal_reason': result['reason'],
                'inventory_unchanged': True, 'old_session_rejected': stale['reason'],
                'exact_identity_restored': fixture.members == original_members,
                'explicit_reconnect_only': True, 'human_chat_not_simulated': True}

    for policy in ('whitelist_removed', 'owner_uuid_changed', 'token_revoked'):
        for operation in ('dig', 'navigation', 'use'):
            fixture.case('authority_' + policy + '_during_' + operation,
                         ['EXEC-03', 'EXEC-06', 'SDK-02', 'VERIFY-03', 'VERIFY-04'],
                         lambda policy=policy, operation=operation: revoke_during_work(policy, operation))

    def wrong_owner():
        from scru_minecraft import AgentClient
        reset()
        fixture.console('setblock 2 64 0 oak_log')
        original_members = copy.deepcopy(fixture.members)
        other = {'name': 'FixtureStranger', 'uuid': str(uuid.uuid5(uuid.NAMESPACE_DNS, 'scrucraft.fixture.stranger'))}
        other_stream = None
        digest = None
        with fixture.gateway.changed:
            accepted_before = set(fixture.gateway.actions.get(name, {}))
            lease_before = fixture.gateway.active(name)['id']
        before = inventory(stream.observe())
        try:
            with fixture.gateway.changed:
                fixture.members.append(other)
                token = fixture.gateway.issue(other['name'], 'player', player_uuid=other['uuid'])
                digest = hashlib.sha256(token.encode()).hexdigest()
            other_stream = AgentClient(stream.client.url, token, name, allow_local_http=True, timeout=2).realtime()
            try:
                other_stream.connect()
            except ConnectionError:
                diagnostic = other_stream.diagnostics()['last_disconnect']
                assert diagnostic['close_code'] == 1008, diagnostic
                assert diagnostic['close_reason'].endswith('_forbidden'), diagnostic
            else:
                raise AssertionError('Different whitelisted owner acquired an existing body')
            with fixture.gateway.changed:
                assert set(fixture.gateway.actions.get(name, {})) == accepted_before
                assert fixture.gateway.active(name)['id'] == lease_before
            assert inventory(stream.observe()) == before
            assert done(stream, stream.query_blocks(positions=[[2, 64, 0]]))['blocks'][0]['block'] == 'minecraft:oak_log'
            return {'different_whitelisted_owner_rejected_before_action': True, 'existing_lease_unchanged': True,
                    'accepted_action_count_unchanged': True, 'world_inventory_unchanged': True}
        finally:
            if other_stream is not None:
                other_stream.close()
            with fixture.gateway.changed:
                fixture.members[:] = original_members
                if digest is not None:
                    fixture.gateway.db.execute('DELETE FROM tokens WHERE hash=?', (digest,));fixture.gateway.db.commit()

    fixture.case('authority_wrong_owner_rejected_before_native_execution', ['EXEC-06', 'VERIFY-03', 'VERIFY-04'], wrong_owner)

    def bounds_change():
        from scru_minecraft import GatewayError
        reset()
        fixture.console('setblock 2 64 0 oak_log')
        opened = done(stream, stream.open_container(2, 64, 2))
        before = inventory(stream.observe())
        receipt = stream.dig(2, 64, 0)
        begin = started(receipt)
        with fixture.gateway.changed:
            original = copy.deepcopy(fixture.gateway.body(name)['data'].get('area'))
        try:
            with fixture.gateway.changed:
                body = fixture.gateway.body(name)
                body['data']['area'] = {'dimension': 'minecraft:overworld', 'min': [-24, 60, -24], 'max': [2, 78, 24]}
                fixture.gateway.save(body)
            result = stream.wait_action(receipt['id'], timeout=5, body_epoch=receipt['body_epoch'])
            assert result['state'] == 'failed' and result['reason'] == 'outside_work_area', result
            wait_for(lambda: not stream.observe()['container'].get('open'), description='new bounds invalidate old container')
            try:
                stream.dig(2, 64, 0)
            except GatewayError as error:
                assert (error.status, error.code) == (403, 'outside_work_area'), (error.status, error.code)
            else:
                raise AssertionError('Changed bounds allowed a new dig')
            stale = stream.move_item({'inventory': 'player', 'slot': 0}, {'inventory': 'container', 'slot': 0}, 1,
                                     session_id=opened['session_id'], revision=opened['revision']).wait(5)
            assert stale['state'] == 'failed' and stale['reason'] in {'container_closed', 'stale_container_session', 'outside_work_area'}, stale
            wait_for(lambda: observed()['world_tick'] >= begin['tick'] + 100, timeout=12,
                     description='bounds-rejected dig remains aborted beyond original completion')
            assert inventory(stream.observe()) == before
            assert done(stream, stream.query_blocks(positions=[[2, 64, 0]]))['blocks'][0]['block'] == 'minecraft:oak_log'
            assert quantity(stream, 'minecraft:oak_log') == 0
            return {'active_dig_result': result['reason'], 'new_dig_http_status': 403,
                    'old_container_invalidated': True, 'waited_native_ticks': 100,
                    'target_intact': True, 'inventory_unchanged': True, 'fault_injection': 'fixture owner bounds only'}
        finally:
            with fixture.gateway.changed:
                body = fixture.gateway.body(name);body['data']['area'] = original;fixture.gateway.save(body)

    fixture.case('authority_bounds_change_aborts_active_dig_and_container',
                 ['EXEC-03', 'EXEC-06', 'VERIFY-03', 'VERIFY-04'], bounds_change)
