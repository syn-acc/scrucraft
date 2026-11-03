"""Deferred native payloads must remain bounded work and reach a finite result."""
import unittest
import test_controller_gateway as fixtures


class ResultBackpressureTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.GatewayTests();self.f.setUp();self.g=self.f.g
        self.sample=fixtures.frame(tick=102)
        self.sample.update(body_epoch='epoch',control_protocol=2,raw_capabilities=['query_blocks'],action_results=[])
        self.g.frame(self.sample);self.f.lease()
    def tearDown(self):self.f.tearDown()
    def query(self,index):
        return self.f.call('POST','/v1/actions',dict(id='block_query_'+str(index).zfill(8),op='query_blocks',body_epoch='epoch',target=[0,64,0],radius=4))
    def grant(self):
        with self.g.changed:return self.g.realtime_control('Forge')
    def test_pending_payloads_apply_backpressure_then_expire_explicitly(self):
        ids=[]
        for n in range(32):
            receipt=self.query(n);ids.append(receipt['id'])
            self.sample['tick']+=1
            self.sample['action_results'].append(dict(id=receipt['id'],state='done',body_epoch='epoch',details_pending=True))
            self.g.frame(self.sample)
        self.assertEqual([],self.grant()['acknowledged_results'])
        self.assertEqual('action_queue_full',self.f.error(429,lambda:self.query(32)))
        self.f.now+=31
        for rid in ids:
            row=self.f.call('GET','/v1/action-results',{'action_id':rid})['results'][0]
            self.assertEqual('failed',row['state']);self.assertEqual('result_details_timeout',row['reason'])
            self.assertNotIn('details_pending',row)
    def test_pending_payload_after_stop_cannot_keep_sdk_waiting(self):
        receipt=self.query(1)
        self.sample.update(tick=103,action_results=[dict(id=receipt['id'],state='done',body_epoch='epoch',details_pending=True)])
        self.g.frame(self.sample);self.f.call('DELETE','/v1/goal')
        row=self.f.call('GET','/v1/action-results',{'action_id':receipt['id']})['results'][0]
        self.assertEqual('cancelled',row['state']);self.assertNotIn('details_pending',row)
    def test_orphan_full_result_is_recovered_and_acknowledged_without_lease(self):
        receipt=self.query(1)
        self.g.actions.clear();self.g.native_acks.clear();self.g.leases.clear()
        self.sample.update(tick=103,action_results=[dict(id=receipt['id'],state='done',body_epoch='epoch',blocks=[{'block':'minecraft:stone'}])])
        self.g.frame(self.sample)
        row=self.f.call('GET','/v1/action-results',{'action_id':receipt['id']})['results'][0]
        self.assertEqual('done',row['state']);self.assertTrue(row['recovered']);self.assertEqual('minecraft:stone',row['blocks'][0]['block'])
        grant=self.grant();self.assertIsNone(grant['lease_id']);self.assertIn(receipt['id'],grant['acknowledged_results'])
        self.sample['action_results']=[dict(id=receipt['id'],state='done',body_epoch='epoch',details_retained_by_gateway=True)]
        self.sample['tick']+=1;self.g.frame(self.sample)
        self.assertEqual(row['blocks'],self.f.call('GET','/v1/action-results',{'action_id':receipt['id']})['results'][0]['blocks'])
        self.assertNotIn(receipt['id'],self.grant()['acknowledged_results'])
        self.sample['action_results']=[dict(row,details_retained_by_gateway=False)]
        self.sample['tick']+=1;self.g.frame(self.sample)
        self.assertIn(receipt['id'],self.grant()['acknowledged_results'],'A full native replay must be acknowledged again')
    def test_ack_window_includes_old_action_after_many_new_outcomes(self):
        self.g.leases.clear()
        ids=['old_completion_'+str(n).zfill(8) for n in range(100)]
        self.sample.update(tick=103,action_results=[dict(id=rid,state='done',body_epoch='epoch',tick=n) for n,rid in enumerate(ids)])
        self.g.frame(self.sample)
        self.assertEqual(set(ids),set(self.grant()['acknowledged_results']))

    def test_push_window_tracks_transitions_and_keeps_unfinished_details(self):
        old=self.query(1)['id'];pending=self.query(2)['id']
        self.sample.update(tick=103,action_results=[dict(id=pending,state='done',body_epoch='epoch',details_pending=True)])
        self.g.frame(self.sample)
        newer=[dict(id='completed_'+str(n).zfill(16),state='done',reason='oriented',body_epoch='epoch',tick=n) for n in range(100)]
        self.sample.update(tick=104,action_results=newer);self.g.frame(self.sample)
        rows=self.g.stream_results('Forge')
        self.assertEqual(66,len(rows));self.assertIn(old,[r['id'] for r in rows]);self.assertIn(pending,[r['id'] for r in rows])
        self.sample.update(tick=105,action_results=[dict(id=old,state='done',reason='arrived',body_epoch='epoch',tick=105)])
        self.g.frame(self.sample)
        rows=self.g.stream_results('Forge');self.assertEqual(old,rows[-1]['id']);self.assertEqual('done',rows[-1]['state'])
        self.assertEqual(65,len(rows));self.assertIn(pending,[r['id'] for r in rows])
        self.assertEqual('done',self.f.call('GET','/v1/action-results',{'action_id':newer[0]['id']})['results'][0]['state'])

    def test_push_cache_expires_with_authoritative_retention(self):
        self.sample.update(tick=103,action_results=[dict(id='old_completion_00000001',state='done',body_epoch='epoch')])
        self.g.frame(self.sample);self.assertEqual(1,len(self.g.stream_results('Forge')))
        self.f.now+=601;self.g.update_results('Forge')
        self.assertEqual([],self.g.stream_results('Forge'))
