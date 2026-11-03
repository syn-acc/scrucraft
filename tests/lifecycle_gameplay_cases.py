"""Native death/respawn and SDK resynchronization; no production bodies involved."""
import time
from gameplay_cases import done, quantity
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    def death_and_respawn():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('clear VerifyBuilder')
        fixture.console('kill @e[type=minecraft:item]')
        fixture.console('fill -2 64 -2 5 68 4 air')
        fixture.console('fill -2 63 -2 5 63 4 stone')
        fixture.console('fill 9 64 -1 11 67 1 air')
        fixture.console('fill 9 63 -1 11 63 1 stone')
        # Respawning at the death location naturally picks up dropped items before
        # observation. A separate native spawnpoint keeps both inventories observable.
        fixture.console('spawnpoint VerifyBuilder 10 64 0')
        fixture.console('gamerule keepInventory false')
        try:
            # A local player must acknowledge completed native dimension travel.
            # Otherwise ServerPlayer's changing-dimension flag makes /kill and
            # ordinary survival damage ineffective despite command acknowledgement.
            before_travel_epoch = stream.observe()['body_epoch']
            fixture.console('execute in minecraft:the_nether run forceload add 0 0')
            fixture.console('execute in minecraft:the_nether run fill 0 64 0 3 68 3 air')
            fixture.console('execute in minecraft:the_nether run fill 0 63 0 3 63 3 stone')
            entered_epoch = None
            try:
                fixture.console('execute in minecraft:the_nether run tp VerifyBuilder 0.5 64 0.5')
                entered = wait_for(lambda: fixture.gateway.frames.get('VerifyBuilder')
                                   if fixture.gateway.frames.get('VerifyBuilder', {}).get('dimension') == 'minecraft:the_nether'
                                   and fixture.gateway.frames['VerifyBuilder']['body_epoch'] != before_travel_epoch else None,
                                   timeout=35, description='lifecycle fixture native dimension transition')
                entered_epoch = entered['body_epoch']
            finally:
                fixture.console('execute in minecraft:overworld run tp VerifyBuilder 0.5 64 0.5')
                wait_for(lambda: fixture.gateway.frames.get('VerifyBuilder', {}).get('dimension') == 'minecraft:overworld'
                         and fixture.gateway.frames['VerifyBuilder'].get('body_epoch') != entered_epoch,
                         timeout=35, description='lifecycle fixture returns from native dimension transition')
                stream.reconnect()
                fixture.console('execute in minecraft:the_nether run forceload remove 0 0')
            health_before = stream.observe()['health']
            assert health_before > 0, stream.observe().get('health')
            damage = min(2.0, health_before / 2)
            fixture.console(f'damage VerifyBuilder {damage:.4f} minecraft:generic')
            health_after = wait_for(lambda: stream.observe()['health']
                                    if stream.observe()['health'] <= health_before - damage * .8 else None,
                                    timeout=5, description='ordinary native damage after dimension transition')
            fixture.console('give VerifyBuilder diamond 2')
            full_pack = bool(getattr(fixture.args, 'full_pack_mods', None))
            protected_tool = None
            if full_pack:
                fixture.console('item replace entity VerifyBuilder hotbar.1 with minecraft:iron_pickaxe[minecraft:damage=7,minecraft:custom_name=\'"Recovery proof"\'] 1')
                wait_for(lambda: quantity(stream, 'minecraft:iron_pickaxe') == 1)
                protected_tool = stream.inventory_slot(1)
            fixture.console('setblock 2 64 0 chest')
            wait_for(lambda: quantity(stream, 'minecraft:diamond') == 2)
            opened = done(stream, stream.open_container(2, 64, 0))
            epoch = stream.observe()['body_epoch']
            movement = stream.move_to(20.5, 64, .5)
            wait_for(lambda: movement['id'] in stream.observe()['execution']['active_actions'])
            death_position = stream.observe()['position']
            fixture.console('kill VerifyBuilder')
            started = time.monotonic()
            wait_for(lambda: fixture.gateway.frames.get('VerifyBuilder', {}).get('body_epoch') != epoch,
                     timeout=35, description='native AgentPlayer respawn and new epoch')
            stream.reconnect()
            observation = stream.observe()
            diagnostic = {'old_epoch': epoch, 'new_epoch': observation.get('body_epoch'),
                          'position': observation.get('position'), 'health': observation.get('health'),
                          'container': observation.get('container'), 'execution': observation.get('execution'),
                          'diamonds': quantity(stream, 'minecraft:diamond')}
            assert observation['body_epoch'] != epoch and observation['health'] > 0, diagnostic
            assert not observation['container'].get('open'), diagnostic
            assert not observation['execution']['active_actions'], diagnostic
            assert quantity(stream, 'minecraft:diamond') == 0, diagnostic
            dropped = sum(e.get('stack', {}).get('count', 0) for e in observation['entities']
                          if e.get('stack', {}).get('item') == 'minecraft:diamond')
            recovery = {'route': 'native_loose_drops', 'diamond_drops': dropped, 'player_diamonds': 0}
            if full_pack:
                assert dropped == 0, {'state': diagnostic, 'entities': observation['entities']}
                corpse = wait_for(lambda: next((e for e in stream.observe()['entities'] if e.get('type') == 'corpse:corpse'), None),
                                  description='native Corpse entity after owner death')
                # Native navigation and interaction perform recovery; no /data extraction or inventory restoration.
                pos = corpse['position']
                done(stream, stream.move_to(pos[0] + 1.5, 64, pos[2] + 1), timeout=25)
                done(stream, stream.use_on(entity_id=corpse['id']))
                container = wait_for(lambda: stream.observe().get('container') if stream.observe().get('container', {}).get('kind') == 'entity_menu' else None,
                                     description='native owner-authorized corpse menu')
                assert container['entity_id'] == corpse['id'] and container['entity_type'] == 'corpse:corpse', container
                rows = [r for r in container['slots'] if r['inventory'] == 'container']
                assert sum(r['count'] for r in rows if r.get('item') == 'minecraft:diamond') == 2
                tool = next(r for r in rows if r.get('item') == 'minecraft:iron_pickaxe')
                stored = stream.inventory_slot(tool['slot'], inventory='container', session_id=container['session_id'], revision=container['revision'])
                assert stored['components'] == protected_tool['components'] and stored['count'] == 1
                for item, count, destination in [('minecraft:diamond', 2, 0), ('minecraft:iron_pickaxe', 1, 1)]:
                    source = next(r for r in container['slots'] if r['inventory'] == 'container' and r.get('item') == item)
                    container = done(stream, stream.move_item({'inventory': 'container', 'slot': source['slot']},
                                     {'inventory': 'player', 'slot': destination}, count,
                                     session_id=container['session_id'], revision=container['revision']))
                wait_for(lambda: quantity(stream, 'minecraft:diamond') == 2 and quantity(stream, 'minecraft:iron_pickaxe') == 1)
                assert stream.inventory_slot(1)['components'] == protected_tool['components']
                assert not any(r['count'] for r in container['slots'] if r['inventory'] == 'container')
                done(stream, stream.close_container(session_id=container['session_id'], revision=container['revision']))
                recovery = {'route': 'native_owner_corpse_menu', 'diamond_drops': 0, 'player_diamonds': 2,
                            'corpse_diamonds_remaining': 0, 'named_damaged_tool_preserved': True,
                            'owner_recovery_verified': True, 'nonowner_denial_verified': False}
            else:
                assert dropped == 2, {'state': diagnostic, 'entities': observation['entities']}
            prior = stream.action_results(movement['id'])[0]
            assert prior['state'] in {'cancelled', 'failed'}, prior
            # A fresh epoch and live snapshots alone do not prove control resumed.
            resumed = done(stream, stream.look_at(12, 65, 2))
            assert resumed['body_epoch'] == observation['body_epoch'], resumed
            return {'death_to_recovery_and_fresh_control_seconds': time.monotonic()-started, 'epoch_changed': True,
                    'dimension_roundtrip_before_death': True, 'native_damage_after_dimension_change': damage,
                    'health_before_damage': health_before, 'health_after_damage': health_after,
                    'old_container_session': opened['session_id'], 'container_closed': True,
                    'prior_movement_outcome': prior['state'], **recovery, 'death_position': death_position,
                    'respawn_position': observation['position'], 'new_epoch_action': resumed['reason'],
                    'fixture_keep_inventory': False, 'fixture_respawn_separated_from_drops': True}
        finally:
            fixture.console('gamerule keepInventory true')
            fixture.console('spawnpoint VerifyBuilder 0 64 0')
            fixture.console('tp VerifyBuilder 0.5 64 0.5')

    fixture.case('native_death_respawn_and_sdk_resync', ['EXEC-03', 'EXEC-04', 'SDK-02', 'VERIFY-01', 'VERIFY-03'], death_and_respawn)
