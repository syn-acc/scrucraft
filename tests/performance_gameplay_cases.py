"""Ten-body actual Java response measurements; thresholds live in docs/verification.md."""
import concurrent.futures
import json
import math
import threading
import time

from gameplay_cases import done


def percentiles(values):
    values = sorted(values)
    if not values:
        return {}
    return {key: round(values[min(len(values)-1, math.ceil(p * len(values))-1)], 3)
            for key, p in [('p50', .5), ('p95', .95), ('p99', .99), ('max', 1)]}


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
            stop.set()
            for watcher in watchers:
                watcher.join(timeout=2)
            final = [(last_observations.get(i, ({'tick': initial[i][0]}, time.monotonic()))[0]['tick'],
                      last_observations.get(i, ({}, time.monotonic()))[1]) for i in range(len(streams))]
            tps = [(end[0]-start[0])/(end[1]-start[1]) for start, end in zip(initial, final)]
            counts = [sum(r['body'] == i for r in rows) for i in range(10)]
            report = {'seconds': time.monotonic()-began, 'bodies': 10, 'actions_per_second_per_body': 5,
                      'fixture_resource_limits': {'cpu_percent': 150, 'jvm_heap_mib': 1536, 'service_memory_mib': 2400, 'tasks': 512},
                      'measurement': 'loopback SDK send through gateway to actual Java terminal result',
                      'samples': rows, 'observation_gaps': observations, 'failures': failures,
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
            if report is None:
                (fixture.root/'performance.json').write_text(json.dumps({'samples': rows,
                    'observation_gaps': observations, 'failures': failures, 'incomplete': True}, indent=2)+'\n')
            for stream in streams:
                try:
                    stream.close()
                except Exception as error:
                    failures.append({'phase': 'cleanup', 'error': type(error).__name__})

    fixture.case('ten_body_five_minute_instant_action_load', ['VERIFY-05'], measure)
