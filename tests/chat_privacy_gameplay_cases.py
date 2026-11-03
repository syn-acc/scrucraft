"""OBS-04 / ACT-12 / SDK-02: native private-message exclusion and public resync.

All identities and messages belong to the disposable fixture. Real human chat
delivery has separate live evidence; console tellraw exercises the private native
message path without generating enrollment codes or messaging real players.
"""
import json
import time
import uuid

from gameplay_cases import done
from isolated_game_fixture import wait_for


def run_cases(fixture, stream):
    def private_messages():
        stream.stop()
        public = 'PublicFixture'+uuid.uuid4().hex
        private = 'PrivateFixture'+uuid.uuid4().hex
        done(stream, stream.chat(public))
        row = wait_for(lambda: next((r for r in stream.observe().get('public_chat', [])
                                      if r.get('text') == public), None))
        assert row.get('id') and row.get('speaker') == 'VerifyBuilder' and row.get('at')
        start = stream.observe()['world_tick']
        fixture.console('tellraw VerifyBuilder '+json.dumps({'text': private}))
        sampled = 0
        deadline = time.monotonic()+8
        while stream.observe()['world_tick'] < start+20:
            assert time.monotonic() < deadline, 'Private-message observation window stalled'
            observation = stream.observe()
            assert private not in json.dumps(observation), 'Private system message entered SDK observations'
            sampled += 1
            time.sleep(.04)
        return {'public_message_id_present': True, 'sender_and_timestamp_present': True,
                'private_native_tellraw_excluded': True, 'native_ticks_checked': 20,
                'snapshots_checked': sampled, 'real_enrollment_code_generated': False}

    fixture.case('native_public_chat_excludes_private_system_message',
                 ['ACT-12', 'OBS-04', 'VERIFY-04'], private_messages)

    def chat_reconnect():
        tick = stream.observe()['world_tick']
        wait_for(lambda: stream.observe()['world_tick'] >= tick+25)
        first = 'BeforeReconnect'+uuid.uuid4().hex
        done(stream, stream.chat(first))
        rows = wait_for(lambda: stream.observe().get('public_chat')
                        if any(r.get('text') == first for r in stream.observe().get('public_chat', [])) else None)
        events = stream.chat_events()
        seen = []
        for _ in rows:
            event = next(events)
            seen.append(event.id)
            if event.text == first:
                break
        assert event.text == first
        old_sequence = stream.sequence
        stream.reconnect()
        tick = stream.observe()['world_tick']
        wait_for(lambda: stream.observe()['world_tick'] >= tick+25)
        second = 'AfterReconnect'+uuid.uuid4().hex
        done(stream, stream.chat(second))
        wait_for(lambda: any(r.get('text') == second for r in stream.observe().get('public_chat', [])))
        # A client-local sequence must survive reconnect; otherwise a paused
        # iterator can wait for an arbitrarily old cursor after reinitialization.
        assert stream.sequence > old_sequence, 'Subscription cursor reset across reconnect'
        resumed = next(events)
        assert resumed.text == second and resumed.id not in seen
        return {'same_subscription_resumed': True, 'old_messages_not_reemitted': True,
                'distinct_message_ids': True, 'client_sequence_monotonic': True}

    fixture.case('native_public_chat_subscription_reconnect_deduplication',
                 ['OBS-04', 'SDK-02', 'SDK-03'], chat_reconnect)
