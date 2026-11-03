"""Native container/recipe edge cases in the disposable loopback fixture only."""
import json
import hashlib
import time

from gameplay_cases import done, quantity, slot
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    def reset():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('clear VerifyBuilder')
        fixture.console('kill @e[type=minecraft:item]')
        fixture.console('fill -16 64 -16 26 70 16 air')
        fixture.console('fill -16 63 -16 26 63 16 stone')
        wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 0)
        time.sleep(.4)

    def failed(receipt, reason):
        result = stream.wait_action(receipt['id'], timeout=15)
        assert result['state'] == 'failed' and result.get('reason') == reason, result
        return result

    def signature():
        return json.dumps(stream.observe()['inventory'], sort_keys=True)

    def container(receipt):
        result = done(stream, receipt)
        return result if 'session_id' in result else stream.observe()['container']

    def full_inventory():
        reset()
        for index in range(36):
            reference = f'hotbar.{index}' if index < 9 else f'inventory.{index - 9}'
            item, count = ('oak_log', 2) if index == 0 else ('stone', 64)
            fixture.console(f'item replace entity VerifyBuilder {reference} with minecraft:{item} {count}')
        wait_for(lambda: quantity(stream, 'minecraft:stone') == 35 * 64 and quantity(stream, 'minecraft:oak_log') == 2)
        before = signature()
        result = failed(stream.craft('minecraft:oak_planks', 1), 'inventory_full')
        time.sleep(.2)
        assert signature() == before, stream.observe()['inventory']
        return {'failure': result['reason'], 'slots_unchanged': True, 'log_count': 2, 'occupied_storage_slots': 36}

    fixture.case('craft_full_inventory_atomic_failure', ['ACT-15', 'VERIFY-03'], full_inventory)

    def mixed_ingredients():
        reset()
        fixture.console('setblock 2 64 0 crafting_table')
        fixture.console('give VerifyBuilder oak_planks 4')
        fixture.console('give VerifyBuilder birch_planks 4')
        wait_for(lambda: quantity(stream, 'minecraft:oak_planks') == 4 and quantity(stream, 'minecraft:birch_planks') == 4)
        done(stream, stream.craft('minecraft:chest', 1, target=[2, 64, 0]))
        wait_for(lambda: quantity(stream, 'minecraft:chest') == 1)
        assert quantity(stream, 'minecraft:oak_planks') == quantity(stream, 'minecraft:birch_planks') == 0
        return {'recipe': 'minecraft:chest', 'oak_planks_consumed': 4, 'birch_planks_consumed': 4, 'chests': 1}

    fixture.case('craft_mixed_tag_ingredients', ['ACT-15', 'VERIFY-03'], mixed_ingredients)

    def stale_revision():
        reset()
        fixture.console('setblock 2 64 0 chest')
        time.sleep(.2)
        opened = container(stream.open_container(2, 64, 0))
        old_revision = opened['revision']
        fixture.console('item replace block 2 64 0 container.0 with minecraft:stone 2')
        def changed_container():
            value = stream.observe().get('container', {})
            return value if value.get('revision', 0) > old_revision else None
        changed = wait_for(changed_container, description='externally changed chest revision')
        result = failed(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 1,
                        session_id=opened['session_id'], revision=old_revision), 'stale_container_revision')
        assert quantity(stream, 'minecraft:stone') == 0
        current = stream.observe()['container']
        assert next(r['count'] for r in current['slots'] if r['inventory'] == 'container' and r['slot'] == 0) == 2
        return {'old_revision': old_revision, 'new_revision': changed['revision'], 'failure': result['reason'],
                'external_mutation': 'fixture console simulates another viewer', 'chest_stones': 2, 'player_stones': 0}

    fixture.case('container_competing_mutation_stale_revision', ['ACT-14', 'OBS-05', 'VERIFY-03'], stale_revision)

    def components():
        reset()
        fixture.console('setblock 2 64 0 chest')
        fixture.console('item replace entity VerifyBuilder hotbar.0 with minecraft:iron_pickaxe[minecraft:damage=7,minecraft:custom_name=\'{"text":"Container fixture pick"}\'] 1')
        wait_for(lambda: quantity(stream, 'minecraft:iron_pickaxe') == 1)
        before = next(r for r in stream.observe()['inventory'] if r['slot'] == 0)
        opened = container(stream.open_container(2, 64, 0))
        moved = container(stream.move_item({'inventory': 'player', 'slot': 0}, {'inventory': 'container', 'slot': 0}, 1,
                          session_id=opened['session_id'], revision=opened['revision']))
        stored = next(r for r in moved['slots'] if r['inventory'] == 'container' and r['slot'] == 0)
        assert stored['components'] == before['components'] and stored['damage'] == 7, (before, stored)
        container(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 1}, 1,
                  session_id=moved['session_id'], revision=moved['revision']))
        returned = wait_for(lambda: next((r for r in stream.observe()['inventory'] if r['slot'] == 1 and r.get('item') == 'minecraft:iron_pickaxe'), None))
        assert returned['components'] == before['components'] and returned['damage'] == 7
        assert quantity(stream, 'minecraft:iron_pickaxe') == 1
        return {'components_preserved': True, 'damage': 7, 'total_pickaxes': 1, 'round_trip': 'player:0 -> container:0 -> player:1'}

    fixture.case('container_named_damaged_stack_conservation', ['ACT-14', 'OBS-05', 'VERIFY-03'], components)

    def double_chest_area():
        reset()
        fixture.console('setblock 23 64 0 minecraft:chest[facing=north,type=left]')
        fixture.console('setblock 24 64 0 minecraft:chest[facing=north,type=right]')
        fixture.console('tp VerifyBuilder 21.5 64 0.5')
        wait_for(lambda: abs(stream.observe()['position'][0] - 21.5) < .1)
        time.sleep(.2)
        result = failed(stream.open_container(23, 64, 0), 'outside_work_area')
        assert not stream.observe().get('container', {}).get('open', False)
        return {'inside_half': [23, 64, 0], 'outside_half': [24, 64, 0], 'area_max_x_exclusive': 24, 'failure': result['reason']}

    fixture.case('double_chest_second_half_work_area', ['ACT-13', 'ACT-14', 'VERIFY-04'], double_chest_area)

    def recipe_discovery():
        reset()
        page = done(stream, stream.query_recipes(offset=0, limit=2))
        assert len(page['recipes']) == 2 and page['total'] >= 2 and page['next_offset'] == 2, page
        for recipe in page['recipes']:
            assert recipe['supported'] and recipe['ingredients'] and recipe['output']['count'] > 0, recipe
            assert recipe['count_semantics'] == 'recipe_executions', recipe
        second = done(stream, stream.query_recipes(offset=page['next_offset'], limit=2))
        assert not ({r['recipe_id'] for r in page['recipes']} & {r['recipe_id'] for r in second['recipes']}), (page, second)
        result = failed(stream.craft('minecraft:iron_ingot_from_smelting_iron_ore', 1), 'unsupported_recipe_type')
        full = stream.recipe('minecraft:cake')
        assert full['recipe_id'] == 'minecraft:cake' and full['output']['item'] == 'minecraft:cake' and full['output']['count'] == 1, full
        assert full['workstation'] == 'minecraft:crafting_table' and 'ingredients_truncated' not in full
        milk = [item for alternatives in full['ingredients'] for item in alternatives if item['item'] == 'minecraft:milk_bucket']
        assert len(milk) == 3 and all(item['remainder']['item'] == 'minecraft:bucket' for item in milk), full
        first_recipe = done(stream, stream.query_recipe('minecraft:cake', limit=128))
        next_recipe = done(stream, stream.query_recipe('minecraft:cake', offset=first_recipe['next_offset'], limit=128,
                           recipe_revision=first_recipe['recipe_revision']))
        assert next_recipe['recipe_revision'] == first_recipe['recipe_revision'] and next_recipe['offset'] == 128
        failed(stream.query_recipe('minecraft:cake', offset=first_recipe['next_offset'], limit=128, recipe_revision='0' * 64), 'stale_recipe_revision')
        return {'discovered_recipes': page['total'], 'page_limit_obeyed': True, 'distinct_pages': True, 'machine_recipe_failure': result['reason'],
                'full_recipe_metadata': True, 'cake_bucket_remainders_described': 3, 'recipe_pages_revision_pinned': True, 'wrong_revision_rejected': True}

    fixture.case('recipe_discovery_paging_and_machine_rejection', ['OBS-06', 'ACT-15'], recipe_discovery)

    def missing_batch():
        reset()
        fixture.console('give VerifyBuilder oak_log 1')
        wait_for(lambda: quantity(stream, 'minecraft:oak_log') == 1)
        before = signature()
        failed(stream.craft('minecraft:oak_planks', 2), 'insufficient_ingredients')
        time.sleep(.15)
        assert signature() == before
        return {'requested_executions': 2, 'available_logs': 1, 'all_slots_unchanged': True}

    fixture.case('craft_missing_batch_ingredient_atomicity', ['ACT-15', 'VERIFY-03'], missing_batch)

    def remainder_space():
        reset()
        for index in range(36):
            if index == 1:
                continue
            reference = f'hotbar.{index}' if index < 9 else f'inventory.{index - 9}'
            item, count = ('honey_bottle', 5) if index == 0 else ('stone', 64)
            fixture.console(f'item replace entity VerifyBuilder {reference} with minecraft:{item} {count}')
        wait_for(lambda: quantity(stream, 'minecraft:stone') == 34 * 64 and quantity(stream, 'minecraft:honey_bottle') == 5)
        before = signature()
        failed(stream.craft('minecraft:honey_block', 1), 'inventory_full_for_remainder')
        time.sleep(.15)
        assert signature() == before
        return {'output_space_available': True, 'four_bottle_remainders_would_not_fit': True, 'all_slots_unchanged': True}

    fixture.case('craft_remainder_capacity_atomicity', ['ACT-15', 'VERIFY-03'], remainder_space)

    def blocked_and_removed():
        reset()
        fixture.console('setblock 2 64 0 chest')
        fixture.console('setblock 2 65 0 stone')
        time.sleep(.2)
        result = stream.wait_action(stream.open_container(2, 64, 0)['id'], timeout=15)
        assert result['state'] == 'failed' and result['reason'] in {'container_blocked', 'container_locked_or_blocked'}, result
        fixture.console('setblock 2 65 0 air')
        time.sleep(.15)
        opened = container(stream.open_container(2, 64, 0))
        fixture.console('setblock 2 64 0 air')
        closed = wait_for(lambda: (value if not value.get('open', False) else None)
                          if (value := stream.observe().get('container', {})) else None)
        assert closed.get('closed_session_id') == opened['session_id'], closed
        failed(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 1,
               session_id=opened['session_id'], revision=opened['revision']), 'container_closed')
        return {'blocked_open_rejected': True, 'removed_session_invalidated': True, 'close_reason': closed['reason']}

    fixture.case('container_blocked_and_removed', ['ACT-13', 'ACT-14', 'OBS-05'], blocked_and_removed)

    def range_invalidation():
        reset()
        fixture.console('setblock 2 64 0 chest')
        time.sleep(.15)
        opened = container(stream.open_container(2, 64, 0))
        done(stream, stream.move_to(-5.5, 64, .5))
        closed = wait_for(lambda: (value if not value.get('open', False) else None)
                          if (value := stream.observe().get('container', {})) else None)
        assert closed['closed_session_id'] == opened['session_id'], closed
        assert closed['reason'] == 'out_of_reach_or_occluded', closed
        failed(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 1,
               session_id=opened['session_id'], revision=opened['revision']), 'container_closed')
        return {'actual_navigation_out_of_range': True, 'session_invalidated': True, 'close_reason': closed['reason']}

    fixture.case('container_range_invalidation', ['ACT-13', 'ACT-14', 'OBS-05'], range_invalidation)

    def close_and_stop():
        reset()
        fixture.console('setblock 2 64 0 chest')
        time.sleep(.15)
        opened = container(stream.open_container(2, 64, 0))
        closed = done(stream, stream.close_container(session_id=opened['session_id'], revision=opened['revision']))
        assert not closed['open'] and closed['closed_session_id'] == opened['session_id'], closed
        reopened = container(stream.open_container(2, 64, 0))
        assert reopened['session_id'] != opened['session_id']
        failed(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 1,
               session_id=opened['session_id'], revision=opened['revision']), 'stale_container_session')
        done(stream, stream.action('stop'))
        closed = wait_for(lambda: (value if not value.get('open', False) else None)
                          if (value := stream.observe().get('container', {})) else None)
        assert closed['closed_session_id'] == reopened['session_id'], closed
        return {'explicit_close_invalidates': True, 'reopen_has_new_id': True, 'old_handle_rejected': True,
                'stop_closed_session': True, 'stop_reason': closed['reason'], 'cursor_fixture': 'empty'}

    fixture.case('container_explicit_close_and_stop', ['ACT-16', 'OBS-05', 'EXEC-03'], close_and_stop)

    def furnace_slots():
        reset()
        fixture.console('setblock 2 64 0 furnace')
        fixture.console('item replace block 2 64 0 container.2 with minecraft:iron_ingot 3')
        fixture.console('give VerifyBuilder stone 1')
        wait_for(lambda: quantity(stream, 'minecraft:stone') == 1)
        opened = container(stream.open_container(2, 64, 0))
        assert [r['role'] for r in opened['slots'] if r['inventory'] == 'container'] == ['input', 'fuel', 'output']
        failed(stream.move_item({'inventory': 'player', 'slot': slot(stream, 'minecraft:stone')},
               {'inventory': 'container', 'slot': 1}, 1, session_id=opened['session_id'], revision=opened['revision']), 'slot_rule_rejected')
        moved = container(stream.move_item({'inventory': 'container', 'slot': 2}, {'inventory': 'player', 'slot': 1}, 1,
                          session_id=opened['session_id'], revision=opened['revision']))
        assert next(r['count'] for r in moved['slots'] if r['inventory'] == 'container' and r['slot'] == 2) == 2
        wait_for(lambda: quantity(stream, 'minecraft:iron_ingot') == 1)
        failed(stream.move_item({'inventory': 'player', 'slot': 1}, {'inventory': 'container', 'slot': 2}, 1,
               session_id=moved['session_id'], revision=moved['revision']), 'slot_rule_rejected')
        return {'output_partial_extraction': 1, 'output_remaining': 2, 'fuel_rule_enforced': True, 'output_insert_rejected': True,
                'fixture_supplied_furnace_output': True, 'actual_smelting_or_xp_verified': False}

    fixture.case('container_furnace_native_slot_rules', ['ACT-14', 'OBS-05', 'VERIFY-03'], furnace_slots)

    def large_components():
        reset()
        fixture.console('setblock 2 64 0 chest')
        expected_name = 'Fixture metadata ' + 'x' * 20000 + '\U0001f331\u00e9' * 100
        # SNBT's enclosing quoted string does not accept JSON \u escapes; send UTF-8 literally.
        custom_name = json.dumps({'text': expected_name}, separators=(',', ':'), ensure_ascii=False)
        fixture.console(f"item replace entity VerifyBuilder hotbar.0 with minecraft:iron_pickaxe[minecraft:damage=7,minecraft:custom_name='{custom_name}'] 1")
        wait_for(lambda: quantity(stream, 'minecraft:iron_pickaxe') == 1)
        before = next(r for r in stream.observe()['inventory'] if r['slot'] == 0)
        assert before['components_truncated'] and before['component_bytes'] > 2048 and 'components' not in before, before
        opened = container(stream.open_container(2, 64, 0))
        moved = container(stream.move_item({'inventory': 'player', 'slot': 0}, {'inventory': 'container', 'slot': 0}, 1,
                          session_id=opened['session_id'], revision=opened['revision']))
        stored = next(r for r in moved['slots'] if r['inventory'] == 'container' and r['slot'] == 0)
        assert stored['components_sha256'] == before['components_sha256'] and stored['damage'] == 7, (before, stored)
        def name_of(row):
            value = row['components']['minecraft:custom_name']
            # Minecraft's component codec may wrap a text component in a JSON-encoded string.
            if isinstance(value, str) and value[:1] in {'"', '{', '['}:
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            return value.get('text') if isinstance(value, dict) else value
        full_stored = stream.inventory_slot(0, inventory='container', session_id=moved['session_id'], revision=moved['revision'])
        assert name_of(full_stored) == expected_name and full_stored['damage'] == 7, 'Full container metadata did not reconstruct'
        raw_components = json.dumps(full_stored['components'], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        assert hashlib.sha256(raw_components).hexdigest() == before['components_sha256'], 'Full component bytes differ from ambient fingerprint'
        moved = container(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 1}, 1,
                          session_id=moved['session_id'], revision=moved['revision']))
        returned = wait_for(lambda: next((r for r in stream.observe()['inventory'] if r['slot'] == 1 and r.get('item') == 'minecraft:iron_pickaxe'), None))
        assert returned['components_sha256'] == before['components_sha256'] and returned['component_bytes'] == before['component_bytes']
        assert quantity(stream, 'minecraft:iron_pickaxe') == 1
        full = stream.inventory_slot(1)
        assert name_of(full) == expected_name and full['damage'] == 7, 'Full player metadata did not reconstruct'
        assert full['component_bytes'] > 16384, full['component_bytes']
        cursor = stream.inventory_slot(-1)
        assert cursor['empty'] and cursor['count'] == 0, cursor
        first_page = done(stream, stream.query_inventory(1, limit=256))
        fixture.console('item replace entity VerifyBuilder hotbar.1 with minecraft:iron_pickaxe[minecraft:damage=8] 1')
        wait_for(lambda: any(r['slot'] == 1 and r.get('damage') == 8 for r in stream.observe()['inventory']))
        failed(stream.query_inventory(1, offset=first_page['next_offset'], limit=256, stack_revision=first_page['stack_revision']), 'stale_inventory_revision')
        return {'native_component_bytes': before['component_bytes'], 'ambient_json_omitted': True, 'full_metadata_hash_preserved': True,
                'attributes_available': ['count', 'damage', 'max_damage'], 'full_metadata_query_implemented': True,
                'player_and_container_multichunk_unicode_reconstruction': True, 'empty_cursor_query': True, 'changed_slot_chunk_rejected': True}

    fixture.case('large_components_bounded_observation_exact_transfer', ['ACT-14', 'OBS-01', 'OBS-05', 'VERIFY-03'], large_components)
