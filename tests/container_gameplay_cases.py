"""Native container/recipe edge cases in the disposable loopback fixture only."""
import json
import hashlib
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from gameplay_cases import done, quantity, slot
from isolated_game_fixture import wait_for, OWNER


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

    def concurrent_native_viewers():
        reset()
        fixture.console('setblock 2 64 0 chest')
        fixture.console('item replace block 2 64 0 container.0 with minecraft:diamond 4')
        viewer_name = 'Viewer' + uuid.uuid4().hex[:8]
        viewer = None
        evidence = {}
        try:
            viewer_client = fixture.client(viewer_name)
            fixture.console(f'tp {viewer_name} 0.5 64 -1.5')
            fixture.console(f'clear {viewer_name}')
            viewer = viewer_client.realtime().connect()
            wait_for(lambda: abs(viewer.observe()['position'][2] + 1.5) < .2)
            primary_open = container(stream.open_container(2, 64, 0))
            second_open = done(viewer, viewer.open_container(2, 64, 0))
            assert primary_open['session_id'] != second_open['session_id']
            assert stream.observe()['container']['open'] and viewer.observe()['container']['open']
            gate = threading.Barrier(2)

            def contend(connection, opened):
                gate.wait(timeout=5)
                receipt = connection.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 3,
                              session_id=opened['session_id'], revision=opened['revision'])
                return connection.wait_action(receipt['id'], timeout=15)

            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(contend, stream, primary_open)
                second = pool.submit(contend, viewer, second_open)
                outcomes = [first.result(timeout=20), second.result(timeout=20)]
            assert sorted(row['state'] for row in outcomes) == ['done', 'failed'], outcomes
            assert next(row for row in outcomes if row['state'] == 'failed')['reason'] == 'stale_container_revision', outcomes
            wait_for(lambda: quantity(stream, 'minecraft:diamond') + quantity(viewer, 'minecraft:diamond') == 3)
            primary_state = wait_for(lambda: (value if value.get('revision', 0) > primary_open['revision'] else None)
                                     if (value := stream.observe().get('container', {})) else None)
            remaining = next(row['count'] for row in primary_state['slots'] if row['inventory'] == 'container' and row['slot'] == 0)
            assert remaining == 1
            loser = stream if outcomes[0]['state'] == 'failed' else viewer
            loser_state = wait_for(lambda: (value if value.get('revision', 0) >
                                  (primary_open if loser is stream else second_open)['revision'] else None)
                                  if (value := loser.observe().get('container', {})) else None)
            recovered = done(loser, loser.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 1,
                             session_id=loser_state['session_id'], revision=loser_state['revision']))
            wait_for(lambda: quantity(stream, 'minecraft:diamond') + quantity(viewer, 'minecraft:diamond') == 4)
            chest_count = next(row['count'] for row in recovered['slots'] if row['inventory'] == 'container' and row['slot'] == 0)
            assert chest_count == 0
            evidence.update(native_viewers=2, human_or_gui_viewers=False, contested_requests=2,
                            successes=1, stale_revision_failures=1, fresh_revision_recovery=True,
                            primary_diamonds=quantity(stream, 'minecraft:diamond'),
                            second_diamonds=quantity(viewer, 'minecraft:diamond'), chest_diamonds=chest_count,
                            total_diamonds_before_fixture_cleanup=4)
            return evidence
        finally:
            if viewer is not None:
                try:
                    viewer.close()
                except Exception:
                    pass  # Authorized removal below revokes any remaining lease and native body.
            with fixture.gateway.changed:
                registered = fixture.gateway.db.execute('SELECT 1 FROM bodies WHERE name=?', (viewer_name,)).fetchone()
                if registered and not fixture.gateway.body(viewer_name)['data'].get('removed'):
                    owner = fixture.gateway.issue(OWNER['name'], 'player', player_uuid=OWNER['uuid'])
                    fixture.gateway.handle('DELETE', '/v1/agent',
                        {'Authorization': 'Bearer ' + owner, 'X-SCRU-Agent': viewer_name}, {})
            if registered:
                def removed():
                    with fixture.gateway.changed:
                        return (viewer_name not in fixture.gateway.body_connections and
                                fixture.gateway.body(viewer_name)['data'].get('removed', False))
                wait_for(removed, timeout=15, description='fixture second native viewer removed')
                evidence['fixture_second_body_removed'] = True

    fixture.case('container_two_native_viewers_contested_transfer_conservation', ['ACT-14', 'VERIFY-03'], concurrent_native_viewers)

    def disconnect_transfer_reconciliation():
        reset()
        fixture.console('setblock 2 64 0 chest')
        fixture.console('give VerifyBuilder diamond 5')
        wait_for(lambda: quantity(stream, 'minecraft:diamond') == 5)
        opened = container(stream.open_container(2, 64, 0))
        source = slot(stream, 'minecraft:diamond')
        request_id = uuid.uuid4().hex
        arguments = dict(session_id=opened['session_id'], revision=opened['revision'], request_id=request_id)
        receipt = stream.move_item({'inventory': 'player', 'slot': source}, {'inventory': 'container', 'slot': 0}, 2, **arguments)
        try:
            def native_finished():
                with fixture.gateway.changed:
                    row = fixture.gateway.actions.get('VerifyBuilder', {}).get(receipt['id'], {}).get('result', {})
                    if row.get('state') in {'failed', 'cancelled', 'unknown'}:
                        raise AssertionError(dict(row))
                    return dict(row) if row.get('state') == 'done' and not row.get('details_pending') else None
            # Wait through fixture instrumentation, deliberately not through the application's action handle.
            original = wait_for(native_finished, description='native transfer before disconnect')
            stream.connection.close()
            wait_for(lambda: stream.stopped.is_set(), description='SDK observes forced public disconnect')
            def lease_released():
                with fixture.gateway.changed:
                    return fixture.gateway.active('VerifyBuilder') is None
            wait_for(lease_released, description='public disconnect releases prior lease')
            stream.reconnect(attempts=1)
            reconciled = stream.action_results(request_id)[0]
            assert reconciled['state'] == 'done' and reconciled.get('moved') == 2, reconciled
            assert reconciled['body_epoch'] == original['body_epoch'] and reconciled['id'] == request_id
            wait_for(lambda: not stream.observe().get('container', {}).get('open', False), description='old container session released')
            reopened = container(stream.open_container(2, 64, 0))
            assert reopened['session_id'] != opened['session_id']
            try:
                stream.move_item({'inventory': 'player', 'slot': source}, {'inventory': 'container', 'slot': 0}, 2, **arguments)
            except Exception as error:
                assert getattr(error, 'status', None) == 409 and getattr(error, 'code', None) == 'action_belongs_to_previous_lease', repr(error)
            else:
                raise AssertionError('Previous-lease mutation was accepted for replay')
            wait_for(lambda: quantity(stream, 'minecraft:diamond') == 3)
            stored = next(row['count'] for row in reopened['slots'] if row['inventory'] == 'container' and row['slot'] == 0)
            assert stored == 2 and stored + quantity(stream, 'minecraft:diamond') == 5
            done(stream, stream.close_container(session_id=reopened['session_id'], revision=reopened['revision']))
            return {'exact_action_id_reconciled': True, 'native_executions': 1, 'moved': 2,
                    'prior_lease_replay_rejected': True, 'old_session_invalidated': True,
                    'player_diamonds': 3, 'chest_diamonds': 2, 'total_diamonds': 5,
                    'disconnect_timing': 'after native completion, before application handle wait; no simulated lost network frame'}
        finally:
            with fixture.gateway.changed:
                needs_reconnect = stream.stopped.is_set() or fixture.gateway.active('VerifyBuilder') is None
            if needs_reconnect:
                stream.reconnect(attempts=1)

    fixture.case('container_disconnect_reconcile_without_mutation_replay', ['ACT-14', 'ACT-16', 'EXEC-04', 'VERIFY-03'], disconnect_transfer_reconciliation)

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

    def double_chest_success():
        reset()
        fixture.console('setblock 2 64 0 minecraft:chest[facing=north,type=left]')
        fixture.console('setblock 3 64 0 minecraft:chest[facing=north,type=right]')
        fixture.console('give VerifyBuilder diamond 3')
        wait_for(lambda: quantity(stream, 'minecraft:diamond') == 3)
        opened = container(stream.open_container(2, 64, 0))
        storage = [row for row in opened['slots'] if row['inventory'] == 'container']
        player = [row for row in opened['slots'] if row['inventory'] == 'player']
        assert len(storage) == 54 and {row['slot'] for row in storage} == set(range(54)), opened
        assert len(player) == 36 and {row['slot'] for row in player} == set(range(36)), opened
        source = slot(stream, 'minecraft:diamond')
        moved = container(stream.move_item({'inventory': 'player', 'slot': source}, {'inventory': 'container', 'slot': 53}, 3,
                          session_id=opened['session_id'], revision=opened['revision']))
        assert next(row['count'] for row in moved['slots'] if row['inventory'] == 'container' and row['slot'] == 53) == 3
        wait_for(lambda: quantity(stream, 'minecraft:diamond') == 0)
        moved = container(stream.move_item({'inventory': 'container', 'slot': 53}, {'inventory': 'player', 'slot': source}, 1,
                          session_id=moved['session_id'], revision=moved['revision']))
        wait_for(lambda: quantity(stream, 'minecraft:diamond') == 1)
        done(stream, stream.close_container(session_id=moved['session_id'], revision=moved['revision']))
        reopened = container(stream.open_container(2, 64, 0))
        stored = next(row for row in reopened['slots'] if row['inventory'] == 'container' and row['slot'] == 53)
        assert stored['item'] == 'minecraft:diamond' and stored['count'] == 2, reopened
        assert stored['count'] + quantity(stream, 'minecraft:diamond') == 3
        done(stream, stream.close_container(session_id=reopened['session_id'], revision=reopened['revision']))
        return {'storage_slots': 54, 'player_slots': 36, 'second_menu_half_slot': 53,
                'deposited': 3, 'withdrawn': 1, 'persisted_after_reopen': 2, 'player_diamonds': 1, 'total_diamonds': 3}

    fixture.case('double_chest_complete_layout_second_half_conservation', ['ACT-13', 'ACT-14', 'OBS-05', 'VERIFY-03'], double_chest_success)

    def recipe_discovery():
        reset()
        page = done(stream, stream.query_recipes(offset=0, limit=2))
        assert len(page['recipes']) == 2 and page['total'] >= 2 and page['next_offset'] == 2, page
        for recipe in page['recipes']:
            assert recipe['ingredients'], recipe
            if recipe['craft_supported']:
                assert recipe['supported'] and recipe['output']['count'] > 0, recipe
                assert recipe['count_semantics'] == 'recipe_executions', recipe
            else:
                assert recipe['execution'] == 'native_world_ticks' and recipe['native_recipe'], recipe
        second = done(stream, stream.query_recipes(offset=page['next_offset'], limit=2))
        assert not ({r['recipe_id'] for r in page['recipes']} & {r['recipe_id'] for r in second['recipes']}), (page, second)
        result = failed(stream.craft('minecraft:iron_ingot_from_smelting_iron_ore', 1), 'machine_processing_required')
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

    def administrator_order_stop():
        reset()
        fixture.console('setblock 2 64 0 chest')
        fixture.console('give VerifyBuilder diamond 2')
        wait_for(lambda: quantity(stream, 'minecraft:diamond') == 2)
        opened = container(stream.open_container(2, 64, 0))
        source = slot(stream, 'minecraft:diamond')
        moved = container(stream.move_item({'inventory': 'player', 'slot': source}, {'inventory': 'container', 'slot': 0}, 1,
                          session_id=opened['session_id'], revision=opened['revision']))
        with fixture.gateway.changed:
            owner_token = fixture.gateway.issue(OWNER['name'], 'player', player_uuid=OWNER['uuid'])
        owner_headers = {'Authorization': 'Bearer ' + owner_token, 'X-SCRU-Agent': 'VerifyBuilder'}
        try:
            # This invokes the shared native order recorder as Server, not a human chat event.
            fixture.console('synagent order VerifyBuilder, stop')
            def suspended():
                with fixture.gateway.changed:
                    return fixture.gateway.body('VerifyBuilder')['data'].get('suspended', False)
            wait_for(suspended, description='administrator order persistent stop latch')
            closed = wait_for(lambda: (value if not value.get('open', False) else None)
                              if (value := stream.observe().get('container', {})) else None)
            assert closed['closed_session_id'] == opened['session_id'], closed
            assert quantity(stream, 'minecraft:diamond') == 1
            try:
                stream.reconnect(attempts=1)
            except Exception as error:
                assert getattr(error, 'status', None) == 423, repr(error)
            else:
                raise AssertionError('Reconnect bypassed the persistent administrator stop')
            assert suspended()
            with fixture.gateway.changed:
                resumed = fixture.gateway.handle('POST', '/v1/resume', owner_headers, {})
            assert resumed['status'] == 'resumed', resumed
            stream.reconnect(attempts=1)
            reopened = container(stream.open_container(2, 64, 0))
            stored = next(row['count'] for row in reopened['slots'] if row['inventory'] == 'container' and row['slot'] == 0)
            assert stored == 1 and quantity(stream, 'minecraft:diamond') == 1
            done(stream, stream.close_container(session_id=reopened['session_id'], revision=reopened['revision']))
            return {'source': 'administrator console synagent order through shared native recordOrder',
                    'actual_human_chat_event_verified': False, 'persistent_stop_closed_session': True,
                    'reconnect_denied_423_until_owner_resume': True, 'deliberate_owner_resume_verified': True,
                    'cursor_fixture': 'empty', 'chest_diamonds': stored, 'player_diamonds': 1, 'total_diamonds': 2}
        finally:
            # Leave the shared synthetic test body controllable even if an assertion fails.
            with fixture.gateway.changed:
                if fixture.gateway.body('VerifyBuilder')['data'].get('suspended'):
                    fixture.gateway.handle('POST', '/v1/resume', owner_headers, {})
                needs_reconnect = stream.stopped.is_set() or fixture.gateway.active('VerifyBuilder') is None
            if needs_reconnect:
                stream.reconnect(attempts=1)

    fixture.case('administrator_order_container_stop_persistence_owner_resume', ['ACT-13', 'ACT-16', 'EXEC-03', 'VERIFY-04'], administrator_order_stop)

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

    if getattr(fixture.args, 'full_pack_mods', None):
        run_industrial_cases(fixture, stream, reset, failed, container)


