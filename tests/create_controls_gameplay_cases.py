"""MOD-01 / ACT-08,10: native Create placement, tools and water-powered processing.

Pinned reference: Creators-of-Create/Create tag mc1.21.1-6.0.10, specifically
DirectionalKineticBlock, RotatedPillarKineticBlock, IWrenchable, HandCrankBlockEntity,
WaterWheelBlockEntity and MillstoneBlockEntity. Console commands arrange only the
disposable scene/inputs and read native telemetry. All measured interactions,
machine placement, water activation and inventory transfers use the public SDK.
"""
import math
import re
import time

from gameplay_cases import done, quantity, slot
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    if not getattr(fixture.args, 'full_pack_mods', None):
        return

    def ticks(count):
        start = stream.observe()['world_tick']
        wait_for(lambda: stream.observe()['world_tick'] >= start + count,
                 timeout=max(15, count / 10), description='Create fixture native ticks')

    def reset():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('effect clear VerifyBuilder')
        fixture.console('effect give VerifyBuilder saturation 1 255 true')
        fixture.console('fill -5 64 -6 10 72 8 air')
        fixture.console('fill -5 63 -6 10 63 8 stone')
        ticks(2)
        fixture.console('kill @e[type=minecraft:item]')
        fixture.console('clear VerifyBuilder')
        ticks(8)
        assert not any(row.get('count', 0) for row in stream.observe()['inventory']), 'Fixture reset retained spilled inventory'
        done(stream, stream.select_slot(0))
        done(stream, stream.sneak(False))

    def block(position):
        return done(stream, stream.query_blocks(positions=[position]))['blocks'][0]

    def native_number(position, field):
        """Read-only test oracle, explicitly not a claimed SDK kinetic-state API."""
        log = fixture.root / 'minecraft.log'
        offset = log.stat().st_size
        fixture.console('data get block ' + ' '.join(map(str, position)) + ' ' + field)

        def answer():
            with log.open('rb') as source:
                source.seek(offset)
                text = source.read(65536).decode('utf-8', errors='replace')
            match = re.search(r'has the following block data:\s*(-?\d+(?:\.\d+)?)(?:[bdfsLl])?(?:\s|$)', text)
            return [float(match.group(1))] if match else None

        return wait_for(answer, timeout=5, description='native ' + field + ' telemetry')[0]

    def opened(receipt):
        result = done(stream, receipt)
        return result if 'session_id' in result else wait_for(
            lambda: stream.observe().get('container') if stream.observe().get('container', {}).get('open') else None)

    def move_item(state, source, destination, count):
        return opened(stream.move_item(source, destination, count,
            session_id=state['session_id'], revision=state['revision']))

    def amount(state, item):
        return sum(row.get('count', 0) for row in state.get('slots', [])
                   if row['inventory'] == 'container' and row.get('item') == item)

    with fixture.gateway.changed:
        body = fixture.gateway.body('VerifyBuilder')
        previous_area = body['data'].get('area')
        body['data']['area'] = None
        fixture.gateway.save(body)
    ticks(5)
    try:
        def placement_orientation():
            evidence = []
            for item, look, property_name, expected in (
                ('create:shaft', [20, 65.62, .5], 'axis', 'x'),
                ('create:shaft', [.5, 40, .5], 'axis', 'y'),
                # Native CogWheelBlock uses the clicked-face axis while sneaking;
                # place() intentionally sneaks to avoid activating the support.
                ('create:cogwheel', [20, 65.62, .5], 'axis', 'y'),
                ('create:large_cogwheel', [.5, 40, .5], 'axis', 'y'),
                ('create:water_wheel', [.5, 40, .5], 'facing', 'down'),
                ('create:hand_crank', [20, 65.62, .5], 'facing', 'up'),
                ('create:mechanical_press', [20, 65.62, .5], None, None),
                ('create:mechanical_mixer', [20, 65.62, .5], None, None),
                ('create:gearbox', [20, 65.62, .5], None, None),
                ('create:depot', [20, 65.62, .5], None, None),
                ('create:basin', [20, 65.62, .5], None, None),
                ('create:millstone', [20, 65.62, .5], None, None),
            ):
                reset()
                fixture.console('item replace entity VerifyBuilder hotbar.0 with ' + item + ' 2')
                wait_for(lambda: quantity(stream, item) == 2)
                done(stream, stream.look_at(*look))
                done(stream, stream.place(2, 64, 0, 'up'))
                actual = block([2, 64, 0])
                assert actual['block'] == item and quantity(stream, item) == 1, actual
                if property_name:
                    assert actual['properties'][property_name] == expected, actual
                evidence.append({'block': item, 'properties': actual['properties'], 'consumed': 1})
            return {'held_native_placements': evidence, 'optional_area': None,
                    'seeded_inputs': 'two of each tested machine item and stone support',
                    'machine_recipes_or_power_claimed': False}

        fixture.case('create_held_machine_placement_and_native_orientation',
                     ['ACT-08', 'OBS-03', 'VERIFY-03', 'MOD-01'], placement_orientation)

        def wrench_rotation_and_recovery():
            reset()
            fixture.console('item replace entity VerifyBuilder hotbar.0 with create:shaft 1')
            fixture.console('item replace entity VerifyBuilder hotbar.1 with create:wrench 1')
            wait_for(lambda: quantity(stream, 'create:shaft') == quantity(stream, 'create:wrench') == 1)
            wrench_before = stream.inventory_slot(1)
            done(stream, stream.look_at(20, 65.62, .5))
            done(stream, stream.place(2, 64, 0, 'up'))
            assert block([2, 64, 0])['properties']['axis'] == 'x'
            done(stream, stream.select_slot(1))
            done(stream, stream.use_on([2, 64, 0], face='up'))
            rotated = block([2, 64, 0])
            assert rotated['properties']['axis'] == 'z', rotated
            done(stream, stream.sneak(True))
            try:
                done(stream, stream.use_on([2, 64, 0], face='up'))
            finally:
                done(stream, stream.sneak(False))
            assert block([2, 64, 0])['block'] == 'minecraft:air'
            assert quantity(stream, 'create:shaft') == quantity(stream, 'create:wrench') == 1
            wrench_after = stream.inventory_slot(1)
            assert wrench_after['components'] == wrench_before['components']
            assert not any(e.get('stack', {}).get('item') == 'create:shaft' for e in stream.observe()['entities'])
            return {'placed_axis': 'x', 'wrenched_axis': 'z', 'sneak_wrench_recovered': 1,
                    'wrench_components_preserved': True, 'duplicate_drop_entities': 0}

        fixture.case('create_wrench_native_rotation_and_sneak_recovery',
                     ['ACT-08', 'ACT-10', 'VERIFY-03', 'MOD-01'], wrench_rotation_and_recovery)

        def shaft_helper_and_optional_bounds():
            reset()
            fixture.console('item replace entity VerifyBuilder hotbar.0 with create:shaft 2')
            wait_for(lambda: quantity(stream, 'create:shaft') == 2)
            done(stream, stream.look_at(20, 65.62, .5))
            done(stream, stream.place(2, 64, 0, 'up'))
            with fixture.gateway.changed:
                body = fixture.gateway.body('VerifyBuilder')
                body['data']['area'] = {'dimension': 'minecraft:overworld', 'min': [2, 63, 0], 'max': [3, 67, 1]}
                fixture.gateway.save(body)
            ticks(5)
            try:
                result = stream.wait_action(stream.use_on([2, 64, 0], face='west')['id'])
                assert result['state'] == 'failed' and result['reason'] in ('outside_work_area', 'unsupported_use_footprint'), result
                assert quantity(stream, 'create:shaft') == 1
                assert block([1, 64, 0])['block'] == block([3, 64, 0])['block'] == 'minecraft:air'
            finally:
                with fixture.gateway.changed:
                    body = fixture.gateway.body('VerifyBuilder')
                    body['data']['area'] = None
                    fixture.gateway.save(body)
                ticks(5)
            done(stream, stream.use_on([2, 64, 0], face='west'))
            queried = done(stream, stream.query_blocks(positions=[[1, 64, 0], [2, 64, 0], [3, 64, 0]]))['blocks']
            actual = [row for row in queried if row['block'] == 'create:shaft']
            assert len(actual) == 2 and all(row['properties']['axis'] == 'x' for row in actual), queried
            assert quantity(stream, 'create:shaft') == 0
            return {'bounded_helper_rejected_without_consumption': True,
                    'native_unrestricted_helper_placed_one_shaft': True,
                    'resulting_shaft_positions': [row['position'] for row in actual], 'shafts_consumed_total': 2}

        fixture.case('create_native_shaft_placement_helper_respects_optional_bounds',
                     ['ACT-08', 'ACT-10', 'EXEC-06', 'VERIFY-04', 'MOD-01'], shaft_helper_and_optional_bounds)

        def crank_use_direction_and_decay():
            reset()
            fixture.console('item replace entity VerifyBuilder hotbar.0 with create:hand_crank 1')
            wait_for(lambda: quantity(stream, 'create:hand_crank') == 1)
            done(stream, stream.place(2, 64, 0, 'up'))
            assert block([2, 64, 0])['properties']['facing'] == 'up'
            assert native_number([2, 64, 0], 'Speed') == 0
            done(stream, stream.select_slot(8))
            done(stream, stream.use_on([2, 64, 0], face='up'))
            forward = native_number([2, 64, 0], 'Speed')
            assert abs(forward) == 32, forward
            done(stream, stream.sneak(True))
            try:
                done(stream, stream.use_on([2, 64, 0], face='up'))
                reverse = native_number([2, 64, 0], 'Speed')
                assert reverse == -forward and native_number([2, 64, 0], 'Backwards') == 1, (forward, reverse)
            finally:
                done(stream, stream.sneak(False))
            ticks(15)
            assert native_number([2, 64, 0], 'InUse') == 0 and native_number([2, 64, 0], 'Speed') == 0
            return {'forward_native_rpm': forward, 'reverse_native_rpm': reverse, 'native_decay_to_zero': True,
                    'energy_injected': False, 'telemetry_oracle': 'read-only fixture console; no SDK kinetic telemetry claim'}

        fixture.case('create_hand_crank_native_forward_reverse_and_expiry',
                     ['ACT-10', 'OBS-03', 'MOD-01'], crank_use_direction_and_decay)

        def waterwheel_powers_native_milling():
            reset()
            # A one-block stone flume east of the horizontal wheel. It contains no
            # water, output items, generator or preconfigured kinetic block entity.
            fixture.console('fill 4 64 -3 4 64 3 stone')
            fixture.console('fill 2 64 -3 2 64 -1 stone')
            fixture.console('fill 2 64 1 2 64 3 stone')
            fixture.console('setblock 3 64 -3 stone')
            for index, (item, count) in enumerate((('create:water_wheel', 1), ('create:millstone', 1),
                                                   ('minecraft:water_bucket', 1), ('minecraft:wheat', 2))):
                fixture.console(f'item replace entity VerifyBuilder hotbar.{index} with {item} {count}')
            wait_for(lambda: quantity(stream, 'minecraft:wheat') == 2 and quantity(stream, 'create:water_wheel') == 1)
            done(stream, stream.look_at(.5, 40, .5))
            done(stream, stream.place(2, 64, 0, 'up'))
            wheel = block([2, 64, 0])
            assert wheel['properties']['facing'] in ('up', 'down'), wheel
            done(stream, stream.select_slot(1))
            done(stream, stream.place(2, 65, 0, 'up'))
            assert quantity(stream, 'create:water_wheel') == quantity(stream, 'create:millstone') == 0
            recipe = stream.recipe('create:milling/wheat')
            assert recipe['native_recipe']['type'] == 'create:milling'
            state = opened(stream.open_container(2, 65, 0))
            state = move_item(state, {'inventory': 'player', 'slot': 3}, {'inventory': 'container', 'slot': 0}, 1)
            ticks(170)
            state = stream.observe()['container']
            assert amount(state, 'minecraft:wheat') == 1 and amount(state, 'create:wheat_flour') == 0
            assert native_number([2, 64, 0], 'Speed') == 0 and native_number([2, 65, 0], 'Speed') == 0
            done(stream, stream.close_container(session_id=state['session_id'], revision=state['revision']))
            done(stream, stream.move_to(2.5, 65, -1.5))
            assert math.dist(stream.observe()['position'], [2.5, 65, -1.5]) < .6
            done(stream, stream.select_slot(2))
            done(stream, stream.look_at(3.5, 64, -1.5))
            done(stream, stream.use_item())
            assert quantity(stream, 'minecraft:bucket') == 1

            def flowing():
                current = block([3, 64, 0])
                return current if current['block'] == 'minecraft:water' and 0 < int(current['properties']['level']) < 8 else None

            flow = wait_for(flowing, timeout=15, description='native horizontal water flow reaches wheel rim')
            state = opened(stream.open_container(2, 65, 0))
            state = wait_for(lambda: stream.observe()['container'] if amount(stream.observe()['container'], 'create:wheat_flour') else None,
                             timeout=25, description='waterwheel alone powers native flour production')
            flour = amount(state, 'create:wheat_flour')
            assert amount(state, 'minecraft:wheat') == 0 and 1 <= flour <= 3, state
            wheel_speed, mill_speed = native_number([2, 64, 0], 'Speed'), native_number([2, 65, 0], 'Speed')
            assert abs(wheel_speed) == abs(mill_speed) == 8, (wheel_speed, mill_speed)
            seeds = amount(state, 'minecraft:wheat_seeds')
            assert seeds in (0, 1), seeds
            outputs = [dict(row) for row in state['slots'] if row['inventory'] == 'container' and row.get('count')]
            for index, row in enumerate(outputs):
                state = move_item(state, {'inventory': 'container', 'slot': row['slot']},
                                  {'inventory': 'player', 'slot': 20 + index}, row['count'])
            done(stream, stream.close_container(session_id=state['session_id'], revision=state['revision']))
            assert quantity(stream, 'create:wheat_flour') == flour and quantity(stream, 'minecraft:wheat_seeds') == seeds
            # Remove only the real water source using the empty bucket; decay must
            # stop the same native network, not a fixture command changing its speed.
            done(stream, stream.select_slot(slot(stream, 'minecraft:bucket')))
            done(stream, stream.look_at(3.5, 64.5, -1.5))
            done(stream, stream.use_item())
            assert quantity(stream, 'minecraft:water_bucket') == 1
            wait_for(lambda: block([3, 64, 0])['block'] != 'minecraft:water', timeout=15, description='flow decays after source collection')
            ticks(80)
            assert native_number([2, 64, 0], 'Speed') == native_number([2, 65, 0], 'Speed') == 0
            state = opened(stream.open_container(2, 65, 0))
            state = move_item(state, {'inventory': 'player', 'slot': slot(stream, 'minecraft:wheat')},
                              {'inventory': 'container', 'slot': 0}, 1)
            ticks(170)
            state = stream.observe()['container']
            assert amount(state, 'minecraft:wheat') == 1 and amount(state, 'create:wheat_flour') == 0
            done(stream, stream.close_container(session_id=state['session_id'], revision=state['revision']))
            done(stream, stream.select_slot(8))
            # From the elevated flume the top is visible; the ray to the north
            # face crosses the millstone top before reaching its requested face.
            done(stream, stream.use_on([2, 65, 0], face='up'))
            assert quantity(stream, 'minecraft:wheat') == 1 and quantity(stream, 'create:wheat_flour') == flour
            return {'sdk_placed': ['create:water_wheel', 'create:millstone'], 'water_source_placed_and_collected_via_sdk': True,
                    'observed_flow_level': flow['properties']['level'], 'waterwheel_rpm': wheel_speed, 'millstone_rpm': mill_speed,
                    'dry_before_and_after_source_removal': True, 'wheat_initial': 2, 'wheat_remaining': 1, 'actual_flour_roll': flour,
                    'actual_seed_roll': seeds, 'water_bucket_conserved': 1, 'machine_output_or_energy_injected': False,
                    'seeded': ['stone flume/platform', 'one waterwheel item', 'one millstone item', 'one filled water bucket', 'two wheat'],
                    'telemetry_oracle': 'native SDK output plus read-only console speed; no survival crafting claim'}

        fixture.case('create_sdk_waterwheel_flow_powers_and_stops_native_millstone',
                     ['ACT-08', 'ACT-09', 'ACT-10', 'ACT-13', 'ACT-14', 'VERIFY-03', 'MOD-01', 'MOD-03'], waterwheel_powers_native_milling)
    finally:
        try:
            stream.stop()
        finally:
            with fixture.gateway.changed:
                body = fixture.gateway.body('VerifyBuilder')
                body['data']['area'] = previous_area
                fixture.gateway.save(body)
