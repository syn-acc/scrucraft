"""Ten-body actual Java response measurements; thresholds live in docs/verification.md."""
import concurrent.futures
import json
import math
import socket
import threading
import time

from gameplay_cases import done


def percentiles(values):
    values = sorted(values)
    if not values:
        return {}
    return {key: round(values[min(len(values)-1, math.ceil(p * len(values))-1)], 3)
            for key, p in [('p50', .5), ('p95', .95), ('p99', .99), ('max', 1)]}



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
        try:
            fixture.console('effect give VerifyBuilder saturation 1 255 true')
            # Reuse the existing body; total is ten, matching the configured cap.
            with fixture.gateway.changed:
                from scru_minecraft import AgentClient
                owner = fixture.gateway.member('FixtureOwner')
                token = fixture.gateway.issue(owner['name'], 'agent', 'VerifyBuilder', player_uuid=owner['uuid'])
            client = AgentClient(f'http://127.0.0.1:{fixture.args.ws_port}', token, 'VerifyBuilder', allow_local_http=True, timeout=8)
            streams.append(client.realtime().connect())
            for index in range(1, 10):
                time.sleep(5.05)  # Respect owner provisioning limits; this is setup, not measured gameplay.
                streams.append(fixture.client('VerifyLoad' + str(index)).realtime().connect())
            # This peer authenticates only: it must never interfere with the body's
            # controlling lease, even when it stalls or disconnects under backpressure.
            controlling_lease = streams[0].lease
            slow_observer = SlowObserver(streams[0], fixture.args.ws_port)
            initial = [(s.observe()['tick'], time.monotonic()) for s in streams]
            began = time.monotonic()

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
                        observations.append({'body': index, 'gap_ms': (now-previous[1])*1000,
                            'average_tick_ms': obs.get('average_tick_ms'),
                            'observation_ms': obs.get('observation_ms')})
                    if previous is None or sample != previous[0]:
                        previous = (sample, now)

            watchers = [threading.Thread(target=watch, args=(i, s), daemon=True) for i, s in enumerate(streams)]
            for watcher in watchers:
                watcher.start()

            def exercise(index, stream):
                count = 0
                while not stop.is_set() and time.monotonic()-began < seconds:
                    started = time.monotonic()
                    try:
                        obs = stream.observe()
                        x, y, z = obs['position']
                        receipt = stream.look_at(x + (-2 if count % 2 else 2), y+1, z+2)
                        ack = (time.monotonic()-started)*1000
                        done(stream, receipt, timeout=8)
                        rows.append({'body': index, 'index': count, 'elapsed_seconds': started-began,
                                     'ack_ms': ack, 'completion_ms': (time.monotonic()-started)*1000})
                        count += 1
                    except Exception as error:
                        failures.append({'body': index, 'error': type(error).__name__ + ': ' + str(error),
                                         'diagnostics': stream.diagnostics()})
                        stop.set()
                        break
                    time.sleep(max(0, .2-(time.monotonic()-started)))

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                list(executor.map(lambda args: exercise(*args), enumerate(streams)))
            measured_end = time.monotonic()
            stop.set()
            for watcher in watchers:
                watcher.join(timeout=2)
            final = [(last_observations.get(i, ({'tick': initial[i][0]}, time.monotonic()))[0]['tick'],
                      last_observations.get(i, ({}, time.monotonic()))[1]) for i in range(len(streams))]
            tps = [(end[0]-start[0])/(end[1]-start[1]) for start, end in zip(initial, final)]
            counts = [sum(r['body'] == i for r in rows) for i in range(10)]
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
                      'ack_ms': percentiles([r['ack_ms'] for r in rows]),
                      'completion_ms': percentiles([r['completion_ms'] for r in rows]),
                      'observation_gap_ms': percentiles([r['gap_ms'] for r in observations])}
            tick_costs = [r['average_tick_ms'] for r in observations if r['average_tick_ms'] is not None]
            report['rolling_average_tick_ms'] = percentiles(tick_costs) if tick_costs else None
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
                'failures': failures, 'slow_observer': slow_evidence or (slow_observer.evidence if slow_observer else None),
                'incomplete': True}
            (fixture.root/'performance.json').write_text(json.dumps(final_report, indent=2)+'\n')

    fixture.case('ten_body_five_minute_instant_action_load', ['VERIFY-05'], measure)
