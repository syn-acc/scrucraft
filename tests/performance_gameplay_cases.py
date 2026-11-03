"""Native ten-body load with SDK consumers in a separate, same-cgroup process."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

from performance_driver import cpu_sample, cpu_delta


def verify_targets(report, seconds):
    """Original VERIFY-05 targets, unchanged by consumer process topology."""
    assert not report.get('incomplete'), 'Performance driver did not complete'
    assert not report['failures'], report['failures']
    assert min(report['per_body_counts']) >= seconds * 4, report['per_body_counts']
    assert min(report['per_body_tps']) >= 19, report['per_body_tps']
    assert report['ack_ms']['p95'] < 25, report['ack_ms']
    assert report['completion_ms']['p95'] < 150 and report['completion_ms']['p99'] < 250, report['completion_ms']
    assert report['observation_gap_ms']['p99'] < 250, report['observation_gap_ms']


def launch_driver(config):
    """Private stdin and bounded result protocol; no credential file or argv values."""
    process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('performance_driver.py'))],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',bufsize=1)
    events=queue.Queue()
    def read():
        try:
            for line in process.stdout:
                try:events.put(json.loads(line))
                except (ValueError,TypeError):events.put({'type':'invalid_output'})
        finally:events.put({'type':'eof'})
    reader=threading.Thread(target=read,daemon=True,name='performance-driver-results');reader.start()
    report=None;cpu_before=cpu_after=None;driver=None;fatal=None
    before_at=after_at=None;deadline=time.monotonic()+config['seconds']+180
    try:
        process.stdin.write(json.dumps(config));process.stdin.close()
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Performance driver exceeded its bounded setup/measurement/reconciliation window')
            try:event=events.get(timeout=remaining)
            except queue.Empty:raise TimeoutError('Performance driver stopped reporting') from None
            kind=event.get('type');value=event.get('value')
            if kind=='ready':driver=value
            elif kind=='measurement_started':cpu_before=cpu_sample();before_at=time.monotonic()
            elif kind=='measurement_ended':cpu_after=cpu_sample();after_at=time.monotonic()
            elif kind=='report':report=value
            elif kind=='fatal':fatal=value
            elif kind=='eof':break
            else:raise RuntimeError('Invalid performance driver event')
        exit_code=process.wait(timeout=5)
        if report is None:report={'incomplete':True,'failures':[]}
        report['topology']={
            'name':'separate_sdk_driver_same_cgroup',
            'parent':'Gateway and native bridge; no measured SDK/watcher threads',
            'child':'Ten SDK control streams, ten watcher threads and one slow observer in a separate Python interpreter',
            'resource_scope':'Parent, SDK driver, JVM and nginx inherit the same150% CPU cgroup; targets unchanged',
            'credentials_transport':'stdin pipe only; absent from argv and public artifacts',
            'driver':driver,'driver_exit_code':exit_code,
            'comparison':'Earlier shared-interpreter performance reports remain separate failed evidence, not superseded passes'}
        if fatal or exit_code:
            report.setdefault('failures',[]).append({'phase':'driver','exit_code':exit_code,'error':fatal})
        if cpu_before is not None and cpu_after is not None:
            report['parent_cpu_usage']=cpu_delta(cpu_before,cpu_after,after_at-before_at)
            report['parent_cpu_usage']['process_scope']='Parent fixture Python: gateway and native bridge; SDK consumers are a child process'
            report['parent_cpu_usage']['window_seconds']=after_at-before_at
            report['parent_cpu_usage']['window_alignment']='Received child measured-start/end markers; bounded pipe/scheduling delay is included'
        return report
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        if process.stdout:process.stdout.close()
        if process.stdin and not process.stdin.closed:process.stdin.close()
        reader.join(timeout=2)


def run_cases(fixture,seconds=300):
    if seconds<300:raise ValueError('The recorded VERIFY-05 steady-state acceptance window is at least five minutes')
    def measure():
        fixture.console('effect give VerifyBuilder saturation 1 255 true')
        clients=[];startup=[];setup_started=time.monotonic();report=None
        try:
            with fixture.gateway.changed:
                owner=fixture.gateway.member('FixtureOwner')
                token=fixture.gateway.issue(owner['name'],'agent','VerifyBuilder',player_uuid=owner['uuid'])
            clients.append({'agent':'VerifyBuilder','token':token})
            startup.append({'body':0,'existing_body':True})
            for index in range(1,10):
                time.sleep(5.05)  # Same owner provisioning limit; excluded from measured window.
                began=time.monotonic();client=fixture.client('VerifyLoad'+str(index))
                clients.append({'agent':client.agent,'token':client.token})
                startup.append({'body':index,'existing_body':False,'prepare_seconds':time.monotonic()-began})
            config={'seconds':seconds,'public_url':fixture.public_url,'public_port':fixture.public_port,
                    'clients':clients,'startup':startup,'cgroup':cpu_sample()}
            provisioning_seconds=time.monotonic()-setup_started
            report=launch_driver(config)
            report['parent_provisioning_seconds']=provisioning_seconds
            # Native state is read only after driver measurements and reconciliation.
            for row in (report.get('failure_reconciliation') or {}).get('actions',[]):
                with fixture.gateway.changed:
                    native=fixture.gateway.frames.get(clients[row['body']]['agent'],{})
                    fields=('body_epoch','tick','world_tick','captured_at_ms','gateway_received_at_ms',
                            'body_receive_lag_ms','position','health','food','execution','movement')
                    row['latest_gateway_native_observation']={key:native.get(key) for key in fields}
                    row['native_observation_capture_scope']='Parent read after child measurement/reconciliation/cleanup'
            (fixture.root/'performance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
            verify_targets(report,seconds)
            return {key:value for key,value in report.items() if key not in {'samples','observation_gaps'}}
        finally:
            if report is None:
                (fixture.root/'performance.json').write_text(json.dumps({'incomplete':True,
                    'topology':'separate_sdk_driver_same_cgroup','startup':startup})+'\n',encoding='utf-8')
    fixture.case('ten_body_five_minute_instant_action_load',['VERIFY-05'],measure)
