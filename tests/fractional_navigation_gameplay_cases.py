"""VERIFY-01 regression: resolve real fractional native ground without floating endpoints."""
import time

from gameplay_cases import done
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    def reset():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('fill -2 64 -2 10 70 2 air')
        fixture.console('fill -2 63 -2 10 63 2 stone')
        fixture.console('fill -1 64 -1 9 69 -1 stone')
        fixture.console('fill -1 64 1 9 69 1 stone')
        fixture.console('fill -1 64 -1 -1 69 1 stone')
        fixture.console('fill 9 64 -1 9 69 1 stone')
        time.sleep(.3)

    def short_route_completion():
        reset()
        before = stream.observe()['world_tick']
        result = done(stream, stream.move_to(1.5, 64, .5))
        elapsed = result['tick'] - before
        assert 0 < elapsed < 30, {'elapsed_native_ticks': elapsed, 'result': result}
        assert stream.observe()['position'][0] > 1, stream.observe()['position']
        assert stream.observe()['execution']['on_ground']
        return {'distance_requested_blocks': 1, 'completion_native_ticks': elapsed,
                'stall_replan_threshold_ticks': 30, 'arrival_completed_before_stall_replan': True}

    fixture.case('navigation_short_ground_route_completes_before_stall_replan',
                 ['VERIFY-01', 'EXEC-02'], short_route_completion)

    def fractional_ground():
        evidence = []
        for name, command, feet in (
            ('farmland', 'fill 2 63 0 7 63 0 farmland[moisture=7]', 63.9375),
            ('dirt_path', 'fill 2 63 0 7 63 0 dirt_path', 63.9375),
            ('carpet', 'fill 2 64 0 7 64 0 white_carpet', 64.0625),
            ('snow_layer', 'fill 2 64 0 7 64 0 snow[layers=2]', 64.125),
        ):
            reset()
            fixture.console(command)
            time.sleep(.2)
            result = done(stream, stream.move_to(6.5, 64, .5))
            position = wait_for(lambda: stream.observe()['position']
                if abs(stream.observe()['position'][1]-feet) < .01 else None,
                timeout=3, description='standing on actual ' + name + ' collision surface')
            assert position[0] > 6 and -.01 <= position[2] <= 1.01, position
            returned = done(stream, stream.move_to(.5, 64, .5))
            assert abs(stream.observe()['position'][1]-64) < .05
            evidence.append({'surface': name, 'actual_feet': position[1],
                             'requested_y': 64, 'arrival': result['reason'], 'return': returned['reason']})
        return {'native_surface_routes': evidence, 'alternate_route_excluded': True,
                'movement_or_teleport_injected_during_actions': False}

    fixture.case('navigation_native_fractional_ground_and_return', ['VERIFY-01'], fractional_ground)

    def no_floating_support():
        reset()
        fixture.console('fill 5 63 0 7 63 0 air')
        fixture.console('fill 5 62 0 7 62 0 stone')
        time.sleep(.2)
        result = stream.wait_action(stream.move_to(6.5, 64, .5)['id'], timeout=10)
        assert result['state'] == 'failed' and result['reason'] == 'invalid_endpoint', result
        assert stream.observe()['position'][0] < 1, stream.observe()['position']
        return {'target_floor_y': 63, 'requested_feet_y': 64,
                'terminal': result['reason'], 'body_did_not_start': True}

    fixture.case('navigation_fractional_resolver_rejects_floating_endpoint',
                 ['VERIFY-01', 'EXEC-05'], no_floating_support)
