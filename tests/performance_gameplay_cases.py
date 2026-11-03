"""Ten-body actual Java response measurements; thresholds live in docs/verification.md."""
import concurrent.futures
import json
import math
from pathlib import Path
import socket
import threading
import time
import uuid

from gameplay_cases import done


def percentiles(values):
    values = sorted(values)
    if not values:
        return {}
    return {key: round(values[min(len(values)-1, math.ceil(p * len(values))-1)], 3)
            for key, p in [('p50', .5), ('p95', .95), ('p99', .99), ('max', 1)]}


def cpu_sample():
    """Whole Python process, plus inherited Linux cgroup diagnostics when available."""
    result = {'process_cpu_seconds': time.process_time()}
    try:
        membership = Path('/proc/self/cgroup').read_text().splitlines()
        relative = next(line.split(':', 2)[2] for line in membership if line.startswith('0::'))
        root = Path('/sys/fs/cgroup').resolve()
        group = (root / relative.lstrip('/')).resolve()
        if group != root and root not in group.parents:
            raise ValueError('Cgroup path outside cgroup mount')
        values = {}
        for line in (group / 'cpu.stat').read_text().splitlines():
            key, value = line.split()
            values[key] = int(value)
        result['cgroup_cpu_stat'] = values
        result['cgroup_cpu_max'] = (group / 'cpu.max').read_text().strip()
        result['cgroup_scope'] = 'Current process cgroup; includes inherited JVM/nginx and any other members'
    except (OSError, ValueError, StopIteration) as error:
        result['cgroup_unavailable'] = type(error).__name__
    return result


def cpu_delta(before, after, seconds):
    value = after['process_cpu_seconds'] - before['process_cpu_seconds']
    result = {'process_cpu_seconds': value, 'process_cpu_percent': value / seconds * 100 if seconds > 0 else None,
              'process_scope': 'Fixture Python process: gateway, websocket internals, SDK clients and watchers; excludes child JVM/nginx',
              'cgroup_diagnostic_only': True}
    if 'cgroup_cpu_stat' in before and 'cgroup_cpu_stat' in after:
        result['cgroup_cpu_stat_delta'] = {key: end - before['cgroup_cpu_stat'][key]
            for key, end in after['cgroup_cpu_stat'].items() if key in before['cgroup_cpu_stat']}
        result['cgroup_cpu_max'] = after['cgroup_cpu_max']
        result['cgroup_scope'] = after['cgroup_scope']
    else:
        result['cgroup_unavailable'] = after.get('cgroup_unavailable', before.get('cgroup_unavailable'))
    return result


def reconcile_failed_actions(fixture, streams, failures, attempts):
    """Read original IDs until their original TTL; no replay, new lease, or resume."""
    from scru_minecraft import AgentClient
    targets = {index: attempt for index, attempt in attempts.items() if attempt.get('id') and not attempt.get('completed')}
    started = time.monotonic()
    evidence = {'diagnostic_only': True, 'excluded_from_steady_state_window': True,
                'mutation_replay': False, 'final_expiry_read_timeout_seconds': .25,
                'original_action_ids': [r['id'] for r in targets.values()], 'actions': []}
    readers = {}
    records = {}
    for index, attempt in targets.items():
        source = streams[index].client
        readers[index] = AgentClient(source.url, source.token, source.agent, timeout=1, allow_local_http=True)
        records[index] = {'body': index, 'id': attempt['id'], 'body_epoch': attempt['epoch'],
                          'original_ttl_seconds': attempt['ttl'], 'acknowledged': attempt.get('acknowledged', False),
                          'reads': [], 'terminal_observed': False}
    while targets:
        for index, attempt in list(targets.items()):
            remaining = attempt['deadline'] - time.monotonic()
            record = records[index]
            final_read = remaining <= 0
            if final_read:
                record['diagnostic_deadline_reached'] = True
            reader = readers[index]
            reader.timeout = .25 if final_read else min(1, remaining)
            try:
                result = reader.action_results(attempt['id'])[0]
                record['reads'].append({'at_seconds': time.monotonic() - started, 'result': result})
                record['final_result'] = result
                record['epoch_matches'] = result.get('body_epoch') in (None, attempt['epoch'])
                terminal = result.get('state') in {'done', 'failed', 'cancelled', 'unknown'} and not result.get('details_pending')
                if terminal:
                    record['terminal_observed'] = True
                    targets.pop(index)
            except Exception as error:
                record['reads'].append({'at_seconds': time.monotonic() - started, 'error': type(error).__name__})
            if final_read:
                targets.pop(index, None)
        if targets:
            time.sleep(min(.5, max(0, max(r['deadline'] for r in targets.values()) - time.monotonic())))
    for index, record in records.items():
        # Capture both received views without generating or replaying a gameplay action.
        stream = streams[index]
        fields = ('body_epoch', 'tick', 'world_tick', 'captured_at_ms', 'gateway_received_at_ms', 'body_receive_lag_ms',
                  'position', 'health', 'food', 'execution', 'movement')
        with fixture.gateway.changed:
            native = fixture.gateway.frames.get(stream.client.agent, {})
            record['latest_gateway_native_observation'] = {key: native.get(key) for key in fields}
            native_time = native.get('captured_at_ms')
            record['gateway_native_capture_age_ms'] = time.time_ns() // 1_000_000 - native_time if isinstance(native_time, (int, float)) else None
        try:
            observation = stream.observe()
            record['sdk_observation'] = {key: observation.get(key) for key in fields}
        except Exception as error:
            record['sdk_observation_error'] = type(error).__name__
        evidence['actions'].append(record)
    evidence['seconds'] = time.monotonic() - started
    return evidence



