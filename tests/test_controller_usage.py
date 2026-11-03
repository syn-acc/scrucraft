import importlib.util,io,json,pathlib,tempfile,threading,time,unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('usage_controller',pathlib.Path(__file__).parents[1]/'agent-service/service.py')
controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)

class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.rootpatch=patch.object(controller,'ROOT',pathlib.Path(self.temp.name));self.rootpatch.start()
        self.c=controller.Controller();self.c.key='audit-secret';self.c.provider='openai'
    def tearDown(self):
        self.c.pool.shutdown(wait=True);self.c.db.close();self.rootpatch.stop();self.temp.cleanup()
    def response(self,usage=None,content=None):
        result={'id':'chatcmpl-audit','model':'gpt-4o-mini-actual',
                'choices':[{'message':{'content':content if content is not None else json.dumps({'goal':'rest','say':'','reason':''})}}]}
        if usage is not None:result['usage']=usage
        stream=io.StringIO(json.dumps(result));stream.headers={'x-request-id':'req-audit'}
        return stream
    def infer(self,response,revision=0):
        with patch.object(controller.urllib.request,'urlopen',return_value=response):
            self.c.infer(('Syn_Test','decision'),{'chat_revision':revision})
    def last(self):
        self.c.db.row_factory=controller.sqlite3.Row
        return dict(self.c.db.execute('SELECT r.status,r.reserved,r.cost,u.* FROM runs r JOIN run_usage u ON r.id=u.run_id ORDER BY r.at DESC LIMIT 1').fetchone())
    def test_lazy_migration_preserves_retained_object_and_old_rows_without_fabricating_tokens(self):
        self.c.db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',('legacy',time.time(),'Syn_Test','decision','PUBLISHED',.01,.004,'{}','{}'));self.c.db.commit()
        del self.c.usage_schema_ready;del self.c.usage_inflight
        identity=id(self.c);ledger=self.c.db;executor=self.c.pool
        with patch.object(controller.Controller,'__init__',side_effect=AssertionError('Hot reload must not reconstruct controller')):
            usage=self.c.health()['usage']
        self.assertEqual(id(self.c),identity);self.assertIs(self.c.db,ledger);self.assertIs(self.c.pool,executor)
        self.assertEqual(usage['today']['legacy_rows'],1);self.assertEqual(usage['today']['token_usage_rows'],0)
        self.assertAlmostEqual(usage['today']['legacy_accounted_usd'],.004)
        self.assertFalse(usage['today']['token_coverage_complete'])
        self.assertEqual(self.c.db.execute('SELECT count(*) FROM run_usage').fetchone()[0],0)
    def test_success_records_tokens_ids_rates_timing_and_uncached_cost_basis(self):
        self.infer(self.response({'prompt_tokens':1000,'completion_tokens':50,'prompt_tokens_details':{'cached_tokens':500}}))
        row=self.last()
        self.assertEqual((row['prompt_tokens'],row['completion_tokens'],row['cached_prompt_tokens']),(1000,50,500))
        self.assertEqual((row['provider_request_id'],row['provider_response_id']),('req-audit','chatcmpl-audit'))
        self.assertEqual(row['provider'],'openai');self.assertEqual(row['requested_model'],'gpt-4o-mini')
        self.assertEqual(row['response_model'],'gpt-4o-mini-actual');self.assertEqual(row['input_rate_per_million'],.15)
        self.assertEqual(row['cost_source'],'token_estimate_uncached');self.assertAlmostEqual(row['cost'],.00018)
        self.assertEqual(row['policy_published'],1);self.assertEqual(row['outcome'],'published')
        self.assertIsNotNone(row['completed_at']);self.assertGreaterEqual(row['elapsed_ms'],0)
        summary=self.c.health()['usage']['today'];self.assertTrue(summary['token_coverage_complete'])
        self.assertEqual(summary['prompt_tokens'],1000);self.assertAlmostEqual(summary['token_estimate_uncached_usd'],.00018)
    def test_invalid_game_output_still_records_and_settles_reported_usage(self):
        self.infer(self.response({'prompt_tokens':1000,'completion_tokens':50},content='not valid JSON'))
        row=self.last();self.assertEqual(row['status'],'FAILED');self.assertEqual(row['outcome'],'failed')
        self.assertEqual(row['prompt_tokens'],1000);self.assertAlmostEqual(row['cost'],.00018)
        self.assertEqual(row['cost_source'],'token_estimate_uncached');self.assertEqual(row['policy_published'],0)
        self.assertNotIn(('Syn_Test','decision'),self.c.policies)
    def test_missing_usage_preserves_reservation_and_explicit_unknown_coverage(self):
        self.infer(self.response())
        row=self.last();self.assertEqual(row['cost'],row['reserved']);self.assertEqual(row['cost_source'],'reservation_unknown')
        self.assertIsNone(row['prompt_tokens']);self.assertIsNone(row['completion_tokens'])
        summary=self.c.health()['usage']['today'];self.assertEqual(summary['token_usage_rows'],0)
        self.assertAlmostEqual(summary['reservation_unknown_usd'],row['reserved'])
        self.assertFalse(summary['token_coverage_complete'])
    def test_openrouter_rejects_nonfinite_boolean_and_negative_costs(self):
        self.c.provider='openrouter'
        for cost in (float('nan'),float('inf'),float('-inf'),False,True,-.1):
            with self.subTest(cost=cost):
                self.infer(self.response({'cost':cost,'prompt_tokens':40,'completion_tokens':4}))
                row=self.last();self.assertEqual(row['cost_source'],'reservation_unknown')
                self.assertEqual(row['cost'],row['reserved']);json.dumps(self.c.health(),allow_nan=False)
        self.infer(self.response({'cost':.0004,'prompt_tokens':40,'completion_tokens':4}))
        row=self.last();self.assertEqual(row['cost_source'],'provider_reported');self.assertEqual(row['cost'],.0004)
    def test_stale_result_is_logged_without_claiming_policy_publication(self):
        self.c.revision=1
        self.infer(self.response({'prompt_tokens':80,'completion_tokens':8}),revision=0)
        row=self.last();self.assertEqual(row['status'],'PUBLISHED')
        self.assertEqual(row['outcome'],'stale');self.assertEqual(row['policy_published'],0)
        self.assertNotIn(('Syn_Test','decision'),self.c.policies)
        summary=self.c.health()['usage']['today'];self.assertEqual(summary['stale_outputs'],1);self.assertEqual(summary['policy_published'],0)
    def test_live_reservation_is_distinct_from_abandoned_reserved_row(self):
        self.c.db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',('abandoned',time.time()-100,'Syn_Test','decision','RESERVED',.003,None,'{}',None));self.c.db.commit()
        key=('Syn_Test','decision');self.c.pending.add(key)
        def network(*args,**kwargs):
            usage=self.c.health()['usage']
            self.assertEqual(usage['pending_requests'],1);self.assertEqual(usage['tracked_inflight_reservations'],1)
            self.assertEqual(usage['reserved_rows'],2);self.assertEqual(usage['unresolved_reserved_rows'],1)
            raise TimeoutError('unknown dispatch outcome')
        with patch.object(controller.urllib.request,'urlopen',side_effect=network):self.c.infer(key,{'chat_revision':0})
        row=self.last();self.assertEqual(row['status'],'FAILED');self.assertIsNone(row['cost'])
        self.assertEqual(row['cost_source'],'reservation_unknown')
        usage=self.c.health()['usage'];self.assertEqual(usage['pending_requests'],0);self.assertEqual(usage['unresolved_reserved_rows'],1)
    def test_budget_skip_has_metadata_but_no_dispatch_or_tokens(self):
        self.c.db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',('used',time.time(),'Syn_Test','decision','PUBLISHED',2,2,'{}','{}'));self.c.db.commit()
        with patch.object(controller.urllib.request,'urlopen') as network:self.c.infer(('Syn_Test','decision'),{'chat_revision':0})
        network.assert_not_called();row=self.last();self.assertEqual(row['outcome'],'budget_skip');self.assertEqual(row['reserved'],0)
        summary=self.c.health()['usage']['today'];self.assertEqual(summary['budget_skips'],1);self.assertEqual(summary['dispatched_runs'],1)
    def test_concurrent_request_sees_first_requests_committed_reservation(self):
        self.c.db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',('used',time.time(),'Syn_Test','decision','PUBLISHED',.249,.249,'{}','{}'));self.c.db.commit()
        entered=threading.Event();release=threading.Event()
        def network(*args,**kwargs):
            entered.set();release.wait(3)
            return self.response({'prompt_tokens':100,'completion_tokens':10})
        with patch.object(controller.urllib.request,'urlopen',side_effect=network) as request:
            future=self.c.pool.submit(self.c.infer,('Syn_First','decision'),{'chat_revision':0})
            try:
                self.assertTrue(entered.wait(2))
                self.c.infer(('Syn_Second','decision'),{'chat_revision':0})
                self.assertEqual(request.call_count,1)
                self.assertEqual(self.c.db.execute("SELECT count(*) FROM runs WHERE status='BUDGET_SKIP'").fetchone()[0],1)
            finally:release.set();future.result(timeout=3)
    def test_metadata_is_sanitized_and_retention_removes_usage_with_its_run(self):
        response=self.response({'prompt_tokens':10,'completion_tokens':2})
        response.headers={'x-request-id':'audit-secret\n sk-sensitive-key'}
        self.infer(response);row=self.last()
        self.assertNotIn('audit-secret',row['provider_request_id']);self.assertNotIn('sk-sensitive-key',row['provider_request_id'])
        old_id=row['run_id'];self.c.db.execute('UPDATE runs SET at=? WHERE id=?',(time.time()-33*86400,old_id));self.c.db.commit()
        self.infer(self.response())
        self.assertIsNone(self.c.db.execute('SELECT id FROM runs WHERE id=?',(old_id,)).fetchone())
        self.assertIsNone(self.c.db.execute('SELECT run_id FROM run_usage WHERE run_id=?',(old_id,)).fetchone())

if __name__=='__main__':unittest.main()
