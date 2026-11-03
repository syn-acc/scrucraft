"""Native receipt-liveness regressions in the disposable loopback world only."""
import copy
import time
import uuid

from gameplay_cases import done
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    def reset():
        stream.stop()
        fixture.console('tp VerifyBuilder 0.5 64 0.5')
        fixture.console('effect clear VerifyBuilder')
        fixture.console('effect give VerifyBuilder saturation 1 255 true')
        fixture.console('clear VerifyBuilder')
        fixture.console('fill -16 64 -16 26 70 16 air')
        fixture.console('fill -16 63 -16 26 63 16 stone')
        time.sleep(.3)
        done(stream, stream.select_slot(0))

    def long_action_terminal_recency():
        reset()
        done(stream, stream.sneak(True))
        movement = stream.move_to(20.5, 64, .5, ttl_seconds=30)
        wait_for(lambda: movement['id'] in stream.observe()['execution']['active_actions'])
        for index in range(80):
            done(stream, stream.look_at(-5, 65, 5 + index % 2))
        # Confirm the test actually aged a still-running action beyond the 64-row window.
        assert movement['id'] in stream.observe()['execution']['active_actions'], stream.observe()['execution']
        done(stream, stream.sneak(False))
        result = stream.wait_action(movement['id'], timeout=30)
        assert result['state'] in ('done', 'failed'), result
        assert not result.get('reason', '').startswith('outcome_unknown'), result
        if result['state'] == 'failed':
            assert result['reason'] in ('blocked', 'timeout', 'unreachable', 'node_limit'), result
        reconciled = stream.action_results(movement['id'])[0]
        assert reconciled['state'] == result['state'] and reconciled['reason'] == result['reason'], (result, reconciled)
        return {'instant_actions_while_running': 80, 'terminal': result['state'],
                'reason': result['reason'], 'native_tick': result.get('tick'), 'reconciliation_matches': True}

    fixture.case('long_action_terminal_survives_eighty_newer_actions', ['EXEC-01', 'EXEC-02', 'EXEC-04'], long_action_terminal_recency)

    def reduced_timeout_retransmission():
        reset()
        request_id = uuid.uuid4().hex
        done(stream, stream.select_slot(1, request_id=request_id))
        with fixture.gateway.changed:
            original = copy.deepcopy(fixture.gateway.actions['VerifyBuilder'][request_id]['control'])
        for index in range(80):
            done(stream, stream.look_at(-5, 65, index % 2))
        done(stream, stream.select_slot(2))
        wait_for(lambda: stream.observe()['selected_slot'] == 2)

        # Fault injection changes only delivery metadata on the private fixture bridge.
        # The gameplay command itself was submitted through the SDK above. Capture raw
        # Java frames so gateway-retained results cannot mask failure to resurface it.
        seen = []
        inject = []
        original_frame = fixture.gateway.frame
        original_control = fixture.gateway.realtime_control

        def capture_frame(observation):
            if observation.get('agent') == 'VerifyBuilder':
                seen.extend(dict(row) for row in observation.get('action_results', []) if row.get('id') == request_id)
            return original_frame(observation)

        def retransmit(name):
            grant = original_control(name)
            if name == 'VerifyBuilder' and inject and grant.get('lease_id'):
                grant['commands'] = list(grant.get('commands', [])) + [copy.deepcopy(inject[0])]
            return grant

        try:
            with fixture.gateway.changed:
                fixture.gateway.frame = capture_frame
                fixture.gateway.realtime_control = retransmit
            time.sleep(.25)
            assert not seen, 'Fixture did not age the native result outside the recent window'
            duplicate = copy.deepcopy(original)
            duplicate['timeout_ticks'] = max(1, original['timeout_ticks'] - 20)
            inject.append(duplicate)
            row = wait_for(lambda: next((r for r in seen if r['state'] == 'done'), None),
                           timeout=5, description='native cached result resurfaced with reduced delivery timeout')
            inject.clear()
            assert stream.observe()['selected_slot'] == 2, 'Derived-timeout retry re-executed slot selection'
            try:
                stream.select_slot(3, request_id=request_id)
            except Exception as error:
                assert getattr(error, 'status', None) == 409, repr(error)
            else:
                raise AssertionError('Changed semantic action reused the ID')
            assert stream.observe()['selected_slot'] == 2
            return {'timeout_before': original['timeout_ticks'], 'timeout_retry': duplicate['timeout_ticks'],
                    'native_result_resurfaced': row['state'], 'selected_slot_unchanged': 2,
                    'semantic_change_rejected': True, 'fault_injection': 'fixture bridge delivery metadata only'}
        finally:
            with fixture.gateway.changed:
                fixture.gateway.frame = original_frame
                fixture.gateway.realtime_control = original_control

    fixture.case('native_retry_ignores_reduced_delivery_budget_without_reexecution', ['EXEC-02', 'EXEC-04'], reduced_timeout_retransmission)

    def deferred_payload_outlives_recent_window():
        reset()
        request_id = uuid.uuid4().hex
        original_frame = fixture.gateway.frame
        mode = {'holding': True, 'partial_sent': False, 'latest_native_offer_tick': -1}
        core = {'id', 'state', 'reason', 'body_epoch', 'tick'}

        def delay_full_payload(observation):
            if observation.get('agent') != 'VerifyBuilder':
                return original_frame(observation)
            forwarded = dict(observation)
            rows = []
            for row in observation.get('action_results', []):
                if row.get('id') != request_id:
                    rows.append(row)
                    continue
                if 'blocks' in row:
                    mode['latest_native_offer_tick'] = observation['tick']
                if not mode['holding']:
                    rows.append(row)
                elif not mode['partial_sent']:
                    # Model a byte-budgeted frame whose terminal metadata precedes its payload.
                    rows.append({**{k: v for k, v in row.items() if k in core}, 'details_pending': True})
                    mode['partial_sent'] = True
            forwarded['action_results'] = rows
            return original_frame(forwarded)

        try:
            with fixture.gateway.changed:
                fixture.gateway.frame = delay_full_payload
            receipt = stream.query_blocks(target=[0, 64, 0], radius=1, request_id=request_id)
            wait_for(lambda: mode['partial_sent'], description='deferred terminal payload')
            for index in range(80):
                done(stream, stream.look_at(-5, 65, index % 2))
            latest_tick = stream.observe()['tick']
            wait_for(lambda: mode['latest_native_offer_tick'] >= latest_tick, timeout=5,
                     description='old unacknowledged payload remains offered outside recent 64')
            mode['holding'] = False
            result = done(stream, receipt, timeout=10)
            assert len(result['blocks']) == 27, result
            assert not result.get('details_pending'), result
            return {'newer_actions': 80, 'full_payload_blocks': 27,
                    'offered_after_recent_window': True, 'fault_injection': 'fixture delays full payload after partial metadata'}
        finally:
            with fixture.gateway.changed:
                fixture.gateway.frame = original_frame

    fixture.case('unacknowledged_full_payload_survives_eighty_newer_results', ['EXEC-02', 'EXEC-04', 'OBS-07'], deferred_payload_outlives_recent_window)

    def queued_delivery_budget_is_not_extended():
        reset()
        request_id = uuid.uuid4().hex
        original_control = fixture.gateway.realtime_control
        original_frame = fixture.gateway.frame
        starts = []

        def short_budget(name):
            grant = original_control(name)
            if name == 'VerifyBuilder':
                commands = []
                for command in grant.get('commands', []):
                    command = dict(command)
                    if command.get('id') == request_id:
                        command['timeout_ticks'] = 2
                    commands.append(command)
                grant['commands'] = commands
            return grant

        def started_tick(observation):
            if observation.get('agent') == 'VerifyBuilder':
                starts.extend(row['tick'] for row in observation.get('action_results', [])
                              if row.get('id') == request_id and row.get('state') == 'started')
            return original_frame(observation)

        try:
            with fixture.gateway.changed:
                fixture.gateway.realtime_control = short_budget
                fixture.gateway.frame = started_tick
            receipt = stream.move_to(20.5, 64, .5, request_id=request_id)
            result = stream.wait_action(receipt['id'], timeout=5)
            assert result['state'] == 'failed' and result['reason'] == 'timeout', result
            assert starts, 'No native start observation; cannot establish the execution tick budget'
            elapsed_ticks = result['tick'] - min(starts)
            assert 0 <= elapsed_ticks <= 2, (starts, result)
            return {'remaining_delivery_ticks': 2, 'native_ticks_until_timeout': elapsed_ticks,
                    'fault_injection': 'fixture simulates queue delay leaving a two-tick budget'}
        finally:
            with fixture.gateway.changed:
                fixture.gateway.realtime_control = original_control
                fixture.gateway.frame = original_frame

    fixture.case('navigation_preserves_two_tick_remaining_delivery_deadline', ['EXEC-02', 'EXEC-03', 'VERIFY-01'], queued_delivery_budget_is_not_extended)
