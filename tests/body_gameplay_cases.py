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
        wait_for(lambda: stream.observe()['world_tick'] >= terminal['tick'] + 90, timeout=12)
        assert block([2, 64, 0]) == 'minecraft:oak_log'
        assert quantity(stream, 'minecraft:oak_log') == 0
        return {'selection_failure': failure['reason'], 'cancelled_dig_block_intact': True}

    fixture.case('dig_hand_channel_and_explicit_cancel', ['EXEC-01', 'EXEC-03', 'ACT-07'], hand_busy_and_cancel)

    def pickup_changes_empty_hand():
        reset()
        fixture.console('item replace entity VerifyBuilder hotbar.0 with crafting_table 1')
        fixture.console('item replace entity VerifyBuilder hotbar.1 with jungle_log 1')
        fixture.console('setblock 2 64 0 oak_log')
        done(stream, stream.select_slot(2))
        assert next(r for r in stream.observe()['inventory'] if r['slot'] == 2)['count'] == 0
        fixture.console('summon item 0.5 64 0.5 {Item:{id:"minecraft:dirt",count:1},PickupDelay:30s}')
        receipt = stream.dig(2, 64, 0)
        begin = started(receipt)
        result = failed(receipt, {'held_item_changed'})
        assert quantity(stream, 'minecraft:dirt') == 1, stream.observe()['inventory']
        # Ninety real world ticks exceed bare-hand oak-log completion (60 ticks).
        wait_for(lambda: stream.observe()['world_tick'] >= begin['tick'] + 90, timeout=12)
        assert block([2, 64, 0]) == 'minecraft:oak_log', 'Cancelled native mining completed after the receipt'
        assert quantity(stream, 'minecraft:dirt') == 1 and quantity(stream, 'minecraft:oak_log') == 0
        assert not any(e.get('stack', {}).get('item') == 'minecraft:oak_log' for e in stream.observe()['entities'])
        reconciled = stream.action_results(receipt['id'])[0]
        assert reconciled['state'] == 'failed' and reconciled['reason'] == 'held_item_changed', reconciled
        return {'failure': result['reason'], 'waited_native_ticks': 90, 'target_still_oak_log': True,
                'injected_dirt_picked_up': 1, 'unearned_log_drops': 0, 'reconciled_result_unchanged': True}

    fixture.case('dig_pickup_empty_hand_failure_cannot_destroy_later', ['ACT-07', 'EXEC-02', 'EXEC-03', 'EXEC-04'], pickup_changes_empty_hand)

    def dig_native_self_state_transition():
        reset()
        fixture.console('item replace entity VerifyBuilder hotbar.0 with iron_pickaxe 1')
        fixture.console('setblock 2 64 0 redstone_ore[lit=false]')
        wait_for(lambda: quantity(stream, 'minecraft:iron_pickaxe') == 1)
        receipt = stream.dig(2, 64, 0)
        started(receipt)
        during = done(stream, stream.query_blocks(positions=[[2, 64, 0]]))['blocks'][0]
        assert during['block'] == 'minecraft:redstone_ore' and during['properties']['lit'] == 'true', during
        result = done(stream, receipt)
        assert block([2, 64, 0]) == 'minecraft:air'
        done(stream, stream.move_to(2.5, 64, .5))
        wait_for(lambda: quantity(stream, 'minecraft:redstone') >= 4)
        redstone = quantity(stream, 'minecraft:redstone')
        assert 4 <= redstone <= 5, stream.observe()['inventory']
        tool = next(row for row in stream.observe()['inventory'] if row.get('item') == 'minecraft:iron_pickaxe')
        assert tool['damage'] == 1, tool
        return {'native_start_changed_lit_property': True, 'result': result['reason'],
                'redstone_drop_count': redstone, 'pickaxe_damage': 1}

    fixture.case('dig_preserves_native_redstone_start_transition', ['ACT-07', 'EXEC-02', 'OBS-03'], dig_native_self_state_transition)

    def interrupted_dig(mode):
        reset()
        fixture.console('setblock 2 64 0 oak_log')
        time.sleep(.1)
        receipt = stream.dig(2, 64, 0)
        begin = started(receipt)
        original_send = None
        bridge = None
        owner_client = None
        reconnect_needed = False
        try:
            if mode == 'stop':
                stream.stop()
            elif mode == 'lease_release':
                stream.close()
                reconnect_needed = True
            elif mode == 'grant_expiry':
                with fixture.gateway.changed:
                    bridge = fixture.gateway.body_connections['VerifyBuilder']
                    original_send = bridge.send
                    # Drop only grant delivery on this disposable bridge; observations
                    # continue, so 200ms expiry must actually cancel the native action.
                    bridge.send = lambda *args, **kwargs: None
            elif mode == 'human_stop':
                from scru_minecraft import AgentClient
                with fixture.gateway.changed:
                    owner = fixture.gateway.member('FixtureOwner')
                    token = fixture.gateway.issue(owner['name'], 'player', player_uuid=owner['uuid'])
                owner_client = AgentClient(stream.client.url, token, 'VerifyBuilder', allow_local_http=True, timeout=8)
                fixture.console('synagent order Agents stop')
                wait_for(lambda: fixture.gateway.body('VerifyBuilder')['data'].get('suspended'), description='native operator stop reached gateway')
                stream.close()
                reconnect_needed = True
                try:
                    stream.reconnect()
                except Exception as error:
                    assert getattr(error, 'status', None) == 423, repr(error)
                else:
                    raise AssertionError('Reconnection cleared a human stop')
            else:
                raise AssertionError(mode)
            wait_for(lambda: fixture.gateway.frames['VerifyBuilder']['world_tick'] >= begin['tick'] + 90,
                     timeout=12, description='past original native break completion time')
        finally:
            if bridge is not None:
                bridge.send = original_send
            if owner_client is not None:
                owner_client.resume()
            if reconnect_needed:
                stream.reconnect()
        result = stream.wait_action(receipt['id'], timeout=10)
        assert result['state'] == 'cancelled', result
        assert block([2, 64, 0]) == 'minecraft:oak_log', (mode, result)
        assert quantity(stream, 'minecraft:oak_log') == 0
        assert not any(e.get('stack', {}).get('item') == 'minecraft:oak_log' for e in stream.observe()['entities'])
        assert not stream.observe()['execution']['active_actions']
        return {'interruption': mode, 'outcome': result['reason'], 'waited_native_ticks': 90,
                'target_intact': True, 'log_drops': 0, 'explicit_owner_resume': mode == 'human_stop'}

    for interruption in ('stop', 'lease_release', 'grant_expiry', 'human_stop'):
        fixture.case('dig_' + interruption + '_cannot_destroy_later',
                     ['ACT-07', 'EXEC-02', 'EXEC-03', 'EXEC-04', 'VERIFY-04'],
                     lambda interruption=interruption: interrupted_dig(interruption))

    def native_enemy_classification():
        reset()
        for entity, position, extra in [('phantom', '4 69 0', ''), ('ghast', '10 69 0', ''),
                                         ('slime', '6 64 5', ',Size:0'), ('cow', '3 64 5', '')]:
            fixture.console('summon minecraft:' + entity + ' ' + position +
                            ' {NoAI:1b,Silent:1b,PersistenceRequired:1b,Invulnerable:1b' + extra + '}')
        expected = {'minecraft:phantom': True, 'minecraft:ghast': True, 'minecraft:slime': True, 'minecraft:cow': False}
        observed = wait_for(lambda: {e['type']: e['hostile'] for e in stream.observe()['entities'] if e['type'] in expected}
                            if all(any(e['type'] == kind for e in stream.observe()['entities']) for kind in expected) else None,
                            description='native Enemy-marker classification fixtures')
        assert observed == expected, observed
        return {'classification': observed, 'basis': 'native Enemy marker, not Monster inheritance',
                'ai_disabled_for_fixture': True}

    fixture.case('entity_hostility_uses_native_enemy_marker', ['OBS-02'], native_enemy_classification)

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

    def unsuitable_tool_native_speed_and_no_drop():
        reset()
        fixture.console('setblock 2 64 0 stone')
        time.sleep(.15)
        receipt = stream.dig(2, 64, 0)
        began = started(receipt)
        result = done(stream, receipt)
        assert result['tick'] - began['tick'] >= 140, (began, result)
        assert block([2, 64, 0]) == 'minecraft:air'
        assert quantity(stream, 'minecraft:cobblestone') == 0 and quantity(stream, 'minecraft:stone') == 0
        assert not any(e.get('stack', {}).get('item') in ('minecraft:cobblestone', 'minecraft:stone')
                       for e in stream.observe()['entities']), stream.observe()['entities']
        return {'bare_hand_stone_break_ticks': result['tick'] - began['tick'],
                'native_slow_break_allowed': True, 'no_harvest_drop_without_suitable_tool': True}

    fixture.case('dig_unsuitable_tool_uses_native_slow_break_without_drops', ['ACT-07', 'VERIFY-03'], unsuitable_tool_native_speed_and_no_drop)

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

    def unrestricted_policy(run):
        with fixture.gateway.changed:
            body = fixture.gateway.body('VerifyBuilder')
            previous = body['data'].get('area')
            body['data']['area'] = None
            fixture.gateway.save(body)
        policy_tick = stream.observe()['world_tick']
        wait_for(lambda: stream.observe()['world_tick'] >= policy_tick + 5)
        try:
            return run()
        finally:
            try:
                stream.stop()
            finally:
                # A failed dimension/reconnect case must not leave later tests
                # with unrestricted policy, even when its SDK socket is closed.
                with fixture.gateway.changed:
                    body = fixture.gateway.body('VerifyBuilder')
                    body['data']['area'] = previous
                    fixture.gateway.save(body)
                policy_tick = fixture.gateway.frames.get('VerifyBuilder', {}).get('world_tick', 0)
                wait_for(lambda: fixture.gateway.frames.get('VerifyBuilder', {}).get('world_tick', 0) >= policy_tick + 5)

    def unrestricted_bucket_and_bonemeal():
        reset()
        fixture.console('item replace entity VerifyBuilder hotbar.0 with bucket 1')
        fixture.console('setblock 2 64 0 water[level=0]')
        wait_for(lambda: quantity(stream, 'minecraft:bucket') == 1)
        done(stream, stream.look_at(2.5, 64.5, .5))
        done(stream, stream.use_item())
        wait_for(lambda: quantity(stream, 'minecraft:water_bucket') == 1)
        source = done(stream, stream.query_blocks(positions=[[2, 64, 0]]))['blocks'][0]
        assert source['block'] != 'minecraft:water' or source['properties'].get('level') != '0', source
        done(stream, stream.look_at(4.5, 64, .5))
        done(stream, stream.use_item())
        wait_for(lambda: quantity(stream, 'minecraft:bucket') == 1)
        placed = done(stream, stream.query_blocks(positions=[[4, 64, 0]]))['blocks'][0]
        assert placed['block'] == 'minecraft:water' and placed['properties']['level'] == '0', placed
        # Separate crop setup keeps water propagation from changing the test's target.
        fixture.console('fill -1 64 -1 8 66 2 air')
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('setblock 2 63 0 farmland[moisture=7]')
        fixture.console('setblock 2 64 0 wheat[age=0]')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with bone_meal 4')
        wait_for(lambda: quantity(stream, 'minecraft:bone_meal') == 4)
        done(stream, stream.use_on([2, 64, 0], face='up'))
        crop = done(stream, stream.query_blocks(positions=[[2, 64, 0]]))['blocks'][0]
        assert int(crop['properties']['age']) > 0, crop
        assert quantity(stream, 'minecraft:bone_meal') == 3
        return {'area': None, 'water_source_collected_and_replaced': True,
                'empty_bucket_returned': 1, 'bone_meal_consumed': 1, 'wheat_age': crop['properties']['age']}

    fixture.case('unrestricted_native_bucket_and_bonemeal_use', ['ACT-09', 'ACT-10', 'EXEC-06'],
                 lambda: unrestricted_policy(unrestricted_bucket_and_bonemeal))

    def native_placement_contexts():
        reset()
        fixture.console('setblock 2 64 0 stone_slab[type=bottom]')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with stone_slab 2')
        wait_for(lambda: quantity(stream, 'minecraft:stone_slab') == 2)
        done(stream, stream.place(2, 64, 0, 'up'))
        slab = done(stream, stream.query_blocks(positions=[[2, 64, 0]]))['blocks'][0]
        assert slab['properties']['type'] == 'double', slab
        assert quantity(stream, 'minecraft:stone_slab') == 1
        fixture.console('setblock 2 63 2 grass_block')
        fixture.console('setblock 2 64 2 short_grass')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with oak_planks 2')
        wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 2)
        done(stream, stream.place(2, 64, 2, 'up'))
        assert block([2, 64, 2]) == 'minecraft:oak_planks'
        assert quantity(stream, 'minecraft:oak_planks') == 1
        return {'matching_slab_merged': True, 'slabs_consumed': 1, 'replaceable_plant_replaced': True,
                'planks_consumed': 1, 'native_context_destination_preserved': True}

    fixture.case('native_place_merges_slab_and_replaces_plant', ['ACT-08', 'OBS-03'], native_placement_contexts)

    def native_use_on_block_and_container():
        reset()
        fixture.console('item replace entity VerifyBuilder hotbar.0 with oak_planks 2')
        wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 2)
        done(stream, stream.use_on([1, 63, 2], face='up'))
        assert block([1, 64, 2]) == 'minecraft:oak_planks'
        assert quantity(stream, 'minecraft:oak_planks') == 1
        fixture.console('setblock 2 64 0 chest')
        time.sleep(.1)
        done(stream, stream.use_on([2, 64, 0], face='west'))
        opened = wait_for(lambda: stream.observe().get('container') if stream.observe().get('container', {}).get('open') else None)
        assert opened['session_id'] and opened['slots'], opened
        done(stream, stream.close_container(session_id=opened['session_id'], revision=opened['revision']))
        return {'native_block_item_use': True, 'planks_consumed': 1,
                'native_chest_click_adopted_as_session': True, 'container_closed': True}

    fixture.case('unrestricted_use_on_places_and_adopts_native_chest_menu', ['ACT-08', 'ACT-10', 'ACT-13', 'OBS-05'],
                 lambda: unrestricted_policy(native_use_on_block_and_container))

    def bounded_unknown_item_footprint():
        reset()
        fixture.console('item replace entity VerifyBuilder hotbar.0 with bucket 1')
        wait_for(lambda: quantity(stream, 'minecraft:bucket') == 1)
        bucket = failed(stream.use_item(), {'bounded_air_use_footprint_unknown'})
        assert quantity(stream, 'minecraft:bucket') == 1
        fixture.console('item replace entity VerifyBuilder hotbar.0 with bone_meal 2')
        fixture.console('setblock 2 63 0 farmland[moisture=7]')
        fixture.console('setblock 2 64 0 wheat[age=0]')
        wait_for(lambda: quantity(stream, 'minecraft:bone_meal') == 2)
        bone_meal = failed(stream.use_on([2, 64, 0], face='up'), {'unsupported_use_footprint'})
        crop = done(stream, stream.query_blocks(positions=[[2, 64, 0]]))['blocks'][0]
        assert crop['properties']['age'] == '0' and quantity(stream, 'minecraft:bone_meal') == 2
        return {'explicit_bounds_retained': True, 'bucket_rejection': bucket['reason'],
                'growth_rejection': bone_meal['reason'], 'inventory_and_target_unchanged': True}

    fixture.case('explicit_bounds_keep_unknown_air_and_growth_footprints_rejected', ['EXEC-06', 'ACT-09', 'ACT-10', 'VERIFY-04'], bounded_unknown_item_footprint)

    def dimension_context_invalidates_old_targets():
        reset()
        # Arrange both dimensions before accepting any work; generation is fixture setup.
        fixture.console('execute in minecraft:the_nether run forceload add 0 0 16 0')
        fixture.console('execute in minecraft:the_nether run fill 0 64 0 21 70 5 air')
        fixture.console('execute in minecraft:the_nether run fill 0 63 0 21 63 5 stone')
        fixture.console('execute in minecraft:the_nether run setblock 2 64 0 oak_log')
        fixture.console('setblock 2 64 0 oak_log')
        time.sleep(.3)
        old_epoch = stream.observe()['body_epoch']
        movement = stream.move_to(20.5, 64, .5)
        wait_for(lambda: movement['id'] in stream.observe()['execution']['active_actions'])
        digging = stream.dig(2, 64, 0)
        started(digging)
        new_state = None
        try:
            fixture.console('execute in minecraft:the_nether run tp VerifyBuilder 0.5 64 0.5')
            wait_for(lambda: fixture.gateway.frames.get('VerifyBuilder', {}).get('dimension') == 'minecraft:the_nether'
                     and fixture.gateway.frames['VerifyBuilder']['body_epoch'] != old_epoch,
                     timeout=35, description='dimension change rotates body execution epoch')
            stream.reconnect()
            current = stream.observe()
            assert current['body_epoch'] != old_epoch and current['dimension'] == 'minecraft:the_nether', current['execution']
            assert not current['execution']['active_actions'], current['execution']
            entered_tick = current['world_tick']
            wait_for(lambda: stream.observe()['world_tick'] >= entered_tick + 90, timeout=12)
            assert block([2, 64, 0]) == 'minecraft:oak_log', 'Old-world mining mutated the same coordinates in a new dimension'
            assert quantity(stream, 'minecraft:oak_log') == 0
            for receipt in (digging, movement):
                result = stream.action_results(receipt['id'])[0]
                assert result['state'] in ('cancelled', 'failed') and result['reason'] in ('body_changed', 'dimension_changed', 'body_disconnected'), result
            try:
                stream.request('POST', '/v1/actions', {'id': uuid.uuid4().hex, 'op': 'dig',
                    'body_epoch': old_epoch, 'target': [2, 64, 0], 'ttl_seconds': 10})
            except Exception as error:
                assert getattr(error, 'status', None) == 409, repr(error)
            else:
                raise AssertionError('Old-world action epoch accepted after a dimension change')
            new_state = {'new_dimension': current['dimension'], 'epoch_changed': True,
                         'new_world_target_intact': True, 'old_epoch_rejected': True,
                         'navigation_and_digging_cancelled': True, 'waited_native_ticks': 90}
        finally:
            fixture.console('execute in minecraft:overworld run tp VerifyBuilder 0.5 64 0.5')
            wait_for(lambda: fixture.gateway.frames.get('VerifyBuilder', {}).get('dimension') == 'minecraft:overworld',
                     timeout=35, description='fixture body returns to overworld')
            stream.reconnect()
            fixture.console('execute in minecraft:the_nether run forceload remove 0 0 16 0')
        assert block([2, 64, 0]) == 'minecraft:oak_log', 'Old-world target broke after leaving that dimension'
        new_state['old_world_target_intact'] = True
        return new_state

    fixture.case('unrestricted_dimension_change_cancels_old_world_actions', ['EXEC-02', 'EXEC-03', 'EXEC-06', 'OBS-03', 'OBS-07', 'VERIFY-01'],
                 lambda: unrestricted_policy(dimension_context_invalidates_old_targets))

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

    def jump_cycles_and_airborne_release():
        reset()
        done(stream, stream.jump(True))
        samples = []
        start_tick = stream.observe()['world_tick']
        last_tick = -1
        deadline = time.monotonic() + 12
        while stream.observe()['world_tick'] < start_tick + 55 and time.monotonic() < deadline:
            state = stream.observe()
            if state['world_tick'] != last_tick:
                samples.append((state['world_tick'], state['position'][1], state['execution']['on_ground']))
                last_tick = state['world_tick']
            time.sleep(.015)
        assert stream.observe()['world_tick'] >= start_tick + 55, 'Jump sampling stopped receiving native ticks'
        # Repeated rises after descent prove held jumping, without relying on a
        # one-frame grounded sample between consecutive native jumps.
        crests = sum(samples[i-1][1] < samples[i][1] and samples[i+1][1] <= samples[i][1]
                     for i in range(1, len(samples)-1))
        assert crests >= 2 and max(row[1] for row in samples) > 65, samples
        wait_for(lambda: stream.observe()['position'][1] > 64.6)
        done(stream, stream.jump(False))
        wait_for(lambda: stream.observe()['execution']['on_ground'])
        landed = stream.observe()['world_tick']
        wait_for(lambda: stream.observe()['world_tick'] >= landed + 20)
        assert abs(stream.observe()['position'][1] - 64) < .02
        assert not stream.observe()['execution']['jump_requested']
        done(stream, stream.jump(True))
        wait_for(lambda: stream.observe()['position'][1] > 64.5)
        stream.stop()
        wait_for(lambda: stream.observe()['execution']['on_ground'])
        assert not stream.observe()['execution']['jump_requested']
        done(stream, stream.jump(True))
        movement = stream.move_to(8.5, 64, .5)
        done(stream, stream.look_at(-5, 65, 5))
        done(stream, movement)
        assert stream.observe()['execution']['jump_requested']
        stream.stop()
        wait_for(lambda: stream.observe()['execution']['on_ground'])
        assert math.dist(stream.observe()['position'], [8.5, 64, .5]) < .7
        return {'held_jump_crests': crests, 'sampled_ticks': len(samples),
                'airborne_release_lands_without_repeat': True, 'stop_released_jump': True,
                'held_jump_with_navigation_and_independent_look': True}

    fixture.case('held_jump_repeats_and_airborne_release_stops_repetition', ['ACT-04', 'EXEC-03', 'OBS-07'], jump_cycles_and_airborne_release)

    def crouch_collision_and_edge_route():
        reset()
        fixture.console('fill -1 66 -1 1 66 1 stone')
        time.sleep(.15)

        def jump_ceiling(sneaking):
            done(stream, stream.sneak(sneaking))
            pose_tick = stream.observe()['world_tick']
            wait_for(lambda: stream.observe()['world_tick'] >= pose_tick + 4)
            done(stream, stream.jump(True))
            samples = []
            end_tick = stream.observe()['world_tick'] + 25
            deadline = time.monotonic() + 10
            while stream.observe()['world_tick'] < end_tick and time.monotonic() < deadline:
                samples.append(stream.observe()['position'][1])
                time.sleep(.015)
            assert stream.observe()['world_tick'] >= end_tick, 'Crouch sampling stopped receiving native ticks'
            done(stream, stream.jump(False))
            wait_for(lambda: stream.observe()['execution']['on_ground'])
            return max(samples)

        standing = jump_ceiling(False)
        crouched = jump_ceiling(True)
        assert standing < 64.25 and 64.4 < crouched < 64.55, (standing, crouched)
        fixture.console('fill -1 66 -1 1 66 1 air')
        fixture.console('fill -1 62 -1 4 63 1 air')
        fixture.console('fill 0 63 0 2 63 0 stone')
        done(stream, stream.move_to(2.75, 64, .5))
        state = stream.observe()
        assert state['execution']['sneaking'] and abs(state['position'][1]-64) < .05, state['position']
        stream.stop()
        wait_for(lambda: not stream.observe()['execution']['sneak_requested'] and not stream.observe()['execution']['sneaking'])
        return {'standing_ceiling_height': standing, 'crouched_ceiling_height': crouched,
                'narrow_platform_edge_route_supported': True, 'stop_released_sneak': True}

    fixture.case('sneak_native_collision_height_and_platform_edge', ['ACT-05', 'EXEC-03', 'VERIFY-01'], crouch_collision_and_edge_route)

    def sprint_hunger_and_lease_release():
        reset()
        done(stream, stream.sprint(True))
        move = stream.move_to(20.5, 64, .5)
        wait_for(lambda: stream.observe()['execution']['sprinting'])
        stream.stop()
        wait_for(lambda: not stream.observe()['execution']['sprinting'])
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        time.sleep(.8)
        fixture.console('effect clear VerifyBuilder')
        fixture.console('effect give VerifyBuilder hunger 5 255 true')
        wait_for(lambda: stream.observe()['food'] <= 6)
        fixture.console('effect clear VerifyBuilder')
        done(stream, stream.sprint(True))
        low_food_move = stream.move_to(20.5, 64, .5)
        started(low_food_move)
        beginning = stream.observe()['world_tick']
        deadline = time.monotonic() + 8
        while stream.observe()['world_tick'] < beginning + 15 and time.monotonic() < deadline:
            state = stream.observe()
            assert state['execution']['sprint_requested'] and not state['execution']['sprinting'], state['execution']
            time.sleep(.025)
        assert stream.observe()['world_tick'] >= beginning + 15, 'Sprint sampling stopped receiving native ticks'
        stream.close()
        wait_for(lambda: not fixture.gateway.frames.get('VerifyBuilder', {}).get('execution', {}).get('sprint_requested', True))
        released = fixture.gateway.frames['VerifyBuilder']['execution']
        assert not released['sprinting'] and not released['active_actions'], released
        stream.reconnect()
        fixture.console('effect give VerifyBuilder saturation 1 255 true')
        return {'fed_forward_movement_sprints': True, 'hunger_at_most_six_blocks_actual_sprint': True,
                'requested_state_preserved_while_hungry': True, 'lease_release_clears_request_and_movement': True}

    fixture.case('sprint_native_hunger_gate_and_lease_release', ['ACT-06', 'EXEC-03', 'OBS-07'], sprint_hunger_and_lease_release)

    def bow_release_and_offhand_use():
        reset()
        fixture.console('item replace entity VerifyBuilder weapon.offhand with bow 1')
        fixture.console('give VerifyBuilder arrow 2')
        wait_for(lambda: quantity(stream, 'minecraft:arrow') == 2)
        done(stream, stream.look_at(12, 65, .5))
        draw = stream.use_item(hand='off')
        started(draw)
        wait_for(lambda: stream.observe()['execution']['use_ticks'] >= 25)
        released = done(stream, stream.release_use())
        terminal = done(stream, draw)
        wait_for(lambda: quantity(stream, 'minecraft:arrow') == 1)
        bow = next(row for row in stream.observe()['inventory'] if row['slot'] == 40)
        assert bow['item'] == 'minecraft:bow' and bow['damage'] == 1, bow
        assert terminal['reason'] == 'released' and not stream.observe()['execution']['using_item']
        fixture.console('item replace entity VerifyBuilder hotbar.0 with stick 1')
        wait_for(lambda: quantity(stream, 'minecraft:stick') == 1)
        rejected = failed(stream.use_item(), {'use_rejected'})
        assert quantity(stream, 'minecraft:stick') == 1
        return {'offhand_draw_released': released['reason'], 'arrow_consumed': 1, 'bow_damage': 1,
                'unusable_item_rejected_without_consumption': rejected['reason']}

    fixture.case('offhand_bow_explicit_release_and_unusable_item', ['ACT-09', 'OBS-01', 'OBS-07'], bow_release_and_offhand_use)

    def entity_obstruction_disappearance_and_collision():
        reset()
        fixture.console('summon minecraft:cow 2.5 64 0.5 {NoAI:1b,Silent:1b,Tags:["body_case"]}')
        cow = wait_for(lambda: next((e for e in stream.observe()['entities'] if e['type'] == 'minecraft:cow'), None))
        fixture.console('fill 1 64 0 1 65 0 stone')
        time.sleep(.15)
        obstructed = failed(stream.attack(cow['id']), {'out_of_reach_or_obstructed'})
        fixture.console('kill @e[tag=body_case]')
        wait_for(lambda: not any(e['id'] == cow['id'] and e.get('health', 0) > 0 for e in stream.observe()['entities']))
        disappeared = failed(stream.use_on(entity_id=cow['id']), {'entity_missing'})
        fixture.console('fill 1 64 0 1 65 0 air')
        fixture.console('summon minecraft:cow 2.5 64 0.5 {NoAI:1b,Silent:1b,Invulnerable:1b,Tags:["body_collision"]}')
        moving_cow = wait_for(lambda: next((e for e in stream.observe()['entities'] if e['type'] == 'minecraft:cow' and e['id'] != cow['id'] and e.get('health', 0) > 0), None))
        move = stream.move_to(7.5, 64, .5)
        done(stream, move)
        final_cow = next(e for e in stream.observe()['entities'] if e['id'] == moving_cow['id'])
        displacement = math.dist(final_cow['position'], moving_cow['position'])
        assert displacement > .05, (moving_cow, final_cow)
        assert math.dist(stream.observe()['position'], [7.5, 64, .5]) < .6
        return {'occluded_attack': obstructed['reason'], 'removed_use_target': disappeared['reason'],
                'native_entity_collision_displacement': displacement, 'navigation_reaches_goal': True}

    fixture.case('entity_obstruction_disappearance_and_navigation_collision', ['ACT-10', 'ACT-11', 'OBS-02', 'VERIFY-01'], entity_obstruction_disappearance_and_collision)

    def public_chat_rate_limit_and_identity():
        reset()
        text = 'Native chat fixture ' + uuid.uuid4().hex[:12]
        first = done(stream, stream.chat(text))
        try:
            repeated = stream.chat(text + ' repeated')
        except Exception as error:
            assert getattr(error, 'status', None) == 429, repr(error)
            limited = 'gateway_rate_limited'
        else:
            limited = failed(repeated, {'chat_rate_limited'})['reason']
        rows = wait_for(lambda: [row for row in stream.observe().get('public_chat', []) if row.get('text') == text])
        assert len(rows) == 1 and rows[0]['speaker'] == 'VerifyBuilder' and rows[0]['id'] and rows[0]['at'], rows
        assert not any(row.get('text') == text + ' repeated' for row in stream.observe().get('public_chat', []))
        assert not any(key in rows[0] for key in ('position', 'dimension', 'private_code')), rows
        for bad in ('/give VerifyBuilder diamond', 'line\nbreak', '\u00a7cformat'):
            try:
                receipt = stream.chat(bad)
            except Exception as error:
                assert getattr(error, 'status', None) == 400, repr(error)
            else:
                failed(receipt, {'invalid_chat'})
        return {'delivered': first['reason'], 'rate_limited': limited,
                'one_message_with_sender_id_timestamp': True, 'command_control_formatting_rejected': True}

    fixture.case('native_public_chat_rate_limit_identity_and_validation', ['ACT-12', 'OBS-04', 'EXEC-05'], public_chat_rate_limit_and_identity)

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
