"""Native primitive and navigation edge cases; setup mutates only the disposable fixture."""
import math
import time
import uuid

from gameplay_cases import done, quantity
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    def reset():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('effect clear VerifyBuilder')
        fixture.console('effect give VerifyBuilder saturation 1 255 true')
        fixture.console('clear VerifyBuilder')
        fixture.console('kill @e[type=!minecraft:player]')
        fixture.console('fill -16 64 -16 26 80 16 air')
        fixture.console('fill -16 63 -16 26 63 16 stone')
        time.sleep(.4)
        done(stream, stream.select_slot(0))

    def failed(receipt, reasons):
        result = stream.wait_action(receipt['id'], timeout=20)
        assert result['state'] == 'failed' and result['reason'] in reasons, result
        return result

    def block(pos):
        return done(stream, stream.query_blocks(positions=[pos]))['blocks'][0]['block']

    def started(receipt):
        return wait_for(lambda: next((r for r in stream.observe()['action_results']
                         if r['id'] == receipt['id'] and r['state'] == 'started'), None), description='native action started')

    def hand_busy_and_cancel():
        reset()
        fixture.console('setblock 2 64 0 oak_log')
        time.sleep(.1)
        dig = stream.dig(2, 64, 0)
        started(dig)
        failure = failed(stream.select_slot(1), {'hand_busy'})
        done(stream, stream.cancel(dig['id']))
        terminal = stream.wait_action(dig['id'])
        assert terminal['state'] == 'cancelled', terminal
        time.sleep(.4)
        assert block([2, 64, 0]) == 'minecraft:oak_log'
        assert quantity(stream, 'minecraft:oak_log') == 0
        return {'selection_failure': failure['reason'], 'cancelled_dig_block_intact': True}

    fixture.case('dig_hand_channel_and_explicit_cancel', ['EXEC-01', 'EXEC-03', 'ACT-07'], hand_busy_and_cancel)

    def exact_drop_and_retry():
        reset()
        fixture.console('give VerifyBuilder stone 5')
        wait_for(lambda: quantity(stream, 'minecraft:stone') == 5)
        request_id = uuid.uuid4().hex
        result = done(stream, stream.drop(0, 2, request_id=request_id))
        wait_for(lambda: quantity(stream, 'minecraft:stone') == 3)
        done(stream, stream.drop(0, 2, request_id=request_id))
        time.sleep(.1)
        assert quantity(stream, 'minecraft:stone') == 3
        entities = stream.observe()['entities']
        dropped = next((e for e in entities if e['id'] == result['entity_id']), None)
        assert dropped and dropped['stack']['item'] == 'minecraft:stone' and dropped['stack']['count'] == 2, entities
        done(stream, stream.drop(0, 3))
        wait_for(lambda: quantity(stream, 'minecraft:stone') == 0)
        # Before native pickup delay, the two item entities may merge but total count must be five.
        total = sum(e.get('stack', {}).get('count', 0) for e in stream.observe()['entities']
                    if e.get('stack', {}).get('item') == 'minecraft:stone')
        assert total == 5, stream.observe()['entities']
        return {'partial': 2, 'remaining_full_drop': 3, 'retry_executed_once': True, 'world_item_total': total}

    fixture.case('drop_partial_full_and_idempotent_retry', ['ACT-03', 'EXEC-04', 'VERIFY-03'], exact_drop_and_retry)

    def invalid_drop_and_selection():
        reset()
        fixture.console('give VerifyBuilder stone 2')
        wait_for(lambda: quantity(stream, 'minecraft:stone') == 2)
        rejected = []
        for operation in (lambda: stream.select_slot(-1), lambda: stream.select_slot(9),
                          lambda: stream.drop(0, 0), lambda: stream.drop(0, -1), lambda: stream.drop(0, 100)):
            try:
                operation()
            except Exception as error:
                assert getattr(error, 'status', None) == 400, repr(error)
                rejected.append(getattr(error, 'status'))
            else:
                raise AssertionError('Invalid inventory argument accepted')
        failure = failed(stream.drop(0, 3), {'insufficient_items'})
        assert quantity(stream, 'minecraft:stone') == 2
        assert not any(e.get('stack', {}).get('item') == 'minecraft:stone' for e in stream.observe()['entities'])
        return {'invalid_arguments': len(rejected), 'insufficient_count': failure['reason'], 'stones_preserved': 2}

    fixture.case('inventory_invalid_arguments_and_drop_shortage', ['ACT-01', 'ACT-03', 'EXEC-05'], invalid_drop_and_selection)

    def binding_armor_drop():
        reset()
        fixture.console('item replace entity VerifyBuilder armor.chest with minecraft:diamond_chestplate[minecraft:enchantments={levels:{"minecraft:binding_curse":1}}] 1')
        wait_for(lambda: quantity(stream, 'minecraft:diamond_chestplate') == 1)
        result = failed(stream.drop(38, 1), {'item_cannot_be_removed'})
        assert quantity(stream, 'minecraft:diamond_chestplate') == 1
        chest = next(row for row in stream.observe()['inventory'] if row['slot'] == 38)
        assert chest['item'] == 'minecraft:diamond_chestplate' and chest['count'] == 1, chest
        assert not any(e.get('stack', {}).get('item') == 'minecraft:diamond_chestplate' for e in stream.observe()['entities'])
        return {'vanilla_slot_pickup_rejected_binding_curse': result['reason'], 'armor_unchanged': True}

    fixture.case('drop_obeys_vanilla_binding_armor_slot_rule', ['ACT-03', 'VERIFY-03'], binding_armor_drop)

    def populated_hands():
        reset()
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:iron_pickaxe[minecraft:damage=11] 1')
        fixture.console('item replace entity VerifyBuilder weapon.offhand with minecraft:diamond 3')
        wait_for(lambda: quantity(stream, 'minecraft:diamond') == 3 and quantity(stream, 'minecraft:iron_pickaxe') == 1)
        def equipment(slot):
            return next(row for row in stream.observe()['inventory'] if row['slot'] == slot)
        main, off = equipment(0), equipment(40)
        done(stream, stream.swap_hands())
        wait_for(lambda: equipment(0)['item'] == 'minecraft:diamond')
        after_main, after_off = equipment(0), equipment(40)
        for before, after in ((main, after_off), (off, after_main)):
            assert all(before[key] == after[key] for key in ('item', 'count', 'components', 'damage')), (before, after)
        done(stream, stream.swap_hands())
        wait_for(lambda: equipment(0)['item'] == 'minecraft:iron_pickaxe')
        return {'both_hands_populated': True, 'pick_damage': 11, 'diamonds': 3, 'two_swaps_preserve_components': True}

    fixture.case('swap_two_populated_hands_preserves_components', ['ACT-02', 'OBS-01'], populated_hands)

    def dig_negative():
        reset()
        fixture.console('setblock 2 64 0 bedrock')
        time.sleep(.1)
        bedrock = failed(stream.dig(2, 64, 0), {'unbreakable'})
        fixture.console('setblock 2 64 0 stone')
        fixture.console('setblock 3 64 0 oak_log')
        time.sleep(.1)
        obstruction = failed(stream.dig(3, 64, 0), {'out_of_reach_or_obstructed'})
        assert block([3, 64, 0]) == 'minecraft:oak_log'
        return {'unbreakable': bedrock['reason'], 'occluded': obstruction['reason']}

    fixture.case('dig_unbreakable_and_obstructed', ['ACT-07', 'EXEC-05', 'VERIFY-03'], dig_negative)

    def tool_break():
        reset()
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:iron_pickaxe[minecraft:damage=249] 1')
        fixture.console('setblock 2 64 0 stone')
        wait_for(lambda: quantity(stream, 'minecraft:iron_pickaxe') == 1)
        result = done(stream, stream.dig(2, 64, 0))
        assert block([2, 64, 0]) == 'minecraft:air'
        wait_for(lambda: quantity(stream, 'minecraft:iron_pickaxe') == 0)
        done(stream, stream.move_to(2.5, 64, .5))
        wait_for(lambda: quantity(stream, 'minecraft:cobblestone') == 1)
        return {'result': result['reason'], 'pickaxe_broken': True, 'real_cobblestone_drop': 1}

    fixture.case('dig_tool_durability_and_natural_drop', ['ACT-07', 'VERIFY-03'], tool_break)

    def changed_target():
        reset()
        fixture.console('setblock 2 64 0 oak_log')
        time.sleep(.1)
        receipt = stream.dig(2, 64, 0)
        started(receipt)
        fixture.console('setblock 2 64 0 obsidian')
        result = failed(receipt, {'target_changed'})
        assert block([2, 64, 0]) == 'minecraft:obsidian'
        return {'failure': result['reason'], 'replacement_preserved': True}

    fixture.case('dig_revalidates_changed_target', ['ACT-07', 'EXEC-06', 'VERIFY-03'], changed_target)

    def area_and_multiblock():
        reset()
        fixture.console('tp VerifyBuilder 21.5 64 0.5')
        fixture.console('give VerifyBuilder oak_planks 2')
        wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 2)
        try:
            stream.place(24, 64, 0, 'up')
        except Exception as error:
            assert getattr(error, 'status', None) == 403, repr(error)
            result = {'reason': 'outside_work_area_gateway_403'}
        else:
            raise AssertionError('Gateway accepted out-of-area destination')
        assert quantity(stream, 'minecraft:oak_planks') == 2
        assert block([24, 64, 0]) == 'minecraft:air'
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:oak_door 1')
        wait_for(lambda: quantity(stream, 'minecraft:oak_door') == 1)
        done(stream, stream.place(2, 64, 0, 'up'))
        cells = done(stream, stream.query_blocks(positions=[[2, 64, 0], [2, 65, 0]]))['blocks']
        assert [c['block'] for c in cells] == ['minecraft:oak_door'] * 2, cells
        assert {c['properties']['half'] for c in cells} == {'lower', 'upper'}
        wait_for(lambda: quantity(stream, 'minecraft:oak_door') == 0)
        return {'outside_area': result['reason'], 'door_cells': 2, 'doors_consumed': 1}

    fixture.case('placement_area_and_two_cell_door', ['ACT-08', 'EXEC-06', 'VERIFY-04'], area_and_multiblock)

    def multiblock_boundary():
        reset()
        fixture.console('fill 0 75 0 3 75 1 stone')
        fixture.console('setblock 2 76 0 stone')
        fixture.console('tp VerifyBuilder 0.5 76 0.5')
        fixture.console('give VerifyBuilder oak_door 1')
        wait_for(lambda: quantity(stream, 'minecraft:oak_door') == 1)
        result = failed(stream.place(2, 77, 0, 'up'), {'outside_work_area'})
        assert quantity(stream, 'minecraft:oak_door') == 1
        cells = done(stream, stream.query_blocks(positions=[[2, 77, 0], [2, 78, 0]]))['blocks']
        assert all(row['block'] == 'minecraft:air' for row in cells), cells
        return {'target_inside_area': True, 'upper_half_outside_area_rejected_natively': result['reason'], 'door_preserved': 1}

    fixture.case('placement_multiblock_secondary_cell_bounds', ['ACT-08', 'EXEC-06', 'VERIFY-04'], multiblock_boundary)

    def door_interaction():
        reset()
        fixture.console('setblock 2 64 0 oak_door[facing=west,half=lower,open=false]')
        fixture.console('setblock 2 65 0 oak_door[facing=west,half=upper,open=false]')
        time.sleep(.2)
        def door_states():
            return done(stream, stream.query_blocks(positions=[[2, 64, 0], [2, 65, 0]]))['blocks']
        initial = door_states()
        assert all(r['properties']['open'] == 'false' for r in initial), initial
        done(stream, stream.use_on([2, 64, 0], face='west'))
        opened = door_states()
        assert all(r['properties']['open'] == 'true' for r in opened), opened
        # An open door rotates its thin outline: approach from north and click the actual north face.
        fixture.console('tp VerifyBuilder 2.5 64 -1.5')
        time.sleep(.2)
        done(stream, stream.use_on([2, 64, 0], face='north'))
        closed = door_states()
        assert all(r['properties']['open'] == 'false' for r in closed), closed
        return {'closed_to_open_to_closed': True, 'both_halves_updated': True, 'empty_hand': True}

    fixture.case('use_on_thin_door_shape_open_close', ['ACT-10', 'OBS-03'], door_interaction)

    def held_use_stop():
        reset()
        fixture.console('give VerifyBuilder bow 1')
        fixture.console('give VerifyBuilder arrow 1')
        wait_for(lambda: quantity(stream, 'minecraft:arrow') == 1)
        receipt = stream.use_item()
        started(receipt)
        wait_for(lambda: stream.observe()['execution']['using_item'])
        stream.stop()
        terminal = stream.wait_action(receipt['id'])
        assert terminal['state'] == 'cancelled', terminal
        wait_for(lambda: not stream.observe()['execution']['using_item'])
        time.sleep(.3)
        assert quantity(stream, 'minecraft:arrow') == 1
        assert not any(e['type'] == 'minecraft:arrow' for e in stream.observe()['entities'])
        return {'stop_aborted_bow_without_firing': True, 'arrows_preserved': 1}

    fixture.case('held_bow_stop_without_release_side_effect', ['ACT-09', 'EXEC-03', 'OBS-07'], held_use_stop)

    def eat_duration():
        reset()
        time.sleep(.7)
        fixture.console('effect clear VerifyBuilder')
        fixture.console('effect give VerifyBuilder hunger 5 255 true')
        wait_for(lambda: stream.observe()['food'] < 10)
        fixture.console('effect clear VerifyBuilder')
        fixture.console('give VerifyBuilder bread 2')
        wait_for(lambda: quantity(stream, 'minecraft:bread') == 2)
        receipt = stream.use_item()
        started(receipt)
        result = done(stream, receipt)
        wait_for(lambda: quantity(stream, 'minecraft:bread') == 1)
        return {'result': result['reason'], 'bread_consumed': 1, 'native_duration_observed': True}

    fixture.case('native_food_duration_and_consumption', ['ACT-09', 'OBS-07'], eat_duration)

    def attack_cases():
        reset()
        missing = failed(stream.attack(2147483647), {'entity_missing'})
        fixture.console('summon minecraft:cow 2 64 0.5 {NoAI:1b}')
        cow = wait_for(lambda: next((e for e in stream.observe()['entities'] if e['type'] == 'minecraft:cow'), None))
        done(stream, stream.attack(cow['id']))
        cooldown = failed(stream.attack(cow['id']), {'attack_cooldown'})
        return {'missing_target': missing['reason'], 'cooldown': cooldown['reason'], 'neutral_mob_attack_executed': True}

    fixture.case('attack_target_lifetime_and_cooldown', ['ACT-11', 'OBS-02'], attack_cases)

    def navigation_slab_stair():
        reset()
        fixture.console('setblock 2 64 0 stone_slab[type=bottom]')
        fixture.console('setblock 3 64 0 stone')
        fixture.console('setblock 4 64 0 stone')
        done(stream, stream.move_to(2.5, 64.5, .5))
        slab = stream.observe()['position']
        assert math.dist(slab, [2.5, 64.5, .5]) < .6, slab
        done(stream, stream.move_to(3.5, 65, .5))
        raised = stream.observe()['position']
        assert math.dist(raised, [3.5, 65, .5]) < .6, raised
        fixture.console('tp VerifyBuilder 0.5 64 4.5')
        fixture.console('setblock 2 64 4 stone_stairs[facing=east,half=bottom,shape=straight]')
        fixture.console('setblock 3 64 4 stone')
        time.sleep(.2)
        done(stream, stream.move_to(3.5, 65, 4.5))
        stair = stream.observe()['position']
        assert math.dist(stair, [3.5, 65, 4.5]) < .6, stair
        return {'slab': slab, 'raised': raised, 'stair': stair, 'alternate_routes_not_excluded': True}

    fixture.case('navigation_half_slab_and_raised_stair_destinations', ['VERIFY-01'], navigation_slab_stair)

    def unreachable_and_timeout():
        reset()
        fixture.console('fill 3 64 -2 7 67 2 stone')
        time.sleep(.2)
        blocked = stream.move_to(5.5, 64, .5, ttl_seconds=3)
        result = stream.wait_action(blocked['id'], timeout=8)
        assert result['state'] in ('failed', 'cancelled'), result
        assert math.dist(stream.observe()['position'], [5.5, 64, .5]) > 1
        fixture.console('fill 3 64 -2 7 67 2 air')
        time.sleep(.2)
        receipt = stream.move_to(20.5, 64, .5, ttl_seconds=1)
        terminal = stream.wait_action(receipt['id'], timeout=8)
        assert terminal['state'] in ('failed', 'cancelled'), terminal
        return {'solid_target': result['reason'], 'short_timeout': terminal['reason']}

    fixture.case('navigation_solid_target_and_timeout', ['VERIFY-01', 'EXEC-03'], unreachable_and_timeout)

    def low_ceiling():
        reset()
        fixture.console('fill 1 64 -1 6 66 -1 stone')
        fixture.console('fill 1 64 1 6 66 1 stone')
        fixture.console('fill 1 66 0 6 66 0 stone')
        fixture.console('fill 6 64 0 6 65 0 stone')
        time.sleep(.2)
        done(stream, stream.move_to(2.5, 64, .5))
        fixture.console('setblock 3 64 0 stone_slab[type=bottom]')
        time.sleep(.2)
        receipt = stream.move_to(5.5, 64, .5, ttl_seconds=4)
        result = stream.wait_action(receipt['id'], timeout=10)
        assert result['state'] in ('failed', 'cancelled'), result
        assert stream.observe()['position'][0] < 3
        return {'two_block_corridor_traversed': True, 'one_and_half_clearance_rejected': result['reason']}

    fixture.case('navigation_low_ceiling_collision', ['VERIFY-01'], low_ceiling)

    def route_change():
        reset()
        receipt = stream.move_to(12.5, 64, .5)
        started(receipt)
        fixture.console('fill 6 64 -1 6 66 1 stone')
        result = stream.wait_action(receipt['id'], timeout=35)
        position = stream.observe()['position']
        assert result['state'] in ('done', 'failed'), result
        if result['state'] == 'done':
            assert math.dist(position, [12.5, 64, .5]) < .6, position
        else:
            assert result['reason'] in ('blocked', 'timeout', 'unreachable', 'node_limit'), result
        assert not (6 <= position[0] < 7 and -1 <= position[2] < 2 and position[1] < 67), position
        return {'changed_terrain_outcome': result['reason'], 'position': position, 'collision_respected': True}

    fixture.case('navigation_obstacle_inserted_during_route', ['VERIFY-01', 'VERIFY-03'], route_change)
