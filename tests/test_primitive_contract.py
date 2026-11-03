"""Protocol 2 queue and authorization regression tests; no Minecraft simulation claims."""
import unittest
import test_controller_gateway as fixtures


class PrimitiveContractTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.GatewayTests();self.f.setUp();self.g=self.f.g
        self.sample=fixtures.frame(tick=101)
        self.sample.update(body_epoch='epoch2',control_protocol=2,control_transport='websocket',
                           raw_capabilities=sorted(fixtures.gateway.PRIMITIVES),action_results=[])
        self.g.frame(self.sample);self.f.lease()
    def tearDown(self):self.f.tearDown()
    def submit(self,op='look_at',rid=None,**fields):
        value=dict(id=rid or ('a'*16+str(len(self.g.actions.get('Forge',{})))),op=op,body_epoch='epoch2',**fields)
        return self.f.call('POST','/v1/actions',value)
    def grant(self):
        with self.g.changed:return self.g.realtime_control('Forge')
    def results(self):return {r['id']:r for r in self.f.call('GET','/v1/action-results')['results']}
    def test_rapid_commands_not_lost_and_acknowledged_commands_not_replayed(self):
        a=self.submit('move_to',target=[3,64,0]);b=self.submit('look_at',target=[0,65,0])
        self.assertEqual([a['id'],b['id']],[r['id'] for r in self.grant()['commands']])
        self.sample.update(tick=102,action_results=[dict(id=a['id'],state='started',body_epoch='epoch2')])
        self.g.frame(self.sample)
        self.assertEqual([b['id']],[r['id'] for r in self.grant()['commands']])
        self.assertEqual('started',self.results()[a['id']]['state'])
        self.sample.update(tick=103,action_results=[dict(id=b['id'],state='done',body_epoch='epoch2')])
        self.g.frame(self.sample)
        self.assertEqual('started',self.results()[a['id']]['state'])
        self.assertEqual('done',self.results()[b['id']]['state'])
    def test_stop_cancels_before_delivery_and_changes_grant_without_losing_lease(self):
        a=self.submit('dig',target=[1,64,0]);before=self.grant()['lease_id']
        self.f.call('DELETE','/v1/goal')
        self.assertNotEqual(before,self.grant()['lease_id']);self.assertEqual([],self.grant()['commands'])
        self.assertEqual('cancelled',self.results()[a['id']]['state'])
        self.assertTrue(self.g.active('Forge'))
    def test_exact_retry_deduplicates_changed_payload_rejected(self):
        a=self.submit(target=[0,64,0]);self.assertEqual(a,self.submit(rid=a['id'],target=[0,64,0]))
        self.assertEqual('request_id_reused',self.f.error(409,lambda:self.submit(rid=a['id'],target=[1,64,0])))
        self.assertEqual(1,len(self.grant()['commands']))
    def test_epoch_change_and_expired_results_are_explicit(self):
        a=self.submit('dig',target=[1,64,0]);self.sample.update(tick=102,body_epoch='new')
        self.g.frame(self.sample);self.assertEqual('body_changed',self.results()[a['id']]['reason'])
        self.f.now+=601
        self.assertEqual('unknown',self.f.call('GET','/v1/action-results',{'action_id':a['id']})['results'][0]['state'])
    def test_whitelist_revocation_closes_grant_and_records_outcome(self):
        a=self.submit('dig',target=[1,64,0]);self.f.members.clear()
        self.assertIsNone(self.grant()['lease_id'])
        self.assertEqual('cancelled',self.g.actions['Forge'][a['id']]['result']['state'])
    def test_new_primitive_validation_and_area_checks(self):
        bad=[('select_slot',{'slot':9}),('jump',{'enabled':1}),('drop',{'slot':0,'count':0}),
             ('query_blocks',{'target':[0,64,0],'radius':5}),('chat',{'text':'/op me'}),
             ('craft',{'recipe_id':'Minecraft:Bad','count':1}),('dig',{'target':[.5,64,0]}),
             ('move_item',{'session_id':'s','revision':0,'from':{'inventory':'player','slot':40},'to':{'inventory':'container','slot':0},'count':1})]
        for op,fields in bad:
            with self.subTest(op=op):self.f.error(400,lambda:self.submit(op,**fields))
        self.assertEqual('outside_work_area',self.f.error(403,lambda:self.submit('dig',target=[20,64,0])))
        self.f.error(400,lambda:self.submit(target=[1,64,0],unexpected=True))
    def test_capabilities_legacy_chat_and_goal_truthful(self):
        self.sample['raw_capabilities']=['look_at'];self.g.frame(self.sample)
        self.assertEqual('adapter_upgrade_required',self.f.error(409,lambda:self.submit('dig',target=[1,64,0])))
        self.assertEqual('use_chat_primitive',self.f.error(409,lambda:self.f.call('POST','/v1/chat',{'text':'Hi','request_id':'r'*16})))
    def test_native_terminal_wins_over_disconnect_uncertainty(self):
        a=self.submit('drop',slot=0,count=1)
        with self.g.changed:self.g.release('Forge','stream_disconnected')
        self.sample.update(tick=102,action_results=[dict(id=a['id'],state='done',body_epoch='epoch2',reason='dropped')])
        self.g.frame(self.sample)
        self.assertEqual('done',self.results()[a['id']]['state'])
    def test_container_fields_forward_exactly_and_reject_unknown_revision(self):
        a=self.submit('move_item',session_id='session',revision=4,**{'from':{'inventory':'player','slot':0},'to':{'inventory':'container','slot':0},'count':2})
        command=self.grant()['commands'][0]
        self.assertEqual(4,command['revision']);self.assertEqual(a['id'],command['id'])
        self.f.error(400,lambda:self.submit('close_container',session_id='session'))
    def test_queue_bound_is_explicit_and_preserves_every_accepted_id(self):
        for n in range(32):
            self.sample['tick']+=1;self.g.frame(self.sample)
            self.submit('select_slot',slot=n%9)
        self.assertEqual('action_queue_full',self.f.error(429,lambda:self.submit('select_slot',slot=0)))
        self.assertEqual(32,len(self.g.actions['Forge']));self.assertEqual(16,len(self.grant()['commands']))

    def test_result_payload_ack_compaction_and_pending_details(self):
        a=self.submit('query_recipes',limit=1)
        self.sample.update(tick=102,action_results=[dict(id=a['id'],state='done',body_epoch='epoch2',details_pending=True)])
        self.g.frame(self.sample)
        self.assertNotIn(a['id'],self.grant()['acknowledged_results'])
        recipes=[{'recipe_id':'minecraft:stick','ingredients':['a'*1000]}]
        self.sample.update(tick=103,action_results=[dict(id=a['id'],state='done',body_epoch='epoch2',recipes=recipes)])
        self.g.frame(self.sample)
        self.assertIn(a['id'],self.grant()['acknowledged_results'])
        compact=self.results()[a['id']]
        self.assertNotIn('recipes',compact);self.assertTrue(compact['details_available'])
        self.sample.update(tick=104,action_results=[dict(id=a['id'],state='done',body_epoch='epoch2',details_retained_by_gateway=True)])
        self.g.frame(self.sample)
        full=self.f.call('GET','/v1/action-results',{'action_id':a['id']})['results'][0]
        self.assertEqual(recipes,full['recipes'])
    def test_ttl_queue_time_is_subtracted_and_stop_bypasses_rate_limit(self):
        a=self.submit('move_to',target=[1,64,0],ttl_seconds=10)
        self.f.now+=2
        self.assertLessEqual(self.grant()['commands'][0]['timeout_ticks'],160)
        self.g.rates[('request',self.g.authenticate(self.f.h['Authorization'])['hash'])]=self.f.now+10
        self.assertEqual('stopped',self.g.handle('DELETE','/v1/goal',self.f.h,{})['status'])

    def test_chat_native_utf16_boundary_and_invalid_controls(self):
        body=self.g.body('Forge');frame=self.g.frames['Forge']
        def validate(text):
            return self.g.primitive(dict(id='chat_boundary_0001',op='chat',body_epoch='epoch2',text=text),frame,body)
        self.assertEqual(220,len(validate('a'*220)[0]['text']))
        self.assertEqual(chr(0x1f600)*110,validate(chr(0x1f600)*110)[0]['text'])
        for text in ('a'*221,chr(0x1f600)*111,'hello'+chr(127),chr(0xd800),chr(0xdc00),'   '):
            with self.subTest(length=len(text)):
                self.f.error(400,lambda:validate(text))


