"""Native Create fluid observations and processing; no capability writes or seeded outputs."""
import time
from contextlib import contextmanager

from gameplay_cases import done, quantity, slot
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    if not getattr(fixture.args, 'full_pack_mods', None):
        return

    @contextmanager
    def area(value):
        with fixture.gateway.changed:
            body = fixture.gateway.body('VerifyBuilder')
            previous = body['data'].get('area')
            body['data']['area'] = value
            fixture.gateway.save(body)
        tick = stream.observe()['world_tick']
        wait_for(lambda: stream.observe()['world_tick'] >= tick + 5)
        try:
            yield
        finally:
            stream.stop()
            with fixture.gateway.changed:
                body = fixture.gateway.body('VerifyBuilder')
                body['data']['area'] = previous
                fixture.gateway.save(body)
            tick = stream.observe()['world_tick']
            wait_for(lambda: stream.observe()['world_tick'] >= tick + 5)

    def reset():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('fill -3 64 -3 7 72 5 air')
        fixture.console('fill -3 63 -3 7 63 5 stone')
        fixture.console('kill @e[type=minecraft:item]')
        fixture.console('clear VerifyBuilder')
        time.sleep(.3)
        wait_for(lambda: not any(r.get('count') for r in stream.observe()['inventory']))
        done(stream, stream.sneak(False))

    def opened(receipt):
        result = done(stream, receipt)
        return result if 'session_id' in result else stream.observe()['container']

    def current():
        return stream.observe().get('container', {})

    def fluid_total(state, name):
        return sum(row['amount_mB'] for row in state.get('fluids', []) if row['fluid'] == name)

    def failed(receipt, reason):
        result = stream.wait_action(receipt['id'], timeout=15)
        assert result['state'] == 'failed' and result['reason'] == reason, result
        return result

    def bucket_basin():
        reset()
        fixture.console('setblock 2 64 0 create:basin')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:water_bucket 1')
        wait_for(lambda: quantity(stream, 'minecraft:water_bucket') == 1)
        done(stream, stream.select_slot(0))
        done(stream, stream.use_on([2, 64, 0], face='west'))
        wait_for(lambda: quantity(stream, 'minecraft:bucket') == 1)
        state = opened(stream.open_container(2, 64, 0))
        assert fluid_total(state, 'minecraft:water') == 1000 and len(state['fluids']) == 4, state
        assert [r['role'] for r in state['fluids']] == ['output', 'output', 'input', 'input']
        assert all(r['capacity_mB'] == 1000 for r in state['fluids'])
        done(stream, stream.use_on([2, 64, 0], face='west'))
        wait_for(lambda: quantity(stream, 'minecraft:water_bucket') == 1 and fluid_total(current(), 'minecraft:water') == 0)
        failed(stream.move_item({'inventory': 'player', 'slot': 0}, {'inventory': 'container', 'slot': 0}, 1,
                               session_id=state['session_id'], revision=state['revision']), 'stale_container_revision')
        assert quantity(stream, 'minecraft:water_bucket') == 1 and quantity(stream, 'minecraft:bucket') == 0
        return {'native_fill_mB': 1000, 'native_withdraw_mB': 1000, 'bucket_count': 1,
                'basin_final_mB': 0, 'fluid_change_invalidates_revision': True,
                'native_bucket_interactions': True, 'direct_capability_writes': False}

    fixture.case('create_basin_native_bucket_fluid_roundtrip', ['ACT-10', 'OBS-05', 'MOD-09', 'VERIFY-03'], bucket_basin)

    def tank_multiblock():
        reset()
        fixture.console('setblock 2 64 0 create:fluid_tank')
        time.sleep(.5)
        first = opened(stream.open_container(2, 64, 0))
        assert first['kind'] == 'machine_fluid_port' and len(first['fluids']) == 1
        capacity = first['fluids'][0]['capacity_mB']
        assert capacity > 0 and first['fluids'][0]['amount_mB'] == 0
        done(stream, stream.close_container(session_id=first['session_id'], revision=first['revision']))
        fixture.console('setblock 2 65 0 create:fluid_tank')
        time.sleep(.6)
        formed = opened(stream.open_container(2, 64, 0))
        assert len(formed['fluid_structure']) == 2 and formed['fluids'][0]['capacity_mB'] == capacity * 2, formed
        assert not any(r['inventory'] == 'container' for r in formed['slots'])
        limited = {'dimension': 'minecraft:overworld', 'min': [-3, 60, -3], 'max': [6, 65, 6]}
        with area(limited):
            assert not current().get('open'), current()
            failed(stream.open_container(2, 64, 0), 'outside_work_area')
        reopened = opened(stream.open_container(2, 64, 0))
        assert reopened['fluids'][0]['amount_mB'] == 0 and reopened['fluids'][0]['capacity_mB'] == capacity * 2
        return {'single_capacity_mB': capacity, 'double_capacity_mB': capacity * 2,
                'native_multiblock_members': 2, 'out_of_area_upper_member_rejected': True,
                'all_reads_preserved_empty_fluid': True, 'survival_direct_tank_bucket_exchange_supported': False}

    fixture.case('create_fluid_tank_multiblock_observation_and_bounds', ['ACT-13', 'OBS-05', 'MOD-09'], tank_multiblock)

    def item_drain():
        reset()
        fixture.console('setblock 2 64 0 create:item_drain')
        # A solid neighbor retains the processed bucket; a bare chest is not
        # a belt input and would require a native funnel for automatic insertion.
        fixture.console('setblock 3 64 0 minecraft:stone')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:water_bucket 1')
        wait_for(lambda: quantity(stream, 'minecraft:water_bucket') == 1)
        readonly = opened(stream.open_container(2, 64, 0))
        assert readonly['kind'] == 'machine_fluid_port' and not any(r['inventory'] == 'container' for r in readonly['slots'])
        failed(stream.open_container(2, 64, 0, face='up'), 'unsupported_item_port_face')
        state = opened(stream.open_container(2, 64, 0, face='west'))
        assert state['item_port_face'] == 'west' and len([r for r in state['slots'] if r['inventory'] == 'container']) == 1
        opened(stream.move_item({'inventory': 'player', 'slot': 0}, {'inventory': 'container', 'slot': 0}, 1,
                               session_id=state['session_id'], revision=state['revision']))
        processed = wait_for(lambda: current() if fluid_total(current(), 'minecraft:water') == 1000 else None,
                             timeout=15, description='native item drain empties the actual bucket')
        assert quantity(stream, 'minecraft:water_bucket') == 0
        processed = wait_for(lambda: current() if any(r['inventory'] == 'container' and r.get('item') == 'minecraft:bucket'
                                                     for r in current().get('slots', [])) else None,
                             timeout=10, description='drain exposes actual empty-bucket remainder')
        opened(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 1,
                               session_id=processed['session_id'], revision=processed['revision']))
        wait_for(lambda: quantity(stream, 'minecraft:bucket') == 1)
        final = opened(stream.open_container(2, 64, 0))
        assert fluid_total(final, 'minecraft:water') == 1000
        return {'input_water_bucket': 1, 'native_fluid_output_mB': 1000, 'empty_buckets_recovered': 1,
                'native_item_input_face': 'west', 'remainder_recovered_through_native_handler': True,
                'read_only_unsided_port': True, 'direct_capability_writes': False}

    fixture.case('create_item_drain_sided_input_native_emptying', ['ACT-13', 'ACT-14', 'OBS-05', 'MOD-09', 'VERIFY-03'], item_drain)

    def fluid_mixing():
        reset()
        fixture.console('setblock 2 64 0 create:basin')
        fixture.console('setblock 2 66 0 create:mechanical_mixer')
        fixture.console('setblock 3 66 0 create:cogwheel[axis=y]')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:water_bucket 1')
        fixture.console('item replace entity VerifyBuilder hotbar.1 with create:wheat_flour 1')
        wait_for(lambda: quantity(stream, 'minecraft:water_bucket') == quantity(stream, 'create:wheat_flour') == 1)
        recipe = stream.recipe('create:mixing/dough_by_mixing')
        assert any(i.get('fluid') == 'minecraft:water' and i.get('amount') == 1000 for i in recipe['native_recipe']['ingredients'])
        done(stream, stream.select_slot(0))
        done(stream, stream.use_on([2, 64, 0], face='west'))
        wait_for(lambda: quantity(stream, 'minecraft:bucket') == 1)
        state = opened(stream.open_container(2, 64, 0))
        state = opened(stream.move_item({'inventory': 'player', 'slot': 1}, {'inventory': 'container', 'slot': 0}, 1,
                                       session_id=state['session_id'], revision=state['revision']))
        time.sleep(1)
        assert fluid_total(current(), 'minecraft:water') == 1000
        fixture.console('setblock 3 67 0 create:creative_motor[facing=down]{ScrollValue:64}')
        def dough():
            value = current()
            return value if any(r['inventory'] == 'container' and r.get('item') == 'create:dough' for r in value.get('slots', [])) else None
        state = wait_for(dough, timeout=20, description='native mixer consumes real flour and bucket water')
        assert fluid_total(state, 'minecraft:water') == 0 and quantity(stream, 'minecraft:bucket') == 1
        source = next(r['slot'] for r in state['slots'] if r['inventory'] == 'container' and r.get('item') == 'create:dough')
        opened(stream.move_item({'inventory': 'container', 'slot': source}, {'inventory': 'player', 'slot': 1}, 1,
                               session_id=state['session_id'], revision=state['revision']))
        wait_for(lambda: quantity(stream, 'create:dough') == 1)
        return {'recipe': 'create:mixing/dough_by_mixing', 'flour_consumed': 1, 'water_consumed_mB': 1000,
                'dough_output': 1, 'empty_buckets_preserved': 1, 'unpowered_fluid_preserved': True,
                'power': 'fixture-seeded native creative motor64rpm', 'fluid_or_output_injected': False}

    fixture.case('create_mixer_native_item_and_fluid_processing', ['ACT-10', 'ACT-14', 'ACT-15', 'OBS-05', 'OBS-06', 'MOD-09', 'VERIFY-03'], fluid_mixing)

    def heated_fluid_mixing():
        with area(None):
            reset()
            fixture.console('setblock 2 64 0 create:blaze_burner[blaze=smouldering]')
            fixture.console('setblock 2 65 0 create:basin')
            fixture.console('setblock 2 67 0 create:mechanical_mixer')
            fixture.console('setblock 3 67 0 create:cogwheel[axis=y]')
            fixture.console('setblock 3 68 0 create:creative_motor[facing=down]{ScrollValue:64}')
            for index, item in enumerate(('minecraft:water_bucket', 'minecraft:milk_bucket', 'minecraft:oak_leaves', 'minecraft:coal')):
                fixture.console(f'item replace entity VerifyBuilder hotbar.{index} with {item} 1')
            wait_for(lambda: quantity(stream, 'minecraft:water_bucket') == quantity(stream, 'minecraft:milk_bucket') == 1)
            recipe = stream.recipe('create:mixing/tea')
            assert recipe['native_recipe']['heat_requirement'] == 'heated'
            for index in (0, 1):
                done(stream, stream.select_slot(index))
                done(stream, stream.use_on([2, 65, 0], face='west'))
            wait_for(lambda: quantity(stream, 'minecraft:bucket') == 2)
            state = opened(stream.open_container(2, 65, 0))
            milk_rows = [r for r in state['fluids'] if not r['empty'] and r['fluid'] != 'minecraft:water']
            assert len(milk_rows) == 1 and milk_rows[0]['amount_mB'] == 1000, state
            milk_id = milk_rows[0]['fluid']
            state = opened(stream.move_item({'inventory': 'player', 'slot': 2}, {'inventory': 'container', 'slot': 0}, 1,
                                           session_id=state['session_id'], revision=state['revision']))
            time.sleep(1)
            assert fluid_total(current(), 'minecraft:water') == fluid_total(current(), milk_id) == 1000
            assert fluid_total(current(), 'create:tea') == 0
            done(stream, stream.select_slot(3))
            done(stream, stream.use_on([2, 64, 0], face='west'))
            wait_for(lambda: quantity(stream, 'minecraft:coal') == 0)
            state = wait_for(lambda: current() if fluid_total(current(), 'create:tea') == 500 else None,
                             timeout=25, description='native fueled heated mixer makes tea from actual fluids')
            assert fluid_total(state, 'minecraft:water') == fluid_total(state, milk_id) == 750, state
            assert quantity(stream, 'minecraft:bucket') == 2
            assert not any(r['inventory'] == 'container' and r.get('item') == 'minecraft:oak_leaves' for r in state['slots'])
            return {'recipe': 'create:mixing/tea', 'water_input_mB': 1000, 'milk_input_mB': 1000,
                    'water_remaining_mB': 750, 'milk_remaining_mB': 750, 'native_tea_output_mB': 500,
                    'empty_buckets_preserved': 2, 'coal_consumed': 1, 'leaves_consumed': 1,
                    'unheated_inputs_preserved': True, 'power': 'fixture-seeded native creative motor64rpm',
                    'burner': 'fixture-seeded captured blaze; actual held coal supplies heat',
                    'fluid_or_output_injected': False, 'owner_area': None}

    fixture.case('create_heated_native_fluid_recipe_conservation', ['ACT-10', 'ACT-14', 'ACT-15', 'OBS-05', 'OBS-06', 'MOD-09', 'VERIFY-03'], heated_fluid_mixing)

    def drain_pump_spout():
        reset()
        fixture.console('tp VerifyBuilder 4.5 64 -2.5')
        fixture.console('setblock 2 64 0 create:depot')
        fixture.console('setblock 2 66 0 create:spout')
        fixture.console('setblock 3 66 0 create:mechanical_pump[facing=west]')
        fixture.console('setblock 4 66 0 create:item_drain')
        fixture.console('setblock 5 66 0 minecraft:stone')
        fixture.console('setblock 3 66 1 create:cogwheel[axis=x]')
        fixture.console('setblock 4 66 1 create:creative_motor[facing=west]{ScrollValue:64}')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:water_bucket 1')
        fixture.console('item replace entity VerifyBuilder hotbar.1 with minecraft:bucket 1')
        wait_for(lambda: quantity(stream, 'minecraft:water_bucket') == quantity(stream, 'minecraft:bucket') == 1)
        state = opened(stream.open_container(4, 66, 0, face='west'))
        opened(stream.move_item({'inventory': 'player', 'slot': 0}, {'inventory': 'container', 'slot': 0}, 1,
                               session_id=state['session_id'], revision=state['revision']))
        state = wait_for(lambda: current() if fluid_total(current(), 'minecraft:water') == 0 and any(r['inventory'] == 'container' and r.get('item') == 'minecraft:bucket'
                                                 for r in current().get('slots', [])) else None,
                         timeout=20, description='native drain returns empty source bucket and pump transfers its water')
        opened(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 1,
                               session_id=state['session_id'], revision=state['revision']))
        wait_for(lambda: quantity(stream, 'minecraft:bucket') == 2)
        fixture.console('tp VerifyBuilder 2.5 64 -2.5')
        opened(stream.open_container(2, 66, 0))
        state = wait_for(lambda: current() if fluid_total(current(), 'minecraft:water') == 1000 else None,
                         timeout=20, description='actual powered native pump transfers drain water to spout')
        assert state['kind'] == 'machine_fluid_port' and state['fluids'][0]['role'] == 'input'
        depot = opened(stream.open_container(2, 64, 0))
        source = slot(stream, 'minecraft:bucket')
        opened(stream.move_item({'inventory': 'player', 'slot': source}, {'inventory': 'container', 'slot': 0}, 1,
                               session_id=depot['session_id'], revision=depot['revision']))
        def filled():
            state = current()
            return state if any(r['inventory'] == 'container' and r.get('item') == 'minecraft:water_bucket'
                                for r in state.get('slots', [])) else None
        depot = wait_for(filled, timeout=20, description='native spout fills actual bucket over depot')
        source = next(r['slot'] for r in depot['slots'] if r['inventory'] == 'container' and r.get('item') == 'minecraft:water_bucket')
        opened(stream.move_item({'inventory': 'container', 'slot': source}, {'inventory': 'player', 'slot': 2}, 1,
                               session_id=depot['session_id'], revision=depot['revision']))
        wait_for(lambda: quantity(stream, 'minecraft:water_bucket') == quantity(stream, 'minecraft:bucket') == 1)
        spout = opened(stream.open_container(2, 66, 0))
        assert fluid_total(spout, 'minecraft:water') == 0, spout
        fixture.console('tp VerifyBuilder 4.5 64 -2.5')
        drain = opened(stream.open_container(4, 66, 0))
        assert fluid_total(drain, 'minecraft:water') == 0, drain
        return {'initial_water_bucket': 1, 'initial_empty_bucket': 1, 'final_water_bucket': 1, 'final_empty_bucket': 1,
                'native_pumped_water_mB': 1000, 'final_spout_mB': 0, 'final_drain_mB': 0,
                'native_spout_bucket_filling': True, 'native_drain_bucket_emptying': True,
                'power': 'fixture-seeded native creative motor64rpm', 'fluid_or_output_injected': False}

    fixture.case('create_native_drain_pump_spout_bucket_conservation', ['ACT-13', 'ACT-14', 'OBS-05', 'MOD-09', 'VERIFY-03'], drain_pump_spout)