def run_industrial_cases(fixture, stream, reset, failed, container):
    """Exact locked Create pack only. Infrastructure is seeded; outputs are never seeded."""
    def current():
        value = stream.observe().get('container', {})
        assert value.get('open') and value.get('kind') == 'machine_item_port', value
        return value

    def row(state, index):
        return next(item for item in state['slots'] if item['inventory'] == 'container' and item['slot'] == index)

    def amount(state, item):
        return sum(r['count'] for r in state['slots'] if r['inventory'] == 'container' and r.get('item') == item)

    def transfer(source, dest, count):
        state = current()
        return container(stream.move_item(source, dest, count, session_id=state['session_id'], revision=state['revision']))

    def output(item):
        state = current()
        return state if amount(state, item) else None

    def depot_contract():
        reset()
        fixture.console('setblock 2 64 0 create:depot')
        fixture.console('give VerifyBuilder minecraft:iron_ingot 3')
        wait_for(lambda: quantity(stream, 'minecraft:iron_ingot') == 3)
        opened = container(stream.open_container(2, 64, 0))
        assert opened['kind'] == 'machine_item_port' and len([r for r in opened['slots'] if r['inventory'] == 'container']) == 9
        before = quantity(stream, 'minecraft:iron_ingot')
        failed(stream.move_item({'inventory': 'player', 'slot': slot(stream, 'minecraft:iron_ingot')},
                               {'inventory': 'container', 'slot': 1}, 1,
                               session_id=opened['session_id'], revision=opened['revision']), 'slot_rule_rejected')
        assert quantity(stream, 'minecraft:iron_ingot') == before
        placed = transfer({'inventory': 'player', 'slot': slot(stream, 'minecraft:iron_ingot')}, {'inventory': 'container', 'slot': 0}, 2)
        assert row(placed, 0)['count'] == 2 and row(placed, 0)['role'] == 'input_or_held'
        full = stream.inventory_slot(0, inventory='container', session_id=placed['session_id'], revision=placed['revision'])
        assert full['item'] == 'minecraft:iron_ingot' and full['count'] == 2
        failed(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 1}, 1,
                               session_id=opened['session_id'], revision=opened['revision']), 'stale_container_revision')
        returned = transfer({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 1}, 2)
        wait_for(lambda: quantity(stream, 'minecraft:iron_ingot') == 3)
        assert amount(returned, 'minecraft:iron_ingot') == 0
        fixture.console('setblock 2 64 0 air')
        wait_for(lambda: not stream.observe().get('container', {}).get('open'), description='removed machine invalidates port')
        return {'native_port': 'create:depot', 'native_slots': 9, 'input_output_rules': True,
                'full_metadata': True, 'stale_revision_rejected': True, 'removed_port_closed': True, 'iron_ingots_conserved': 3}

    fixture.case('create_depot_native_port_exact_transfer', ['ACT-13', 'ACT-14', 'OBS-05', 'VERIFY-03'], depot_contract)

    def powered_press():
        reset()
        fixture.console('setblock 2 64 0 create:depot')
        fixture.console('setblock 2 66 0 create:mechanical_press[facing=east]')
        fixture.console('give VerifyBuilder minecraft:iron_ingot 1')
        wait_for(lambda: quantity(stream, 'minecraft:iron_ingot') == 1)
        recipe = stream.recipe('create:pressing/iron_ingot')
        assert not recipe['craft_supported'] and recipe['execution'] == 'native_world_ticks'
        assert recipe['native_recipe']['type'] == 'create:pressing' and recipe['native_recipe']['results'][0]['id'] == 'create:iron_sheet'
        failed(stream.craft('create:pressing/iron_ingot', 1), 'machine_processing_required')
        container(stream.open_container(2, 64, 0))
        inserted = transfer({'inventory': 'player', 'slot': slot(stream, 'minecraft:iron_ingot')}, {'inventory': 'container', 'slot': 0}, 1)
        time.sleep(1)
        assert amount(current(), 'minecraft:iron_ingot') == 1 and amount(current(), 'create:iron_sheet') == 0
        # Native creative motor is fixture infrastructure, not a claimed survival-crafted power source.
        fixture.console('setblock 3 66 0 create:creative_motor[facing=west]{ScrollValue:64}')
        processed = wait_for(lambda: output('create:iron_sheet'), timeout=20, description='native powered press output')
        assert amount(processed, 'minecraft:iron_ingot') == 0 and amount(processed, 'create:iron_sheet') == 1
        failed(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 1,
                               session_id=inserted['session_id'], revision=inserted['revision']), 'stale_container_revision')
        result_slot = next(r['slot'] for r in processed['slots'] if r['inventory'] == 'container' and r.get('item') == 'create:iron_sheet')
        result = transfer({'inventory': 'container', 'slot': result_slot}, {'inventory': 'player', 'slot': 0}, 1)
        wait_for(lambda: quantity(stream, 'create:iron_sheet') == 1)
        assert amount(result, 'create:iron_sheet') == 0 and quantity(stream, 'minecraft:iron_ingot') == 0
        return {'recipe': 'create:pressing/iron_ingot', 'input_ingots': 1, 'output_sheets': 1,
                'unpowered_no_processing': True, 'processing_revision_changed': True,
                'power': 'fixture-seeded native creative motor 64 rpm', 'machine_output_seeded': False,
                'survival_power_construction_verified': False}

    fixture.case('create_powered_press_depot_real_processing', ['ACT-14', 'ACT-15', 'OBS-05', 'OBS-06', 'VERIFY-03', 'VERIFY-06'], powered_press)

    def powered_mixer():
        reset()
        fixture.console('setblock 2 64 0 create:basin')
        fixture.console('setblock 2 66 0 create:mechanical_mixer')
        fixture.console('setblock 3 66 0 create:cogwheel[axis=y]')
        fixture.console('give VerifyBuilder minecraft:andesite 1')
        fixture.console('give VerifyBuilder minecraft:iron_nugget 1')
        wait_for(lambda: quantity(stream, 'minecraft:andesite') == quantity(stream, 'minecraft:iron_nugget') == 1)
        recipe = stream.recipe('create:mixing/andesite_alloy')
        assert recipe['native_recipe']['type'] == 'create:mixing' and not recipe['craft_supported']
        assert recipe['native_recipe']['results'][0]['id'] == 'create:andesite_alloy'
        opened = container(stream.open_container(2, 64, 0))
        assert len([r for r in opened['slots'] if r['inventory'] == 'container']) == 18
        failed(stream.move_item({'inventory': 'player', 'slot': slot(stream, 'minecraft:andesite')},
                               {'inventory': 'container', 'slot': 9}, 1,
                               session_id=opened['session_id'], revision=opened['revision']), 'slot_rule_rejected')
        transfer({'inventory': 'player', 'slot': slot(stream, 'minecraft:andesite')}, {'inventory': 'container', 'slot': 0}, 1)
        transfer({'inventory': 'player', 'slot': slot(stream, 'minecraft:iron_nugget')}, {'inventory': 'container', 'slot': 1}, 1)
        time.sleep(1)
        assert amount(current(), 'minecraft:andesite') == amount(current(), 'minecraft:iron_nugget') == 1
        assert amount(current(), 'create:andesite_alloy') == 0
        fixture.console('setblock 3 67 0 create:creative_motor[facing=down]{ScrollValue:64}')
        processed = wait_for(lambda: output('create:andesite_alloy'), timeout=25, description='native powered mixer output')
        assert amount(processed, 'minecraft:andesite') == amount(processed, 'minecraft:iron_nugget') == 0
        assert amount(processed, 'create:andesite_alloy') == 1
        result_slot = next(r['slot'] for r in processed['slots'] if r['inventory'] == 'container' and r.get('item') == 'create:andesite_alloy')
        result = transfer({'inventory': 'container', 'slot': result_slot}, {'inventory': 'player', 'slot': 0}, 1)
        wait_for(lambda: quantity(stream, 'create:andesite_alloy') == 1)
        assert amount(result, 'create:andesite_alloy') == 0
        return {'recipe': 'create:mixing/andesite_alloy', 'native_slots': 18, 'input_andesite': 1, 'input_iron_nugget': 1,
                'output_alloy': 1, 'unpowered_no_processing': True, 'output_insertion_rejected': True,
                'power': 'fixture-seeded native creative motor and cogwheel 64 rpm', 'machine_output_seeded': False,
                'survival_power_construction_verified': False}

    fixture.case('create_powered_mixer_basin_real_processing', ['ACT-14', 'ACT-15', 'OBS-05', 'OBS-06', 'VERIFY-03', 'VERIFY-06'], powered_mixer)

    def powered_millstone():
        reset()
        fixture.console('setblock 2 64 0 create:millstone')
        fixture.console('give VerifyBuilder minecraft:wheat 16')
        wait_for(lambda: quantity(stream, 'minecraft:wheat') == 16)
        recipe = stream.recipe('create:milling/wheat')
        native = recipe['native_recipe']
        assert native['type'] == 'create:milling' and native['processing_time'] == 150
        assert any(r.get('chance') == .25 and r['id'] == 'minecraft:wheat_seeds' for r in native['results']), native
        assert any(r.get('chance') == .25 and r.get('count') == 2 and r['id'] == 'create:wheat_flour' for r in native['results']), native
        opened = container(stream.open_container(2, 64, 0))
        assert len([r for r in opened['slots'] if r['inventory'] == 'container']) == 10
        inserted = transfer({'inventory': 'player', 'slot': slot(stream, 'minecraft:wheat')}, {'inventory': 'container', 'slot': 0}, 16)
        failed(stream.move_item({'inventory': 'container', 'slot': 0}, {'inventory': 'player', 'slot': 0}, 1,
                               session_id=inserted['session_id'], revision=inserted['revision']), 'slot_rule_rejected')
        time.sleep(1)
        assert amount(current(), 'minecraft:wheat') == 16 and amount(current(), 'create:wheat_flour') == 0
        fixture.console('setblock 2 63 0 create:creative_motor[facing=up]{ScrollValue:256}')
        batches = []
        for batch in range(2):
            if batch:
                fixture.console('give VerifyBuilder minecraft:wheat 16')
                wait_for(lambda: quantity(stream, 'minecraft:wheat') == 16)
                # Inventory mutation also changes revision; wait for the matching port snapshot.
                wait_for(lambda: sum(r['count'] for r in current()['slots'] if r['inventory'] == 'player' and r.get('item') == 'minecraft:wheat') == 16)
                transfer({'inventory': 'player', 'slot': slot(stream, 'minecraft:wheat')}, {'inventory': 'container', 'slot': 0}, 16)
            processed = wait_for(lambda: current() if amount(current(), 'minecraft:wheat') == 0 else None,
                                 timeout=35, description='native 16-wheat milling batch')
            flour, seeds = amount(processed, 'create:wheat_flour'), amount(processed, 'minecraft:wheat_seeds')
            # Create rolls chance independently for each item in a counted ProcessingOutput.
            # A count2/chance.25 entry can yield zero, one or two bonus flour, not only pairs.
            assert 16 <= flour <= 48 and 0 <= seeds <= 16, processed
            batches.append({'wheat_consumed': 16, 'flour_actual': flour, 'seed_actual': seeds})
            for item, destination in [('create:wheat_flour', 2 + batch), ('minecraft:wheat_seeds', 4 + batch)]:
                while amount(current(), item):
                    source = next(r for r in current()['slots'] if r['inventory'] == 'container' and r.get('item') == item)
                    transfer({'inventory': 'container', 'slot': source['slot']}, {'inventory': 'player', 'slot': destination}, source['count'])
            assert not any(r['count'] for r in current()['slots'] if r['inventory'] == 'container')
        flour_total, seeds_total = sum(b['flour_actual'] for b in batches), sum(b['seed_actual'] for b in batches)
        wait_for(lambda: quantity(stream, 'create:wheat_flour') == flour_total and quantity(stream, 'minecraft:wheat_seeds') == seeds_total)
        state = current()
        done(stream, stream.close_container(session_id=state['session_id'], revision=state['revision']))
        fixture.console('give VerifyBuilder minecraft:water_bucket 1')
        wait_for(lambda: quantity(stream, 'minecraft:water_bucket') == 1)
        done(stream, stream.craft('create:crafting/appliances/dough', 1))
        wait_for(lambda: quantity(stream, 'create:dough') == quantity(stream, 'minecraft:bucket') == 1)
        assert quantity(stream, 'minecraft:water_bucket') == 0 and quantity(stream, 'create:wheat_flour') == flour_total - 1
        # Prove real furnace ticks on one dough; the separate 32-bread survival journey remains pending.
        fixture.console('setblock 0 64 2 furnace[facing=north]')
        fixture.console('give VerifyBuilder minecraft:coal 1')
        wait_for(lambda: quantity(stream, 'minecraft:coal') == 1)
        furnace = container(stream.open_container(0, 64, 2))
        furnace = container(stream.move_item({'inventory': 'player', 'slot': slot(stream, 'create:dough')}, {'inventory': 'container', 'slot': 0}, 1,
                                            session_id=furnace['session_id'], revision=furnace['revision']))
        container(stream.move_item({'inventory': 'player', 'slot': slot(stream, 'minecraft:coal')}, {'inventory': 'container', 'slot': 1}, 1,
                                   session_id=furnace['session_id'], revision=furnace['revision']))
        baked = wait_for(lambda: stream.observe().get('container') if any(r.get('item') == 'minecraft:bread' and r['count'] == 1
                         for r in stream.observe().get('container', {}).get('slots', []) if r['inventory'] == 'container') else None,
                         timeout=20, description='native furnace bakes Create dough')
        container(stream.move_item({'inventory': 'container', 'slot': 2}, {'inventory': 'player', 'slot': 8}, 1,
                                   session_id=baked['session_id'], revision=baked['revision']))
        wait_for(lambda: quantity(stream, 'minecraft:bread') == 1)
        assert quantity(stream, 'minecraft:bucket') == 1 and quantity(stream, 'minecraft:wheat_seeds') == seeds_total
        return {'recipe': 'create:milling/wheat', 'batches': batches, 'flour_total': flour_total, 'seeds_total': seeds_total,
                'all_native_byproducts_collected': True, 'input_extraction_denied_by_native_port': True,
                'dough_crafted': 1, 'empty_buckets_preserved': 1, 'furnace_bread': 1,
                'power': 'fixture-seeded native creative motor 256 rpm', 'machine_output_seeded': False,
                'waterwheel_and_32_bread_survival_journey_verified': False}

    fixture.case('create_millstone_two_batches_dough_furnace_native_chain',
                 ['ACT-13', 'ACT-14', 'ACT-15', 'OBS-05', 'OBS-06', 'VERIFY-03', 'VERIFY-06'], powered_millstone)
