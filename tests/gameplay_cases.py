"""Real-world integration evidence for individual API checklist criteria.

Fixture commands only arrange initial conditions. All measured gameplay uses the
public Python SDK through the fixture gateway and the loaded Java adapter.
Passing these cases is partial evidence, never the whole release checklist.
"""
import math
import time
import uuid

from isolated_game_fixture import wait_for


def done(stream, receipt, timeout=20):
    result = stream.wait_action(receipt['id'], timeout=timeout)
    assert result['state'] == 'done', result
    return result


def quantity(stream, item):
    return sum(row.get('count', 0) for row in stream.observe()['inventory'] if row.get('item') == item)


def slot(stream, item):
    return next(row['slot'] for row in stream.observe()['inventory'] if row.get('item') == item and row.get('count', 0))


def run_cases(fixture):
    client = fixture.client()
    with client.realtime() as stream:
        def reset():
            stream.stop()
            fixture.console('tp VerifyBuilder 0.5 64 0.5')
            fixture.console('clear VerifyBuilder')
            fixture.console('kill @e[type=minecraft:item]')
            fixture.console('fill -16 64 -16 16 70 16 air')
            fixture.console('fill -16 63 -16 16 63 16 stone')
            time.sleep(.4)

        def inventory_controls():
            reset()
            rows = stream.observe()['inventory']
            assert {r['slot'] for r in rows} == set(range(41)) | {-1}, rows
            done(stream, stream.swap_hands())
            assert not any(r.get('count', 0) for r in stream.observe()['inventory'])
            for n in range(9):
                done(stream, stream.select_slot(n))
                wait_for(lambda: stream.observe()['selected_slot'] == n, description='selected hotbar slot')
            fixture.console('item replace entity VerifyBuilder hotbar.8 with minecraft:iron_pickaxe[minecraft:damage=7,minecraft:custom_name=\'{"text":"Fixture pick"}\'] 1')
            wait_for(lambda: quantity(stream, 'minecraft:iron_pickaxe') == 1)
            before = next(r for r in stream.observe()['inventory'] if r['slot'] == 8)
            done(stream, stream.swap_hands())
            off = wait_for(lambda: next((r for r in stream.observe()['inventory'] if r['slot'] == 40 and r.get('item') == 'minecraft:iron_pickaxe'), None))
            assert off['count'] == 1 and off['components'] == before['components'], (before, off)
            done(stream, stream.swap_hands())
            for name in ('sneak', 'sprint', 'jump'):
                done(stream, getattr(stream, name)(True))
                wait_for(lambda: stream.observe()['execution'][name + '_requested'])
            stream.stop()
            wait_for(lambda: not any(stream.observe()['execution'][name + '_requested'] for name in ('sneak', 'sprint', 'jump')))
            return {'slots': 42, 'hotbar_slots_selected': 9, 'components_preserved': True, 'stop_released_toggles': True}

        fixture.case('inventory_and_held_controls', ['ACT-01', 'ACT-02', 'ACT-04', 'ACT-05', 'ACT-06', 'OBS-01', 'OBS-07', 'EXEC-03'], inventory_controls)

        def navigation():
            reset()
            receipt = stream.move_to(8.5, 64, .5)
            done(stream, stream.look_at(-5, 65, 5))
            result = done(stream, receipt)
            position = stream.observe()['position']
            assert math.dist(position, [8.5, 64, .5]) < .6, position
            return {'result': result, 'position': position, 'look_did_not_cancel_or_redirect_navigation': True}

        fixture.case('flat_navigation_while_looking', ['EXEC-01', 'VERIFY-01'], navigation)

        def world_journey():
            reset()
            for command in ('setblock 2 64 0 oak_log', 'setblock 3 64 2 crafting_table', 'setblock 4 64 2 chest'):
                fixture.console(command)
            time.sleep(.2)
            done(stream, stream.select_slot(0))
            done(stream, stream.dig(2, 64, 0))
            done(stream, stream.move_to(2.5, 64, .5))
            wait_for(lambda: quantity(stream, 'minecraft:oak_log') == 1, description='natural log drop pickup')
            done(stream, stream.craft('minecraft:oak_planks', 1))
            wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 4)
            assert quantity(stream, 'minecraft:oak_log') == 0
            plank_slot = slot(stream, 'minecraft:oak_planks')
            done(stream, stream.select_slot(plank_slot))
            done(stream, stream.place(2, 64, 1, 'up'))
            wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 3)
            opened = done(stream, stream.open_container(4, 64, 2))
            container = opened if 'session_id' in opened else stream.observe()['container']
            moved = done(stream, stream.move_item({'inventory': 'player', 'slot': plank_slot},
                {'inventory': 'container', 'slot': 0}, 3, session_id=container['session_id'], revision=container['revision']))
            container = moved if 'session_id' in moved else stream.observe()['container']
            moved = done(stream, stream.move_item({'inventory': 'container', 'slot': 0},
                {'inventory': 'player', 'slot': plank_slot}, 1, session_id=container['session_id'], revision=container['revision']))
            wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 1)
            container = moved if 'session_id' in moved else stream.observe()['container']
            chest_count = sum(r.get('count', 0) for r in container['slots'] if r['inventory'] == 'container' and r.get('item') == 'minecraft:oak_planks')
            assert chest_count == 2, container
            done(stream, stream.close_container(session_id=container['session_id'], revision=container['revision']))
            block_result = done(stream, stream.query_blocks(positions=[[2, 64, 0], [2, 64, 1]]))
            assert [r['block'] for r in block_result['blocks']] == ['minecraft:air', 'minecraft:oak_planks'], block_result
            done(stream, stream.chat('Fixture gameplay complete.'))
            wait_for(lambda: any(r.get('text') == 'Fixture gameplay complete.' for r in stream.observe().get('public_chat', [])), description='public chat observation')
            return {'log_consumed': 1, 'planks': {'placed': 1, 'player': 1, 'chest': 2},
                    'fixture_supplied': ['one oak log block', 'crafting table', 'empty chest'],
                    'synthetic_identity_only': True}

        fixture.case('dig_craft_place_container_chat', ['ACT-07', 'ACT-08', 'ACT-12', 'ACT-13', 'ACT-14', 'ACT-15', 'ACT-16', 'OBS-03', 'OBS-04', 'OBS-05', 'VERIFY-02'], world_journey)

        def craft_remainders():
            reset()
            fixture.console('setblock 2 64 0 crafting_table')
            for item, count in [('milk_bucket', 3), ('sugar', 2), ('egg', 1), ('wheat', 3)]:
                fixture.console(f'give VerifyBuilder minecraft:{item} {count}')
            wait_for(lambda: quantity(stream, 'minecraft:wheat') == 3)
            done(stream, stream.craft('minecraft:cake', 1, target=[2, 64, 0]))
            wait_for(lambda: quantity(stream, 'minecraft:cake') == 1)
            assert quantity(stream, 'minecraft:bucket') == 3, stream.observe()['inventory']
            assert all(quantity(stream, 'minecraft:' + item) == 0 for item in ('milk_bucket', 'sugar', 'egg', 'wheat'))
            return {'recipe': 'minecraft:cake', 'output': 1, 'bucket_remainders': 3}

        fixture.case('craft_recipe_remainders', ['ACT-15', 'VERIFY-03'], craft_remainders)

        def idempotence():
            reset()
            fixture.console('give VerifyBuilder oak_log 2')
            wait_for(lambda: quantity(stream, 'minecraft:oak_log') == 2)
            rid = uuid.uuid4().hex
            first = stream.craft('minecraft:oak_planks', 1, request_id=rid)
            done(stream, first)
            done(stream, stream.craft('minecraft:oak_planks', 1, request_id=rid))
            wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 4)
            assert quantity(stream, 'minecraft:oak_log') == 1
            try:
                stream.craft('minecraft:oak_planks', 2, request_id=rid)
            except Exception as error:
                assert getattr(error, 'status', None) == 409, repr(error)
            else:
                raise AssertionError('Changed payload reused an ID')
            return {'exact_retry_executions': 1, 'changed_payload_rejected': True}

        fixture.case('mutation_retry_conservation', ['EXEC-02', 'EXEC-04', 'VERIFY-03'], idempotence)

        from container_gameplay_cases import run_cases as container_cases
        container_cases(fixture, stream)
        from body_gameplay_cases import run_cases as body_cases
        body_cases(fixture, stream)
        from result_receipt_gameplay_cases import run_cases as receipt_cases
        receipt_cases(fixture, stream)

        def optional_area():
            # The latest workspace policy makes owner-specified bounds optional.
            # Fixture setup changes the stored owner policy; gameplay still uses SDK calls.
            with fixture.gateway.changed:
                body = fixture.gateway.body('VerifyBuilder')
                previous = body['data']['area']
                body['data']['area'] = None
                fixture.gateway.save(body)
            try:
                stream.stop()
                fixture.console('clear VerifyBuilder')
                fixture.console('fill 24 63 -2 31 63 4 stone')
                fixture.console('fill 24 64 -2 31 67 4 air')
                fixture.console('tp VerifyBuilder 25.5 64 0.5')
                fixture.console('setblock 27 64 0 oak_log')
                fixture.console('setblock 29 64 0 chest')
                time.sleep(.4)
                done(stream, stream.select_slot(0))
                done(stream, stream.dig(27, 64, 0))
                done(stream, stream.move_to(27.5, 64, .5))
                wait_for(lambda: quantity(stream, 'minecraft:oak_log') == 1)
                done(stream, stream.craft('minecraft:oak_planks', 1))
                wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 4)
                selected = slot(stream, 'minecraft:oak_planks')
                done(stream, stream.select_slot(selected))
                done(stream, stream.place(27, 64, 1, 'up'))
                opened = done(stream, stream.open_container(29, 64, 0))
                moved = done(stream, stream.move_item({'inventory': 'player', 'slot': selected},
                    {'inventory': 'container', 'slot': 0}, 3, session_id=opened['session_id'], revision=opened['revision']))
                assert next(r['count'] for r in moved['slots'] if r['inventory'] == 'container' and r['slot'] == 0) == 3
                assert quantity(stream, 'minecraft:oak_planks') == 0
                return {'area': None, 'outside_previous_bounds': True, 'planks_placed': 1, 'planks_in_chest': 3,
                        'fixture_policy_change_only': True}
            finally:
                stream.stop()
                with fixture.gateway.changed:
                    body = fixture.gateway.body('VerifyBuilder')
                    body['data']['area'] = previous
                    fixture.gateway.save(body)

        fixture.case('optional_area_unrestricted_native_journey', ['EXEC-06', 'VERIFY-02'], optional_area)
        from lifecycle_gameplay_cases import run_cases as lifecycle_cases
        lifecycle_cases(fixture, stream)
