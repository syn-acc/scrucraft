import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('syn_controller',pathlib.Path(__file__).parents[1]/'agent-service/service.py')
controller=importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)

def frame():
    return {'schema':1,'agent':'Syn_Test','job':'farmer','tick':100,'position':[.5,64,.5],'health':20,'food':20,'thirst':20,'temperature':20,'night':False,'sheltered':False,'inventory':[],'entities':[],'blocks':[],
            'walkable':[{'pos':[x,64,0],'sheltered':False} for x in range(5)]}

class SurvivalTests(unittest.TestCase):
    def test_path_stays_on_observed_ground(self):
        o=frame(); result=controller.step_toward(o,[4.5,64,.5])
        self.assertEqual(result['target'],[1.5,64,.5])
        self.assertEqual(result['path'],[[1.5,64,.5],[2.5,64,.5],[3.5,64,.5],[4.5,64,.5]])
        o['walkable']=[{'pos':[0,64,0]},{'pos':[3,64,0]}]
        result=controller.step_toward(o,[3.5,64,.5])
        self.assertEqual(result['kind'],'idle');self.assertIn('route',result['reason'])
    def test_thirst_requires_real_drink(self):
        o=frame(); o['thirst']=1
        self.assertNotEqual(controller.choose(o)['kind'],'drink')
        o['inventory']=[{'slot':0,'item':'legendarysurvivaloverhaul:purified_water_bottle','count':1,'hydration':6}]
        self.assertEqual(controller.choose(o),{'kind':'drink'})
    def test_no_attack_on_players(self):
        o=frame(); o['job']='guard'; o['entities']=[{'id':1,'position':[1,64,0],'hostile':False}]
        self.assertNotEqual(controller.choose(o)['kind'],'attack')
    def test_normal_lso_temperature_does_not_force_shelter(self):
        o=frame();o['sheltered']=True;o['temperature']=18
        o['blocks']=[{'pos':[1,64,0],'block':'minecraft:oak_log'}]
        self.assertEqual(controller.choose(o,'gather_wood'),{'kind':'mine','pos':[1,64,0]})
        o['temperature']=34
        self.assertEqual(controller.choose(o,'gather_wood')['kind'],'idle')
    def test_path_starts_at_feet_not_adjacent_block_corner(self):
        o=frame();o['position']=[1.7,64,.5]
        self.assertEqual(controller.step_toward(o,[.5,64,.5])['target'],[.5,64,.5])
    def test_follow_and_stop(self):
        o=frame();o['humans']=[{'name':'Jamie_Syn','position':[4.5,64,.5]}];o['task']={'owner':'Jamie_Syn'}
        self.assertEqual(controller.choose(o,'follow')['kind'],'move')
        self.assertEqual(controller.choose(o,'rest')['kind'],'idle')
    def test_follow_is_not_preempted_by_dropped_items(self):
        o=frame();o['walkable']=[{'pos':[x,64,0]} for x in range(-5,5)]
        o['humans']=[{'name':'Jamie_Syn','position':[-4.5,64,.5]}]
        o['entities']=[{'id':4,'hostile':False,'position':[3.5,64,.5]}]
        self.assertEqual(controller.choose(o,'follow')['target'],[-.5,64,.5])
    def test_resource_selection_skips_unreachable_near_tree(self):
        o=frame();o['walkable']=[{'pos':[x,64,0]} for x in range(10)]
        o['blocks']=[{'pos':[0,71,0],'block':'minecraft:oak_log','reachable':False},{'pos':[8,64,0],'block':'minecraft:oak_log','reachable':False}]
        action=controller.choose(o,'gather_wood')
        self.assertEqual(action['kind'],'move');self.assertEqual(action['work_target'],[8,64,0])
        o['_work_target']=[8,64,0];o['blocks'].append({'pos':[1,64,0],'block':'minecraft:oak_log','reachable':True})
        self.assertEqual(controller.choose(o,'gather_wood')['work_target'],[8,64,0])
    def test_ore_harvest_requires_correct_tool_evidence_or_known_tier(self):
        inv=[{'item':'minecraft:wooden_pickaxe','count':1}]
        self.assertFalse(controller.harvestable({'block':'minecraft:iron_ore'},inv))
        self.assertFalse(controller.harvestable({'block':'minecraft:iron_ore','harvestable':False},[{'item':'minecraft:diamond_pickaxe'}]))
        self.assertTrue(controller.harvestable({'block':'minecraft:deepslate_iron_ore'},[{'item':'minecraft:stone_pickaxe'}]))
        self.assertTrue(controller.harvestable({'block':'create:zinc_ore','harvestable':True},inv))
    def test_build_consumes_only_observed_inventory(self):
        o=frame();o['project']={'origin':[0,64,0],'done':1,'total':80,'clear':[],'cells':[{'pos':[1,64,0],'stage':1,'done':False,'supported':True,'support':[1,63,0],'face':'up'}]}
        o['inventory']=[{'slot':0,'item':'minecraft:oak_log','count':1}]
        self.assertEqual(controller.choose(o,'build_shelter')['kind'],'craft_planks')
        o['inventory']=[{'slot':3,'item':'minecraft:oak_planks','count':4}]
        result=controller.choose(o,'build_shelter');self.assertTrue(result.pop('work_key'))
        self.assertEqual(result,{'kind':'place','pos':[1,63,0],'face':'up','slot':3,'build_target':[1,64,0]})
        o['inventory']=[]
        self.assertNotEqual(controller.choose(o,'build_shelter')['kind'],'place')
    def test_visible_block_is_not_enough_when_click_face_is_hidden(self):
        self.assertFalse(controller.can_click([.5,64.62,.5],[1,64,0],'up',{(1,64,0)}))
        self.assertTrue(controller.can_click([.5,65.62,.5],[1,64,0],'up',{(1,64,0)}))
    def test_builder_moves_to_elevated_work_pose_instead_of_clicking_hidden_face(self):
        o=frame();o['walkable']=[{'pos':[0,64,0]},{'pos':[0,65,1]}]
        row={'pos':[1,66,0],'support':[1,65,0],'face':'up','stage':2,'supported':True}
        o['project']={'cells':[row]}
        result=controller.construction_step(o,[row],{'slot':0})
        self.assertEqual(result['kind'],'move');self.assertEqual(result['target'],[.5,65,1.5])
    def test_angry_enderman_uses_low_cover_without_barehanded_attack(self):
        o=frame();o['walkable'][1]['jump_room']=False
        o['entities']=[{'id':7,'type':'minecraft:enderman','hostile':True,'position':[-2.5,64,.5]}]
        action=controller.choose(o,'gather_wood')
        self.assertEqual(action['target'],[1.5,64,.5]);self.assertIn('cover',action['reason'])
        o['position']=[1.5,64,.5]
        self.assertEqual(controller.choose(o,'gather_wood')['kind'],'idle')
        o['health']=2;o['entities'][0]['position']=[3.5,64,.5]
        action=controller.choose(o,'industrialise')
        self.assertEqual(action['kind'],'move');self.assertLess(action['target'][0],o['position'][0])
    def test_injured_agent_moves_deeper_under_roof_instead_of_attacking(self):
        o=frame();o['position']=[1.5,64,.5];o['health']=3;o['sheltered']=True
        o['walkable']=[{'pos':[x,64,z],'jump_room':False,'sheltered':True} for x in range(1,8) for z in range(-3,4)]
        o['entities']=[{'id':7,'type':'minecraft:enderman','hostile':True,'position':[.5,64,.5]}]
        action=controller.choose(o,'industrialise')
        self.assertEqual(action['kind'],'move');self.assertGreater(action['target'][0],o['position'][0])
        self.assertIn('cover',action['reason'])
    def test_retreat_considers_second_monster_and_ignores_unreachable_cover(self):
        o=frame();o['health']=2
        o['walkable']=[{'pos':[x,64,0]} for x in range(-4,5)]+[{'pos':[0,64,z]} for z in range(-4,5)]+[{'pos':[9,64,9],'jump_room':False}]
        o['entities']=[{'id':7,'type':'minecraft:enderman','hostile':True,'position':[-1.5,64,.5]},{'id':8,'type':'minecraft:zombie','hostile':True,'position':[3.5,64,.5]}]
        action=controller.choose(o,'industrialise')
        self.assertEqual(action['kind'],'move');self.assertEqual(action['target'][0],.5)
        self.assertNotEqual(action['target'][2],.5)
        self.assertIn('Fleeing',action['reason'])
    def test_critical_health_does_not_fall_through_into_industry_without_shelter(self):
        o=frame();o['health']=1.5;o['blocks']=[{'pos':[1,64,0],'block':'minecraft:oak_log','reachable':True}]
        self.assertEqual(controller.choose(o,'industrialise')['kind'],'idle')
        o['sheltered']=True
        action=controller.choose(o,'industrialise')
        self.assertEqual(action['kind'],'idle');self.assertIn('shelter',action['reason'])

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.rootpatch=patch.object(controller,'ROOT',pathlib.Path(self.temp.name)); self.rootpatch.start()
        self.c=controller.Controller(); self.c.key='test-key'
    def tearDown(self):
        self.c.pool.shutdown(wait=True); self.c.db.close(); self.rootpatch.stop(); self.temp.cleanup()
    def test_budget_reservation_blocks_network(self):
        import time
        self.c.db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',('used',time.time(),'Syn_Test','decision','PUBLISHED',2,2,'{}','{}')); self.c.db.commit()
        with patch.object(controller.urllib.request,'urlopen') as network:
            self.c.infer(('Syn_Test','decision'),controller.compact(frame()))
            network.assert_not_called()
        self.assertEqual(self.c.db.execute("SELECT count(*) FROM runs WHERE status='BUDGET_SKIP'").fetchone()[0],1)
    def test_failed_dispatch_keeps_reservation(self):
        with patch.object(controller.urllib.request,'urlopen',side_effect=TimeoutError): self.c.infer(('Syn_Test','decision'),controller.compact(frame()))
        status,reserved,cost=self.c.db.execute('SELECT status,reserved,cost FROM runs').fetchone()
        self.assertEqual(status,'FAILED'); self.assertGreater(reserved,0); self.assertIsNone(cost)
    def test_direct_openai_payload_and_conservative_cost(self):
        import io
        self.c.provider='openai'
        response={'choices':[{'message':{'content':json.dumps({'goal':'shelter','reason':'Cold weather'})}}], 'usage':{'prompt_tokens':1000,'completion_tokens':50,'prompt_tokens_details':{'cached_tokens':500}}}
        with patch.object(controller.urllib.request,'urlopen',return_value=io.StringIO(json.dumps(response))) as network:
            self.c.infer(('Syn_Test','decision'),controller.compact(frame()))
        request=network.call_args.args[0]; payload=json.loads(request.data)
        self.assertEqual(request.full_url,'https://api.openai.com/v1/chat/completions')
        self.assertEqual(payload['model'],'gpt-4o-mini'); self.assertNotIn('provider',payload); self.assertFalse(payload['store'])
        status,cost=self.c.db.execute('SELECT status,cost FROM runs').fetchone()
        self.assertEqual(status,'PUBLISHED'); self.assertAlmostEqual(cost,.00018)
        self.assertEqual(self.c.health()['active_policies'][0]['goal'],'shelter')
    def test_chat_orders_persist_and_agent_speech_cannot_assign(self):
        o=frame();o['chat']=[{'id':'one','speaker':'Jamie_Syn','text':'Agents, build a settlement here','dimension':'minecraft:overworld'}]
        self.c.ingest_chat(o)
        self.assertEqual(self.c.tasks['Syn_Test']['goal'],'build_shelter')
        revision=self.c.revision;self.c.ingest_chat(o);self.assertEqual(self.c.revision,revision)
        o['chat']=[{'id':'two','speaker':'Syn_Forge','agent':True,'text':'Agents stop'}];self.c.ingest_chat(o)
        self.assertEqual(self.c.tasks['Syn_Test']['goal'],'build_shelter')
        saved=json.loads(self.c.db.execute("SELECT value FROM state WHERE key='coordination'").fetchone()[0])
        self.assertEqual(saved['tasks']['Syn_Test']['goal'],'build_shelter')
    def test_new_chat_rejects_stale_model_publication(self):
        import io
        o=controller.compact(frame());o['chat_revision']=0;self.c.revision=1
        response={'choices':[{'message':{'content':json.dumps({'goal':'explore','reason':'Old request'})}}]}
        with patch.object(controller.urllib.request,'urlopen',return_value=io.StringIO(json.dumps(response))):self.c.infer(('Syn_Test','decision'),o)
        self.assertNotIn(('Syn_Test','decision'),self.c.policies)
    def test_full_decision_without_model_then_player_request(self):
        self.c.key='';o=frame()
        result=self.c.decide(o)
        self.assertIn(result['action']['kind'],{'move','idle'})
        self.assertNotIn('announcement_id',result)
        o['chat']=[{'id':'follow-one','speaker':'Jamie_Syn','text':'Syn_Test follow me'}]
        o['humans']=[{'name':'Jamie_Syn','position':[4.5,64,.5]}]
        result=self.c.decide(o)
        self.assertEqual(result['action']['kind'],'move')
        self.assertEqual(self.c.tasks['Syn_Test']['goal'],'follow')
    def test_unknown_new_task_is_left_to_model_instead_of_old_sticky_order(self):
        o=frame();o['chat']=[{'id':'stop','speaker':'Jamie_Syn','text':'Syn_Test stop'}];self.c.ingest_chat(o)
        self.assertEqual(self.c.tasks['Syn_Test']['goal'],'rest')
        o['chat']=[{'id':'new','speaker':'Jamie_Syn','text':'Syn_Test, find some berries'}];self.c.ingest_chat(o)
        self.assertIsNone(self.c.tasks['Syn_Test']['goal'])
    def test_model_answer_is_announced_after_initial_local_acknowledgement(self):
        self.c.tasks['Syn_Test']={'id':'previous','owner':'Jamie_Syn','goal':'gather_wood'}
        o=frame();o['blocks']=[{'pos':[1,64,0],'block':'minecraft:oak_log'}]
        o['chat']=[{'id':'question','speaker':'Jamie_Syn','text':'Syn_Test, what are you doing?'}]
        with patch.object(self.c.pool,'submit'),patch.object(controller.time,'time',return_value=100):first=self.c.decide(o)
        self.c.policies[('Syn_Test','decision')]={'id':'answer','expires':200,'output':{'goal':'gather_wood','say':'I need logs for our shelter.'}}
        with patch.object(self.c.pool,'submit'),patch.object(controller.time,'time',return_value=113):second=self.c.decide(o)
        self.assertNotIn('announcement_id',first)
        self.assertIn('I need logs for our shelter.',second['say'])
        self.assertNotIn('Now:',second['say'])
        o['chat'].append({'id':'echo','speaker':'Syn_Test','agent':True,'text':second['say']})
        self.c.policies[('Syn_Test','decision')]['output']['say']='A differently worded repeat.'
        self.c.policies[('Syn_Test','decision')]['expires']=1000
        with patch.object(self.c.pool,'submit'),patch.object(controller.time,'time',return_value=190):third=self.c.decide(o)
        self.assertNotIn('say',third)
    def test_model_intention_alias_becomes_public_speech(self):
        import io
        response={'choices':[{'message':{'content':json.dumps({'goal':'gather_wood','reason':'We need planks.','intention':'I need logs for our shelter.'})}}]}
        with patch.object(controller.urllib.request,'urlopen',return_value=io.StringIO(json.dumps(response))):self.c.infer(('Syn_Test','decision'),controller.compact(frame()))
        output=self.c.policies[('Syn_Test','decision')]['output']
        self.assertEqual(output['say'],'I need logs for our shelter.')
        self.assertEqual(set(output),{'goal','reason','say'})
    def test_no_routine_narration_on_action_changes_or_minute_heartbeat(self):
        self.c.key='';o=frame();o['humans']=[{'name':'Jamie_Syn','position':[2,64,0]}]
        for at,kind in [(100,'move'),(115,'mine'),(180,'place'),(240,'move'),(900,'mine')]:
            with patch.object(controller,'choose',return_value={'kind':kind}),patch.object(controller.time,'time',return_value=at):result=self.c.decide(o)
            self.assertNotIn('say',result)
    def test_blocker_announced_once_despite_flapping_and_elapsed_time(self):
        self.c.key='';o=frame();o['humans']=[{'name':'Jamie_Syn','position':[2,64,0]}]
        danger={'kind':'move','reason':'Fleeing a nearby monster; I will resume my task when safe.'}
        with patch.object(controller,'choose',return_value=danger),patch.object(controller.time,'time',return_value=100):first=self.c.decide(o)
        self.assertIn('Hostiles',first['say'])
        o['chat']=[{'id':'echo','speaker':'Syn_Test','agent':True,'text':first['say']}]
        with patch.object(controller,'choose',return_value={'kind':'move'}),patch.object(controller.time,'time',return_value=115):self.assertNotIn('say',self.c.decide(o))
        with patch.object(controller,'choose',return_value=danger),patch.object(controller.time,'time',return_value=900):self.assertNotIn('say',self.c.decide(o))
        saved=json.loads(self.c.db.execute("SELECT value FROM state WHERE key='speech'").fetchone()[0])
        self.assertTrue(saved['events'])
        replacement=controller.Controller();replacement.key=''
        try:
            with patch.object(controller,'choose',return_value=danger),patch.object(controller.time,'time',return_value=1800):self.assertNotIn('say',replacement.decide(o))
        finally:replacement.pool.shutdown(wait=True);replacement.db.close()
    def test_shared_milestone_has_one_announcement_for_the_team(self):
        self.c.key='';o=frame();o['humans']=[{'name':'Jamie_Syn','position':[2,64,0]}]
        o['inventory']=[{'slot':0,'item':'minecraft:oak_planks','count':16}]
        o['project']={'origin':[0,64,0],'done':35,'total':85,'clear':[],'cells':[]}
        with patch.object(controller,'choose',return_value={'kind':'move'}),patch.object(controller.time,'time',return_value=100):self.assertNotIn('say',self.c.decide(o))
        o['project']['done']=45
        with patch.object(controller,'choose',return_value={'kind':'place'}),patch.object(controller.time,'time',return_value=120):first=self.c.decide(o)
        self.assertIn('halfway',first['say'])
        o['agent']='Syn_Second'
        with patch.object(controller,'choose',return_value={'kind':'place'}),patch.object(controller.time,'time',return_value=250):self.assertNotIn('say',self.c.decide(o))
    def test_explicit_silence_is_not_replaced_with_model_reason(self):
        import io
        response={'choices':[{'message':{'content':json.dumps({'goal':'explore','reason':'Routine work.','say':''})}}]}
        with patch.object(controller.urllib.request,'urlopen',return_value=io.StringIO(json.dumps(response))):self.c.infer(('Syn_Test','decision'),controller.compact(frame()))
        self.assertEqual(self.c.policies[('Syn_Test','decision')]['output']['say'],'')
    def test_failed_placement_is_backed_off_and_not_counted_as_success(self):
        o=frame();o['project']={'cells':[{'pos':[1,64,0],'done':False}]}
        self.c.observe_skill(o,100)
        action={'kind':'place','pos':[1,63,0],'face':'up','slot':0,'build_target':[1,64,0],'work_key':'failed-pose'}
        self.c.record_skill(o,action,100);self.c.observe_skill(o,105)
        self.assertIn('failed-pose',o['_failed_work'])
        self.assertEqual(self.c.skills['Syn_Test']['verified'],0)
        self.assertEqual(self.c.skills['Syn_Test']['failed'],1)
    def test_actual_world_change_verifies_placement_before_timeout(self):
        o=frame();o['project']={'cells':[{'pos':[1,64,0],'done':False}]}
        self.c.observe_skill(o,100)
        self.c.record_skill(o,{'kind':'place','build_target':[1,64,0],'work_key':'good-pose'},100)
        o['project']['cells'][0]['done']=True;self.c.observe_skill(o,102)
        self.assertEqual(self.c.skills['Syn_Test']['verified'],1)
        self.assertEqual(self.c.skills['Syn_Test']['failed'],0)
    def test_scan_disappearance_does_not_verify_mining_but_real_loot_does(self):
        o=frame();o['blocks']=[{'pos':[1,64,0],'block':'minecraft:oak_log'}]
        self.c.observe_skill(o,100);self.c.record_skill(o,{'kind':'mine','pos':[1,64,0]},100)
        o['blocks']=[];self.c.observe_skill(o,101)
        self.assertEqual(self.c.skills['Syn_Test']['verified'],0)
        o['inventory']=[{'item':'minecraft:oak_log','count':1,'slot':0}]
        self.c.observe_skill(o,102);self.assertEqual(self.c.skills['Syn_Test']['verified'],1)
    def test_pickup_detour_expires_even_when_agent_keeps_moving(self):
        self.c.key='';o=frame();self.c.tasks['Syn_Test']={'goal':'gather_wood'}
        o['entities']=[{'id':8,'hostile':False,'position':[2.5,64,.5]}]
        o['blocks']=[{'pos':[1,64,0],'block':'minecraft:oak_log','reachable':True}]
        with patch.object(controller.time,'time',return_value=100):first=self.c.decide(o)
        self.assertEqual(first['action'].get('pickup_id'),8)
        o['position']=[1.5,64,.5]
        with patch.object(controller.time,'time',return_value=109):later=self.c.decide(o)
        self.assertEqual(later['action']['kind'],'mine');self.assertNotIn('pickup_id',later['action'])
    def test_approach_claims_are_shared_only_within_dimension(self):
        self.c.key='';o=frame();o['walkable']=[{'pos':[x,64,0]} for x in range(10)]
        o['blocks']=[{'pos':[8,64,0],'block':'minecraft:oak_log','reachable':False}]
        self.c.tasks['Syn_Test']={'goal':'gather_wood'}
        self.c.observed['Syn_Other']={'dimension':'minecraft:overworld','observed_at':100}
        self.c.actions['Syn_Other']={'action':{'kind':'move','work_target':[8,64,0]}}
        with patch.object(controller.time,'time',return_value=101):claimed=self.c.decide(o)
        self.assertNotIn('work_target',claimed['action'])
        o['dimension']='minecraft:the_nether'
        with patch.object(controller.time,'time',return_value=102):other_dimension=self.c.decide(o)
        self.assertEqual(other_dimension['action'].get('work_target'),[8,64,0])
    def test_stable_explicit_work_does_not_schedule_decision_inference(self):
        o=frame();o['blocks']=[{'pos':[1,64,0],'block':'minecraft:oak_log','reachable':True}]
        self.c.tasks['Syn_Test']={'goal':'gather_wood','id':'work','text':'Gather logs','at':1000}
        with patch.object(controller.time,'time',return_value=1000),patch.object(self.c.pool,'submit') as submit:self.c.decide(o)
        lanes=[call.args[1][1] for call in submit.call_args_list]
        self.assertEqual(lanes,['strategic','tactical'])
        self.c.pending.clear();o['chat']=[{'id':'question-new','speaker':'Jamie_Syn','text':'Syn_Test, what are you doing?','at':1020}]
        with patch.object(controller.time,'time',return_value=1020),patch.object(self.c.pool,'submit') as submit:self.c.decide(o)
        self.assertEqual(submit.call_args_list[0].args[1][1],'decision')
    def test_health_keeps_inventory_and_advancements_before_work_filtering(self):
        self.c.key='';o=frame();o['inventory']=[{'slot':0,'item':'minecraft:oak_log','count':2},{'slot':1,'item':'minecraft:oak_log','count':3}]
        o['advancements']=['minecraft:story/mine_stone'];o['capabilities']={'craft':True};o['survival_profile']='vanilla'
        self.c.decide(o);observed=self.c.health()['agents']['Syn_Test']
        self.assertEqual(observed['inventory'],{'minecraft:oak_log':5})
        self.assertEqual(observed['advancements'],o['advancements'])
        self.assertEqual(observed['capabilities'],o['capabilities'])
        self.assertEqual(observed['survival_profile'],'vanilla')

if __name__=='__main__': unittest.main()