class SlowObserver:
    """An authenticated observer that never requests, renews or releases a lease."""
    def __init__(self, stream, port):
        from websockets.sync.client import connect
        self.socket = socket.create_connection(('127.0.0.1', port), timeout=8)
        self.connection = None
        self.evidence = {'agent': stream.client.agent, 'lease_operations': 0,
                         'requested_receive_buffer_bytes': 4096, 'max_queue': 1,
                         'resume_frame_limit': 256, 'resume_timeout_seconds': 10}
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            self.evidence['actual_receive_buffer_bytes'] = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            self.connection = connect(f'ws://127.0.0.1:{port}/v1/events', sock=self.socket,
                                      max_size=1048576, max_queue=1, compression=None,
                                      ping_interval=None, open_timeout=8, close_timeout=2, proxy=None)
            self.connection.send(json.dumps({'token': stream.client.token, 'agent': stream.client.agent}))
            first = json.loads(self.connection.recv(timeout=8))
            assert first['type'] == 'snapshot', 'Observer authentication did not produce a snapshot'
            self.evidence.update(initial_tick=first['observation']['tick'], initial_sequence=first['sequence'])
            self.pause_started = time.monotonic()
        except Exception:
            self.close()
            raise

    def resume(self, controlling_stream):
        """Bounded recovery proves coalescing or explicit disconnection, not just connection setup."""
        from websockets.exceptions import ConnectionClosed
        resumed = time.monotonic()
        self.evidence['application_unread_seconds'] = resumed-self.pause_started
        self.evidence['state_before_resume'] = self.connection.state.name
        # Remove the deliberate receive-window constraint while inspecting recovery.
        # The 4 KiB request applies throughout the concurrent measured load above.
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256*1024)
        except OSError:
            pass  # A server-closed observer is also an acceptable isolation outcome.
        frames = []
        previous_tick = self.evidence['initial_tick']
        previous_sequence = self.evidence['initial_sequence']
        coalesced_gap = 0
        caught_up = False
        disconnected = False
        while len(frames) < 256 and time.monotonic()-resumed < 10:
            try:
                event = json.loads(self.connection.recv(timeout=min(1, max(.01, 10-(time.monotonic()-resumed)))))
            except TimeoutError:
                continue
            except ConnectionClosed as error:
                disconnected = True
                self.evidence['disconnect_exception'] = type(error).__name__
                self.evidence['server_close_code'] = error.rcvd.code if error.rcvd else None
                break
            assert event.get('type') == 'snapshot', 'Lease-free observer received a non-snapshot message'
            tick, sequence = event['observation']['tick'], event['sequence']
            assert sequence > previous_sequence and tick >= previous_tick, (previous_sequence, sequence, previous_tick, tick)
            tick_gap = tick-previous_tick
            if sequence == previous_sequence+1:
                coalesced_gap = max(coalesced_gap, tick_gap)
            current_tick = controlling_stream.observe()['tick']
            lag = max(0, current_tick-tick)
            frames.append({'tick': tick, 'sequence': sequence, 'tick_gap': tick_gap, 'current_tick_lag': lag})
            previous_tick, previous_sequence = tick, sequence
            if lag <= 20:
                caught_up = True
                break
        self.evidence.update(resume_seconds=time.monotonic()-resumed, drained_frames=frames,
                             disconnected=disconnected, caught_up=caught_up,
                             largest_coalesced_tick_gap=coalesced_gap)
        # A full-duration unread stream must either be disconnected or skip obsolete
        # snapshots and recover promptly. Merely opening an extra socket cannot pass.
        assert disconnected or (caught_up and coalesced_gap > 20), self.evidence
        self.evidence['isolation_behavior'] = 'server_disconnected_slow_observer' if disconnected else 'bounded_backlog_and_latest_state_catchup'
        return self.evidence

    def close(self):
        try:
            if self.connection is not None:
                self.connection.close()
        finally:
            self.socket.close()
            self.evidence['client_socket_closed'] = self.socket.fileno() == -1