class SDKContractTests(unittest.TestCase):
    def test_wrappers_handles_and_readiness(self):
        class Fake(fixtures.sdk.PrimitiveMethods):
            def observe(self):return {'container':{'session_id':'session','revision':7}}
            def action(self,op,**fields):return dict(op=op,**fields)
        client=Fake()
        self.assertEqual('select_slot',client.select_slot(1)['op'])
        self.assertEqual(7,client.move_item({'inventory':'player','slot':0},{'inventory':'container','slot':1},2)['revision'])
        self.assertEqual('session',client.close_container()['session_id'])
        self.assertEqual(42,client.use_on(entity_id=42)['entity_id'])
        self.assertNotIn('face',client.use_on(entity_id=42))
        self.assertEqual([[1,2,3]],client.query_blocks(positions=[(1,2,3)])['positions'])
        self.assertEqual(16,client.query_recipes(limit=16)['limit'])
        with self.assertRaises(ValueError):client.use_on([1,2,3],entity_id=1)
        class Completion:
            def wait_action(self,rid,timeout):return dict(id=rid,state='failed',reason='out_of_reach')
        handle=fixtures.sdk.ActionHandle(Completion(),{'id':'a'*16,'state':'accepted'})
        self.assertEqual('accepted',handle['state'])
        with self.assertRaises(fixtures.sdk.ActionFailed):handle.result()
