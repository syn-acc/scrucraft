"""Measurement topology must not weaken acceptance or expose fixture credentials."""
import copy
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import performance_gameplay_cases as performance


class PerformanceDriverTests(unittest.TestCase):
    def test_original_targets_remain_independently_enforced(self):
        baseline={'failures':[],'per_body_counts':[1200]*10,'per_body_tps':[19]*10,
                  'ack_ms':{'p95':24.99},'completion_ms':{'p95':149.99,'p99':249.99},
                  'observation_gap_ms':{'p99':249.99}}
        performance.verify_targets(baseline,300)
        edits=[('failures',[{'error':'fixture'}]),('per_body_counts',[1199]+[1200]*9),
               ('per_body_tps',[18.99]+[19]*9),('ack_ms',{'p95':25}),
               ('completion_ms',{'p95':150,'p99':249}),('completion_ms',{'p95':149,'p99':250}),
               ('observation_gap_ms',{'p99':250}),('incomplete',True)]
        for key,value in edits:
            report=copy.deepcopy(baseline);report[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(AssertionError):
                performance.verify_targets(report,300)

    def test_actual_child_rejects_foreign_cgroup_without_printing_stdin_credentials(self):
        secret='synthetic-private-driver-credential'
        config={'clients':[{'agent':'Fixture','token':secret}],
                'cgroup':{'cgroup_path':'/definitely-not-this-fixture-cgroup','cgroup_cpu_max':'150000 100000'}}
        result=subprocess.run([sys.executable,str(Path(performance.__file__).with_name('performance_driver.py'))],
            input=json.dumps(config),text=True,capture_output=True,timeout=10)
        self.assertEqual(1,result.returncode)
        self.assertNotIn(secret,result.stdout+result.stderr)
        self.assertEqual('RuntimeError',json.loads(result.stdout)['value']['exception_type'])
        self.assertEqual('',result.stderr)

    def test_parent_uses_private_stdin_and_records_distinct_cpu_scopes(self):
        secret='synthetic-private-driver-credential';captured=[]
        events=[{'type':'ready','value':{'pid':123,'cgroup_path':'/fixture','cgroup_cpu_max':'150000 100000'}},
                {'type':'measurement_started','value':{}},{'type':'measurement_ended','value':{}},
                {'type':'report','value':{'failures':[],'cpu_usage':{'process_scope':'SDK driver'}}}]
        class Input(io.StringIO):
            def close(self):captured.append(self.getvalue());super().close()
        class Process:
            def __init__(self,*args,**kwargs):
                self.stdin=Input();self.stdout=io.StringIO(''.join(json.dumps(event)+'\n' for event in events))
                self.args=args;self.kwargs=kwargs
            def wait(self,timeout=None):return 0
            def poll(self):return 0
        config={'seconds':300,'clients':[{'agent':'Fixture','token':secret}]}
        with patch.object(performance.subprocess,'Popen',side_effect=Process) as popen:
            report=performance.launch_driver(config)
        self.assertNotIn(secret,str(popen.call_args))
        self.assertEqual(config,json.loads(captured[0]));self.assertNotIn(secret,json.dumps(report))
        self.assertIn('SDK consumers are a child process',report['parent_cpu_usage']['process_scope'])
        self.assertEqual('SDK driver',report['cpu_usage']['process_scope'])
        self.assertEqual(0,report['topology']['driver_exit_code'])