def run_cases(fixture, seconds=300):
    if seconds < 300:
        raise ValueError('The recorded VERIFY-05 steady-state acceptance window is at least five minutes')

    def measure():
        streams = []
        rows = []
        observations = []
        failures = []
        stop = threading.Event()
        last_observations = {}
        report = None
        slow_observer = None
        slow_evidence = None
        startup = []
        attempts = {}
        cpu_before = cpu_after = None
        failure_reconciliation = None
        setup_started = time.monotonic()
        try:
            fixture.console('effect give VerifyBuilder saturation 1 255 true')
            # Reuse the existing body; total is ten, matching the configured cap.
            with fixture.gateway.changed:
                from scru_minecraft import AgentClient
                owner = fixture.gateway.member('FixtureOwner')
                token = fixture.gateway.issue(owner['name'], 'agent', 'VerifyBuilder', player_uuid=owner['uuid'])
            client = AgentClient(fixture.public_url, token, 'VerifyBuilder', allow_local_http=True, timeout=8)
            connect_started = time.monotonic()
            streams.append(client.realtime().connect())
            startup.append({'body': 0, 'existing_body': True,
                            'connect_seconds': time.monotonic()-connect_started})
            for index in range(1, 10):
                time.sleep(5.05)  # Respect owner provisioning limits; this is setup, not measured gameplay.
                provision_started = time.monotonic()
                load_client = fixture.client('VerifyLoad' + str(index))
                connect_started = time.monotonic()
                streams.append(load_client.realtime().connect())
                startup.append({'body': index, 'existing_body': False,
                                'prepare_seconds': connect_started-provision_started,
                                'connect_seconds': time.monotonic()-connect_started})
            # This peer authenticates only: it must never interfere with the body's
            # controlling lease, even when it stalls or disconnects under backpressure.
            controlling_lease = streams[0].lease
            slow_observer = SlowObserver(streams[0], fixture.public_port)
            initial = [(s.observe()['tick'], time.monotonic()) for s in streams]
            began = time.monotonic()
            cpu_before = cpu_sample()
            setup_seconds = began-setup_started

            def watch(index, stream):
                previous = None
                while not stop.wait(.01):
                    try:
                        obs = stream.observe()
                    except Exception as error:
                        failures.append({'body': index, 'phase': 'observation', 'error': str(error),
                                         'diagnostics': stream.diagnostics()})
                        stop.set()
                        return
                    last_observations[index] = (obs, time.monotonic())
                    sample = (obs.get('tick'), obs.get('body_epoch'))
                    now = time.monotonic()
                    if previous is not None and sample != previous[0]:
                        measured = {'body': index, 'gap_ms': (now-previous[1])*1000,
                            'average_tick_ms': obs.get('average_tick_ms'),
                            'observation_ms': obs.get('observation_ms'),
                            'captured_at_ms': obs.get('captured_at_ms'),
                            'gateway_received_at_ms': obs.get('gateway_received_at_ms'),
                            'body_receive_lag_ms': obs.get('body_receive_lag_ms'),
                            'body_receive_clock_skew_ms': obs.get('body_receive_clock_skew_ms')}
                        capture = obs.get('captured_at_ms')
                        if isinstance(capture, (int, float)):
                            age = time.time_ns() // 1_000_000 - capture
                            measured['sdk_observed_capture_age_ms'] = age if age >= 0 else None
                            if age < 0:
                                measured['sdk_capture_clock_skew_ms'] = -age
                        received = obs.get('gateway_received_at_ms')
                        if isinstance(received, (int, float)):
                            age = time.time_ns() // 1_000_000 - received
                            measured['sdk_after_gateway_receive_age_ms'] = age if age >= 0 else None
                            if age < 0:
                                measured['sdk_gateway_clock_skew_ms'] = -age
                        observations.append(measured)
                    if previous is None or sample != previous[0]:
                        previous = (sample, now)

            watchers = [threading.Thread(target=watch, args=(i, s), daemon=True) for i, s in enumerate(streams)]
            for watcher in watchers:
                watcher.start()

            def exercise(index, stream):
                count = 0
                while not stop.is_set() and time.monotonic()-began < seconds:
                    started = time.monotonic()
                    original_id = uuid.uuid4().hex
                    try:
                        obs = stream.observe()
                        x, y, z = obs['position']
                        attempts[index] = {'id': original_id, 'epoch': obs['body_epoch'], 'ttl': 30,
                                           'deadline': started + 30, 'acknowledged': False}
                        receipt = stream.look_at(x + (-2 if count % 2 else 2), y+1, z+2,
                                                 request_id=original_id, expected_body_epoch=obs['body_epoch'], ttl_seconds=30)
                        attempts[index]['acknowledged'] = True
                        # Pin reconciliation to the gateway's original acceptance expiry,
                        # not to a later retry/read or the end of the steady-state window.
                        attempts[index]['deadline'] = time.monotonic() + max(0, min(30, receipt['expires_at'] - time.time()))
                        ack = (time.monotonic()-started)*1000
                        completed = done(stream, receipt, timeout=8)
                        attempts[index]['completed'] = True
                        rows.append({'body': index, 'index': count, 'elapsed_seconds': started-began,
                                     'action_id': original_id, 'body_epoch': obs['body_epoch'], 'result_tick': completed.get('tick'),
                                     'ack_ms': ack, 'completion_ms': (time.monotonic()-started)*1000})
                        count += 1
                    except Exception as error:
                        failures.append({'body': index, 'error': type(error).__name__ + ': ' + str(error),
                                         'action_id': original_id,
                                         'diagnostics': stream.diagnostics()})
                        stop.set()
                        break
                    time.sleep(max(0, .2-(time.monotonic()-started)))

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                list(executor.map(lambda args: exercise(*args), enumerate(streams)))
            measured_end = time.monotonic()
            cpu_after = cpu_sample()
            stop.set()
            for watcher in watchers:
                watcher.join(timeout=2)
            final = [(last_observations.get(i, ({'tick': initial[i][0]}, time.monotonic()))[0]['tick'],
                      last_observations.get(i, ({}, time.monotonic()))[1]) for i in range(len(streams))]
            tps = [(end[0]-start[0])/(end[1]-start[1]) for start, end in zip(initial, final)]
            counts = [sum(r['body'] == i for r in rows) for i in range(10)]
            if failures:
                failure_reconciliation = reconcile_failed_actions(fixture, streams, failures, attempts)
            try:
                slow_evidence = slow_observer.resume(streams[0])
            except Exception as error:
                slow_evidence = slow_observer.evidence
                failures.append({'phase': 'slow_observer_recovery', 'error': type(error).__name__})
            finally:
                try:
                    slow_observer.close()
                except Exception as error:
                    failures.append({'phase': 'slow_observer_cleanup', 'error': type(error).__name__})
            with fixture.gateway.changed:
                lease = fixture.gateway.leases.get(streams[0].client.agent)
                lease_preserved = bool(lease and lease['id'] == controlling_lease)
            slow_evidence['controlling_lease_preserved'] = lease_preserved
            if not lease_preserved:
                failures.append({'phase': 'slow_observer_cleanup', 'error': 'Controlling lease changed'})
            if not failures:
                try:
                    position = streams[0].observe()['position']
                    resumed = done(streams[0], streams[0].look_at(position[0]+2, position[1]+1, position[2]+2))
                    slow_evidence['control_after_observer_close'] = resumed['state']
                except Exception as error:
                    failures.append({'phase': 'control_after_slow_observer', 'error': type(error).__name__})
            report = {'seconds': measured_end-began, 'bodies': 10, 'actions_per_second_per_body': 5,
                      'fixture_resource_limits': {'cpu_percent': 150, 'jvm_heap_mib': 1536, 'service_memory_mib': 2400, 'tasks': 512},
                      'measurement': 'loopback SDK send through gateway to actual Java terminal result',
                      'samples': rows, 'observation_gaps': observations, 'failures': failures,
                      'slow_observer': slow_evidence,
                      'per_body_counts': counts, 'per_body_tps': tps,
                      'startup': startup, 'setup_seconds': setup_seconds,
                      'cpu_usage': cpu_delta(cpu_before, cpu_after, measured_end-began),
                      'failure_reconciliation': failure_reconciliation,
                      'per_body_latency': [{'body': i,
                          'ack_ms': percentiles([r['ack_ms'] for r in rows if r['body'] == i]),
                          'completion_ms': percentiles([r['completion_ms'] for r in rows if r['body'] == i])}
                          for i in range(10)],
                      'ack_ms': percentiles([r['ack_ms'] for r in rows]),
                      'completion_ms': percentiles([r['completion_ms'] for r in rows]),
                      'observation_gap_ms': percentiles([r['gap_ms'] for r in observations])}
            tick_costs = [r['average_tick_ms'] for r in observations if r['average_tick_ms'] is not None]
            report['rolling_average_tick_ms'] = percentiles(tick_costs) if tick_costs else None
            for field in ('body_receive_lag_ms', 'sdk_observed_capture_age_ms', 'sdk_after_gateway_receive_age_ms'):
                values = [r[field] for r in observations if isinstance(r.get(field), (int, float)) and r[field] >= 0]
                report[field] = percentiles(values) if values else None
            report['capture_age_measurement'] = 'SDK watcher wall time minus native capture time; includes up to watcher polling delay, not socket receive-only time'
            report['clock_skew_samples'] = sum(bool(r.get('body_receive_clock_skew_ms') or r.get('sdk_capture_clock_skew_ms') or r.get('sdk_gateway_clock_skew_ms')) for r in observations)
            (fixture.root/'performance.json').write_text(json.dumps(report, indent=2)+'\n')
            assert not failures, failures
            assert min(counts) >= seconds * 4, counts
            assert min(tps) >= 19, tps
            assert report['ack_ms']['p95'] < 25, report['ack_ms']
            assert report['completion_ms']['p95'] < 150 and report['completion_ms']['p99'] < 250, report['completion_ms']
            assert report['observation_gap_ms']['p99'] < 250, report['observation_gap_ms']
            return {key: value for key, value in report.items() if key not in {'samples', 'observation_gaps'}}
        finally:
            stop.set()
            if slow_observer is not None:
                try:
                    slow_observer.close()
                except Exception as error:
                    failures.append({'phase': 'slow_observer_cleanup', 'error': type(error).__name__})
            for stream in streams:
                try:
                    stream.close()
                except Exception as error:
                    failures.append({'phase': 'cleanup', 'error': type(error).__name__})
            final_report = report or {'samples': rows, 'observation_gaps': observations,
                'startup': startup,
                'failure_reconciliation': failure_reconciliation,
                'cpu_before': cpu_before, 'cpu_after': cpu_after,
                'failures': failures, 'slow_observer': slow_evidence or (slow_observer.evidence if slow_observer else None),
                'incomplete': True}
            (fixture.root/'performance.json').write_text(json.dumps(final_report, indent=2)+'\n')

    fixture.case('ten_body_five_minute_instant_action_load', ['VERIFY-05'], measure)
