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
            fixture.console('give VerifyBuilder diamond 2')
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
            assert dropped == 2, {'state': diagnostic, 'entities': observation['entities']}
            prior = stream.action_results(movement['id'])[0]
            assert prior['state'] in {'cancelled', 'failed'}, prior
            # A fresh epoch and live snapshots alone do not prove control resumed.
            resumed = done(stream, stream.look_at(12, 65, 2))
            assert resumed['body_epoch'] == observation['body_epoch'], resumed
            return {'respawn_seconds': time.monotonic()-started, 'epoch_changed': True,
                    'old_container_session': opened['session_id'], 'container_closed': True,
                    'prior_movement_outcome': prior['state'], 'diamond_drops': 2,
                    'player_diamonds': 0, 'death_position': death_position,
                    'respawn_position': observation['position'], 'new_epoch_action': resumed['reason'],
                    'fixture_keep_inventory': False, 'fixture_respawn_separated_from_drops': True}
        finally:
            fixture.console('gamerule keepInventory true')
            fixture.console('spawnpoint VerifyBuilder 0 64 0')
            fixture.console('tp VerifyBuilder 0.5 64 0.5')

    fixture.case('native_death_respawn_and_sdk_resync', ['EXEC-03', 'EXEC-04', 'SDK-02', 'VERIFY-01', 'VERIFY-03'], death_and_respawn)
