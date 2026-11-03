"""VERIFY-05 diagnostic profiling of the isolated native path, not acceptance.

Instrumented timings alter scheduling. Use the uninstrumented full-pack fixture
for release evidence. This script never connects to a production gateway.
"""
import argparse
import cProfile
import collections
import functools
import json
import pstats
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'agent-gateway'), str(ROOT/'sdk')]
import gateway
from isolated_game_fixture import Fixture
from performance_gameplay_cases import run_cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('directory', 'libraries', 'adapter', 'luckperms', 'full-pack-mods'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--pack-lock', type=Path, default=ROOT/'pack.lock.json')
    parser.add_argument('--game-port', type=int, default=18565)
    parser.add_argument('--ws-port', type=int, default=18769)
    parser.add_argument('--python-profile', action='store_true', help='Diagnostic per-thread cProfile; materially changes timings')
    args = parser.parse_args()
    metrics = collections.defaultdict(lambda: {'calls': 0, 'cpu_seconds': 0., 'wall_seconds': 0., 'max_wall_ms': 0.})
    guard = threading.Lock()
    sizes = []
    releases = []
    originals = {}
    profiles = []
    local = threading.local()
    if args.python_profile:
        def start_profile(frame, event, arg):
            if not getattr(local, 'started', False):
                local.started = True
                profile = cProfile.Profile()
                with guard: profiles.append(profile)
                profile.enable()
        threading.setprofile(start_profile)

    def instrument(name, function):
        @functools.wraps(function)
        def call(self, *a, **kw):
            cpu, wall = time.thread_time(), time.monotonic()
            try:
                return function(self, *a, **kw)
            finally:
                elapsed, cost = time.monotonic()-wall, time.thread_time()-cpu
                with guard:
                    row = metrics[name]
                    row['calls'] += 1
                    row['cpu_seconds'] += cost
                    row['wall_seconds'] += elapsed
                    row['max_wall_ms'] = max(row['max_wall_ms'], elapsed*1000)
                    if name == 'release' and len(releases) < 100:
                        releases.append({'body': a[0], 'reason': a[1], 'at': time.monotonic()})
                    if name == 'frame' and row['calls'] % 100 == 1 and len(sizes) < 100:
                        frame = a[0]
                        sizes.append({'body': frame.get('agent'), 'tick': frame.get('tick'),
                                      'bytes': len(json.dumps(frame)),
                                      'result_count': len(frame.get('action_results', [])),
                                      'largest_fields': sorted([(k, len(json.dumps(v))) for k, v in frame.items()],
                                                               key=lambda item: item[1], reverse=True)[:5]})
        return call

    for name in ('frame', 'realtime_control', 'handle', 'authenticate', 'member', 'body',
                 'update_results', 'result_rows', 'stream_results', 'release'):
        originals[name] = getattr(gateway.Gateway, name)
        setattr(gateway.Gateway, name, instrument(name, originals[name]))
    fixture = Fixture(args)
    try:
        fixture.start()
        # Required first body is provisioned through the real SDK helper.
        with fixture.client('VerifyBuilder').realtime() as stream:
            stream.stop()
        run_cases(fixture, seconds=300)
    finally:
        fixture.close()
        for name, function in originals.items():
            setattr(gateway.Gateway, name, function)
        report = {'diagnostic_only': True, 'checklist_ids': ['VERIFY-05'],
                  'timings_include_nested_calls': True, 'metrics': dict(metrics),
                  'sampled_native_frame_sizes': sizes, 'release_reasons': releases}
        (fixture.root/'transport-profile.json').write_text(json.dumps(report, indent=2)+'\n')
        if profiles:
            threading.setprofile(None)
            combined = pstats.Stats(profiles[0])
            for profile in profiles[1:]:
                combined.add(profile)
            combined.dump_stats(str(fixture.root/'python-threads.prof'))


if __name__ == '__main__':
    main()
