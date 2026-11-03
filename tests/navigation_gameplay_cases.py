"""VERIFY-01: constrained native terrain traversal, drop limits and unloaded targets."""
import time
import uuid

from gameplay_cases import done
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    def reset():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('kill @e[type=!minecraft:player]')
        fixture.console('fill -3 64 -3 13 73 3 air')
        fixture.console('fill -3 63 -3 13 63 3 stone')
        fixture.console('effect give VerifyBuilder saturation 1 255 true')
        time.sleep(.3)

    def corridor():
        fixture.console('fill -1 64 -1 9 72 -1 stone')
        fixture.console('fill -1 64 1 9 72 1 stone')
        fixture.console('fill -1 64 -1 -1 72 1 stone')
        fixture.console('fill 9 64 -1 9 72 1 stone')

    def traverse(receipt, timeout=15):
        samples = []
        end = time.monotonic()+timeout
        while time.monotonic() < end:
            observation = stream.observe()
            samples.append(observation['position'])
            result = next((r for r in observation['action_results'] if r['id'] == receipt['id']), None)
            if result and result['state'] in {'done', 'failed', 'cancelled'}:
                assert result['state'] == 'done', result
                return samples, stream.wait_action(receipt['id'], timeout=2)
            time.sleep(.04)
        raise TimeoutError('Constrained native navigation did not finish')

    def constrained_slab_stair_ascent():
        reset(); corridor()
        fixture.console('setblock 3 64 0 stone_slab[type=bottom]')
        fixture.console('setblock 4 64 0 stone_stairs[facing=east,half=bottom,shape=straight]')
        fixture.console('fill 5 64 0 8 64 0 stone')
        time.sleep(.2)
        samples, result = traverse(stream.move_to(7.5, 65, .5))
        assert all(-.01 <= p[2] <= 1.01 for p in samples), 'Route escaped the one-block corridor'
        assert max(p[1] for p in samples) >= 64.9
        assert stream.observe()['position'][0] > 7.0
        return {'terminal': result['reason'], 'samples': samples,
                'alternate_flat_route_excluded': True, 'native_shapes': ['bottom_slab', 'stairs', 'one_block_ascent']}

    fixture.case('navigation_confined_slab_stair_ascent', ['VERIFY-01'], constrained_slab_stair_ascent)

    def three_block_drop():
        reset(); corridor()
        fixture.console('fill 0 64 0 2 66 0 stone')
        fixture.console('tp VerifyBuilder 0.5 67 0.5')
        time.sleep(.3)
        health = stream.observe()['health']
        samples, result = traverse(stream.move_to(6.5, 64, .5))
        assert min(p[1] for p in samples) <= 64.1 and max(p[1] for p in samples) >= 66.9
        assert stream.observe()['health'] == health, 'Supported drop incurred unexpected damage'
        return {'drop_blocks': 3, 'health_preserved': True, 'terminal': result['reason'], 'samples': samples}

    fixture.case('navigation_three_block_drop', ['VERIFY-01'], three_block_drop)

    def excessive_drop():
        reset(); corridor()
        fixture.console('fill 0 64 0 2 67 0 stone')
        fixture.console('tp VerifyBuilder 0.5 68 0.5')
        time.sleep(.3)
        health = stream.observe()['health']
        receipt = stream.move_to(6.5, 64, .5, ttl_seconds=8)
        result = stream.wait_action(receipt['id'], timeout=12)
        assert result['state'] == 'failed' and result['reason'] in {'unreachable', 'timeout', 'search_budget_exhausted', 'invalid_endpoint'}, result
        observation = stream.observe()
        assert observation['position'][1] >= 67.9 and observation['health'] == health, observation['position']
        return {'drop_blocks': 4, 'rejected': result['reason'], 'body_remained_on_platform': True}

    fixture.case('navigation_rejects_four_block_drop', ['VERIFY-01'], excessive_drop)

    def unloaded_target():
        reset()
        fixture.console('gamerule spawnChunkRadius 0')
        target = [-60, 64, 0]  # Inside the documented 64-block action radius, outside view-distance 2.
        log = fixture.root/'minecraft.log'
        before = 'FixtureUnloadedBefore'+uuid.uuid4().hex
        fixture.console('execute unless loaded -60 64 0 run say '+before)
        wait_for(lambda: before in log.read_text(errors='replace'), timeout=10,
                 description='fixture target is initially unloaded')
        result = stream.wait_action(stream.move_to(*target)['id'], timeout=12)
        assert result['state'] == 'failed' and result['reason'] == 'invalid_endpoint', result
        after = 'FixtureUnloadedAfter'+uuid.uuid4().hex
        fixture.console('execute unless loaded -60 64 0 run say '+after)
        wait_for(lambda: after in log.read_text(errors='replace'), timeout=3,
                 description='navigation did not load the target chunk')
        return {'initially_unloaded': True, 'still_unloaded_after_request': True,
                'terminal': result['reason'], 'setup_only_console_loaded_checks': True}

    fixture.case('navigation_unloaded_target_does_not_force_load', ['VERIFY-01', 'OBS-03'], unloaded_target)
