"""Native optional-mod workstation cases. Run only with the exact locked full pack."""
import json
import time

from gameplay_cases import done, quantity, slot
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    if not getattr(fixture.args, 'full_pack_mods', None):
        return

    def reset():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('clear VerifyBuilder')
        fixture.console('kill @e[type=minecraft:item]')
        fixture.console('fill -3 64 -3 5 70 5 air')
        fixture.console('fill -3 63 -3 5 63 5 stone')
        time.sleep(.3)
        done(stream, stream.sneak(False))

    def opened(receipt):
        result = done(stream, receipt)
        if 'session_id' in result:
            return result
        return wait_for(lambda: stream.observe().get('container') if stream.observe().get('container', {}).get('open') else None)

    def transfer(state, source, destination, count):
        return opened(stream.move_item(source, destination, count, session_id=state['session_id'], revision=state['revision']))

    def storage(block):
        reset()
        fixture.console(f'setblock 2 64 0 {block}')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:iron_pickaxe[minecraft:damage=7,minecraft:custom_name=\'"Workstation tool"\'] 1')
        wait_for(lambda: quantity(stream, 'minecraft:iron_pickaxe') == 1)
        original = stream.inventory_slot(0)
        state = opened(stream.open_container(2, 64, 0))
        slots = [r for r in state['slots'] if r['inventory'] == 'container' and r['role'] == 'storage']
        assert len(slots) >= 27, state
        index = slots[-1]['slot']
        state = transfer(state, {'inventory': 'player', 'slot': 0}, {'inventory': 'container', 'slot': index}, 1)
        stored = stream.inventory_slot(index, inventory='container', session_id=state['session_id'], revision=state['revision'])
        assert stored['components'] == original['components'] and stored['count'] == 1
        done(stream, stream.close_container(session_id=state['session_id'], revision=state['revision']))
        state = opened(stream.open_container(2, 64, 0))
        state = transfer(state, {'inventory': 'container', 'slot': index}, {'inventory': 'player', 'slot': 1}, 1)
        returned = stream.inventory_slot(1)
        assert returned['components'] == original['components'] and quantity(stream, 'minecraft:iron_pickaxe') == 1
        return {'block': block, 'native_storage_slots': len(slots), 'last_storage_slot': index,
                'named_damaged_components_preserved': True, 'close_reopen_persistence': True,
                'upgrade_configuration_verified': False}

    for block in ('sophisticatedstorage:chest', 'sophisticatedstorage:barrel', 'sophisticatedstorage:shulker_box'):
        fixture.case('native_' + block.replace(':', '_') + '_menu_roundtrip', ['ACT-13', 'ACT-14', 'OBS-05', 'VERIFY-03', 'MOD-05'],
                     lambda block=block: storage(block))

    def portable_backpack():
        reset()
        fixture.console('item replace entity VerifyBuilder hotbar.0 with sophisticatedbackpacks:backpack 1')
        fixture.console('item replace entity VerifyBuilder hotbar.1 with minecraft:iron_pickaxe[minecraft:damage=9] 1')
        wait_for(lambda: quantity(stream, 'sophisticatedbackpacks:backpack') == quantity(stream, 'minecraft:iron_pickaxe') == 1)
        original = stream.inventory_slot(1)
        done(stream, stream.select_slot(0))
        state = opened(stream.use_item())
        assert state['kind'] == 'item_menu', state
        index = next(r['slot'] for r in state['slots'] if r['inventory'] == 'container' and r['role'] == 'storage')
        state = transfer(state, {'inventory': 'player', 'slot': 1}, {'inventory': 'container', 'slot': index}, 1)
        done(stream, stream.close_container(session_id=state['session_id'], revision=state['revision']))
        state = opened(stream.use_item())
        stored = stream.inventory_slot(index, inventory='container', session_id=state['session_id'], revision=state['revision'])
        assert stored['components'] == original['components']
        state = transfer(state, {'inventory': 'container', 'slot': index}, {'inventory': 'player', 'slot': 1}, 1)
        assert stream.inventory_slot(1)['components'] == original['components']
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:air')
        wait_for(lambda: not stream.observe().get('container', {}).get('open'), description='backpack item replacement invalidates menu')
        return {'native_item_use_open': True, 'damage_preserved': 9, 'native_backpack_context_invalidated': True,
                'backpack_held_slot': 0, 'worn_slot_and_upgrade_configuration_verified': False}

    fixture.case('native_portable_backpack_context_and_components', ['ACT-09', 'ACT-14', 'ACT-16', 'OBS-05', 'MOD-05'], portable_backpack)

    def cooking_pot():
        reset()
        fixture.console('setblock 2 64 0 farmersdelight:cooking_pot')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with farmersdelight:rice 1')
        fixture.console('item replace entity VerifyBuilder hotbar.1 with minecraft:bowl 2')
        wait_for(lambda: quantity(stream, 'farmersdelight:rice') == 1 and quantity(stream, 'minecraft:bowl') == 2)
        done(stream, stream.select_slot(8))
        recipe = stream.recipe('farmersdelight:cooking/cooked_rice')
        assert recipe['native_recipe']['type'] == 'farmersdelight:cooking' and recipe['native_recipe']['cookingtime'] == 100
        state = opened(stream.open_container(2, 64, 0))
        assert [r['role'] for r in state['slots'] if r['inventory'] == 'container'] == ['ingredient'] * 6 + ['meal_preview', 'serving_container', 'output']
        state = transfer(state, {'inventory': 'player', 'slot': 0}, {'inventory': 'container', 'slot': 0}, 1)
        state = transfer(state, {'inventory': 'player', 'slot': 1}, {'inventory': 'container', 'slot': 7}, 1)
        time.sleep(1)
        assert any(r['inventory'] == 'container' and r['slot'] == 0 and r.get('item') == 'farmersdelight:rice'
                   for r in stream.observe()['container']['slots'])
        fixture.console('setblock 2 63 0 minecraft:campfire[lit=true]')
        def cooked():
            current = stream.observe().get('container', {})
            return current if any(r['inventory'] == 'container' and r['slot'] == 8 and r.get('item') == 'farmersdelight:cooked_rice'
                                  for r in current.get('slots', [])) else None
        state = wait_for(cooked, timeout=15, description='native heated cooking pot produces served rice')
        state = transfer(state, {'inventory': 'container', 'slot': 8}, {'inventory': 'player', 'slot': 2}, 1)
        wait_for(lambda: quantity(stream, 'farmersdelight:cooked_rice') == 1)
        assert quantity(stream, 'farmersdelight:rice') == 0 and quantity(stream, 'minecraft:bowl') == 1
        assert not any(r['inventory'] == 'container' and r['count'] for r in state['slots'])
        return {'recipe': 'farmersdelight:cooking/cooked_rice', 'native_heat': 'lit campfire', 'unheated_input_unchanged': True,
                'rice_consumed': 1, 'served_meals': 1, 'bowls_initial': 2, 'empty_bowls_remaining': 1,
                'serving_bowl_in_meal': 1, 'output_injected': False}

    fixture.case('native_farmers_delight_pot_heat_and_serving', ['ACT-13', 'ACT-14', 'ACT-15', 'OBS-05', 'OBS-06', 'MOD-06'], cooking_pot)

    def cutting_board():
        reset()
        with fixture.gateway.changed:
            body = fixture.gateway.body('VerifyBuilder')
            previous = body['data'].get('area')
            body['data']['area'] = None
            fixture.gateway.save(body)
        tick = stream.observe()['world_tick']
        wait_for(lambda: stream.observe()['world_tick'] >= tick + 5)
        try:
            fixture.console('setblock 2 64 0 farmersdelight:cutting_board')
            fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:beef 1')
            fixture.console('item replace entity VerifyBuilder hotbar.1 with farmersdelight:iron_knife 1')
            wait_for(lambda: quantity(stream, 'minecraft:beef') == quantity(stream, 'farmersdelight:iron_knife') == 1)
            recipe = stream.recipe('farmersdelight:cutting/beef')
            assert recipe['native_recipe']['type'] == 'farmersdelight:cutting' and recipe['native_recipe']['tool']
            done(stream, stream.select_slot(0))
            done(stream, stream.use_on([2, 64, 0], face='up'))
            wait_for(lambda: quantity(stream, 'minecraft:beef') == 0)
            done(stream, stream.select_slot(1))
            done(stream, stream.use_on([2, 64, 0], face='up'))
            wait_for(lambda: stream.inventory_slot(1).get('damage') == 1)
            def mince_total():
                observation = stream.observe()
                return quantity(stream, 'farmersdelight:minced_beef') + sum(e.get('stack', {}).get('count', 0)
                    for e in observation['entities'] if e.get('stack', {}).get('item') == 'farmersdelight:minced_beef')
            wait_for(lambda: mince_total() == 2)
            return {'native_cutting_recipe': 'farmersdelight:cutting/beef', 'beef_consumed': 1, 'minced_beef_output': 2,
                    'knife_durability_consumed': 1, 'optional_area': None, 'bounded_callback_footprint_verified': False}
        finally:
            stream.stop()
            with fixture.gateway.changed:
                body = fixture.gateway.body('VerifyBuilder')
                body['data']['area'] = previous
                fixture.gateway.save(body)
            tick = stream.observe()['world_tick']
            wait_for(lambda: stream.observe()['world_tick'] >= tick + 5)

    fixture.case('native_farmers_delight_cutting_tool_and_output', ['ACT-10', 'OBS-06', 'VERIFY-03', 'MOD-06'], cutting_board)
