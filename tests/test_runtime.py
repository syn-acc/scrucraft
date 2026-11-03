import concurrent.futures,importlib.util,pathlib,threading,types,unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('syn_runtime',pathlib.Path(__file__).parents[1]/'agent-service/runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)

class OldController:
    def __init__(self):
        self.lock=threading.RLock();self.tasks={'Syn_Forge':'build'};self.policies={'strategic':'parent-id'}
        self.db=object();self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);self.token='kept-secret';self.completed=[]
    def health(self):return {'version':'old'}
    def infer(self,gate):gate.wait(timeout=5);self.completed.append('old_inference_completed')
class NewController:
    def health(self):return {'version':'new'}

class HotReloadTests(unittest.TestCase):
    def test_reload_preserves_live_tasks_ledger_workers_and_inflight_inference(self):
        old=types.SimpleNamespace(Controller=OldController);new=types.SimpleNamespace(Controller=NewController)
        with patch.object(runtime,'load_candidate',side_effect=[('old',old),('new',new)]):
            host=runtime.Runtime();c=host.controller;db=c.db;pool=c.pool;gate=threading.Event()
            future=pool.submit(c.infer,gate)
            try:
                self.assertTrue(host.reload());self.assertIs(host.controller,c)
                self.assertIs(c.db,db);self.assertIs(c.pool,pool)
                self.assertEqual(c.tasks,{'Syn_Forge':'build'});self.assertEqual(c.policies,{'strategic':'parent-id'})
                self.assertEqual(c.token,'kept-secret');self.assertEqual(host.health()['version'],'new')
                gate.set();future.result(timeout=5);self.assertEqual(c.completed,['old_inference_completed'])
            finally:gate.set();pool.shutdown(wait=True)
    def test_failed_candidate_keeps_working_release(self):
        old=types.SimpleNamespace(Controller=OldController)
        with patch.object(runtime,'load_candidate',side_effect=[('old',old),ValueError('candidate_contract')]):
            host=runtime.Runtime()
            try:
                self.assertFalse(host.reload());self.assertEqual(host.digest,'old');self.assertEqual(host.health()['version'],'old')
                self.assertIn('candidate_contract',host.error)
            finally:host.controller.pool.shutdown(wait=True)

if __name__=='__main__':unittest.main()
