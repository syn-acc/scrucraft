import importlib.util,pathlib,tempfile,unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('progression_controller',pathlib.Path(__file__).parents[1]/'agent-service/service.py')
controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)

def frame(items=()):
    return {'schema':1,'agent':'Syn_Test','job':'engineer','tick':100,'position':[.5,64,.5],
        'health':20,'food':20,'thirst':20,'temperature':20,'night':False,'sheltered':False,
        'capabilities':['craft','place_workstation','furnace_insert','furnace_extract'],
        'inventory':[{'slot':n,'item':item,'count':count} for n,(item,count) in enumerate(items)],
        'entities':[],'blocks':[],'workstations':[],
        'walkable':[{'pos':[x,64,z]} for x in range(-2,4) for z in range(-2,3)]}

class ProgressionTests(unittest.TestCase):
    def test_capability_gate_does_not_pretend_unsupported_progress(self):
        o=frame();o['capabilities']=[]
        a=controller.choose(o,'industrialise')
        self.assertEqual(a['kind'],'idle');self.assertTrue(a['production_blocked'])

    def test_recipe_never_reuses_more_items_than_owned(self):
        o=frame([('minecraft:oak_planks',3)])
        self.assertIsNone(controller.recipe_slots(o,['planks']*4))
        o['inventory'][0]['count']=4
        self.assertEqual(controller.recipe_slots(o,['planks']*4),[0]*4)

    def test_bootstrap_crafts_table_before_three_by_three_tool(self):
        o=frame([('minecraft:oak_planks',8),('minecraft:stick',2)])
        a=controller.choose(o,'industrialise')
        self.assertEqual(a['output'],'minecraft:crafting_table');self.assertEqual(a['width'],2)
        o['workstations']=[{'pos':[1,64,0],'block':'minecraft:crafting_table','reachable':True}]
        a=controller.choose(o,'industrialise')
        self.assertEqual(a['output'],'minecraft:wooden_pickaxe');self.assertEqual(a['slots'],[0,0,0,-1,1,-1,-1,1,-1])

    def test_table_placement_uses_real_inventory_and_clear_floor(self):
        o=frame([('minecraft:crafting_table',1),('minecraft:oak_planks',3),('minecraft:stick',2)])
        a=controller.choose(o,'industrialise')
        self.assertEqual(a['kind'],'place_workstation');self.assertNotEqual(a['build_target'],[0,64,0])
        self.assertEqual(a['pos'][1],63)

    def test_stone_tool_gathers_missing_material_before_returning_to_table(self):
        o=frame([('minecraft:wooden_pickaxe',1),('minecraft:stick',2)])
        o['walkable']=[{'pos':[x,64,0]} for x in range(13)]
        o['workstations']=[{'pos':[10,64,0],'block':'minecraft:crafting_table','reachable':False}]
        o['blocks']=[{'pos':[2,64,0],'block':'minecraft:stone','reachable':True,'harvestable':True}]
        a=controller.choose(o,'industrialise')
        self.assertEqual(a['kind'],'mine');self.assertEqual(a['pos'],[2,64,0])
        self.assertEqual(a['production_target'],'minecraft:stone_pickaxe')
        o['inventory'].append({'slot':2,'item':'minecraft:cobblestone','count':3})
        a=controller.choose(o,'industrialise')
        self.assertEqual(a['kind'],'move');self.assertEqual(a['work_target'],[10,64,0])
        o['workstations'][0]['reachable']=True
        a=controller.choose(o,'industrialise')
        self.assertEqual(a['kind'],'craft');self.assertEqual(a['output'],'minecraft:stone_pickaxe')

    def test_table_construction_rechecks_shared_plank_stock_before_tool_craft(self):
        o=frame([('minecraft:oak_planks',5),('minecraft:stick',2)])
        self.assertEqual(controller.choose(o,'industrialise')['output'],'minecraft:crafting_table')
        # A later authoritative observation reports four planks spent on the table.
        o['inventory'][0]['count']=1
        o['inventory'].append({'slot':2,'item':'minecraft:crafting_table','count':1})
        o['blocks']=[{'pos':[2,64,0],'block':'minecraft:oak_log','reachable':True,'harvestable':True}]
        a=controller.choose(o,'industrialise')
        self.assertEqual(a['kind'],'mine');self.assertEqual(a['pos'],[2,64,0])
        o['inventory'][0]['count']=3
        self.assertEqual(controller.choose(o,'industrialise')['kind'],'place_workstation')
        o['workstations']=[{'pos':[1,64,0],'block':'minecraft:crafting_table','reachable':True}]
        a=controller.choose(o,'industrialise')
        self.assertEqual(a['kind'],'craft');self.assertEqual(a['slots'],[0,0,0,-1,1,-1,-1,1,-1])

    def test_gather_stone_never_mines_own_floor_or_wrong_tool(self):
        o=frame([('minecraft:wooden_pickaxe',1)])
        o['blocks']=[{'pos':[0,63,0],'block':'minecraft:stone','reachable':True,'harvestable':True},
                     {'pos':[2,64,0],'block':'minecraft:stone','reachable':True,'harvestable':True}]
        a=controller.gather_material(o,'minecraft:cobblestone');self.assertEqual(a['pos'],[2,64,0])
        for r in o['blocks']:r['harvestable']=False
        self.assertNotEqual(controller.gather_material(o,'minecraft:cobblestone')['kind'],'mine')

    def test_furnace_uses_real_inputs_fuel_and_output(self):
        o=frame([('minecraft:raw_iron',3),('minecraft:coal',1)])
        station={'pos':[1,64,0],'block':'minecraft:furnace','reachable':True,'slots':[],'lit':False}
        o['workstations']=[station]
        self.assertEqual(controller.smelt_iron(o,0)['section'],'input')
        station['slots']=[{'section':'input','item':'minecraft:raw_iron','count':3}]
        self.assertEqual(controller.smelt_iron(o,0)['section'],'fuel')
        station['slots'].append({'section':'output','item':'minecraft:iron_ingot','count':1})
        self.assertEqual(controller.smelt_iron(o,0)['kind'],'furnace_extract')
        station['slots'][-1]['item']='minecraft:cooked_beef'
        self.assertTrue(controller.smelt_iron(o,0)['production_blocked'])

    def test_create_recipe_matches_installed_pack_and_requires_stock(self):
        o=frame([('minecraft:iron_nugget',2),('minecraft:andesite',2)])
        a=controller.obtain_material(o,'create:andesite_alloy')
        self.assertEqual(a,{'kind':'craft','width':2,'height':2,'slots':[0,1,1,0],'output':'create:andesite_alloy'})

    def test_components_do_not_claim_powered_factory(self):
        o=frame([('minecraft:iron_pickaxe',1),('create:water_wheel',1),('create:cogwheel',1)])
        a=controller.industrialise(o)
        self.assertEqual(a['production_stage'],'powered_factory_gate');self.assertTrue(a['production_blocked'])

    def test_craft_requires_observed_output_and_backs_off_failed_recipe(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(controller,'ROOT',pathlib.Path(temp)):
            c=controller.Controller();c.key=''
            try:
                o=frame([('minecraft:oak_planks',4)]);a={'kind':'craft','output':'minecraft:crafting_table'}
                c.observe_skill(o,100);c.record_skill(o,a,100);c.observe_skill(o,101)
                self.assertEqual(c.skills['Syn_Test']['verified'],0)
                c.observe_skill(o,121);self.assertIn('minecraft:crafting_table',o['_failed_recipes'])
                c.record_skill(o,a,122);o['inventory']=[{'slot':0,'item':'minecraft:crafting_table','count':1}]
                c.observe_skill(o,123);self.assertEqual(c.skills['Syn_Test']['verified'],1)
            finally:c.pool.shutdown(wait=True);c.db.close()

    def test_orders_select_industrial_progression_and_survival_preempts_it(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(controller,'ROOT',pathlib.Path(temp)):
            c=controller.Controller();c.key=''
            try:
                o=frame();o['chat']=[{'id':'industrial','speaker':'Jamie_Syn','text':'Agents, industrialise and get advancements'}]
                c.ingest_chat(o);self.assertEqual(c.tasks['Syn_Test']['goal'],'industrialise')
                o['food']=2;o['inventory']=[{'slot':0,'item':'minecraft:bread','count':1,'food':True}]
                self.assertEqual(controller.choose(o,'industrialise')['kind'],'eat')
            finally:c.pool.shutdown(wait=True);c.db.close()

if __name__=='__main__':unittest.main()
