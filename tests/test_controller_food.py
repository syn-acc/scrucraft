import importlib.util
import pathlib
import unittest


spec = importlib.util.spec_from_file_location(
    'food_controller', pathlib.Path(__file__).parents[1] / 'agent-service/service.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def frame():
    return {
        'agent': 'Syn_Test', 'job': 'engineer', 'tick': 100,
        'position': [.5, 64, .5], 'health': 20, 'food': 14, 'thirst': 20,
        'temperature': 20, 'night': False, 'sheltered': False,
        'inventory': [], 'entities': [], 'blocks': [], 'workstations': [],
        'capabilities': ['craft'],
        'walkable': [{'pos': [x, 64, 0]} for x in range(-4, 7)],
    }


class FoodSurvivalTests(unittest.TestCase):
    def test_vanilla_profile_does_not_create_removed_survival_needs(self):
        o = frame()
        o.update(food=20, thirst=0, temperature=0, survival_profile='vanilla')
        o['inventory'] = [{'slot': 0, 'item': 'minecraft:potion', 'count': 1, 'hydration': 6}]
        o['blocks'] = [{'pos': [1, 64, 0], 'block': 'minecraft:oak_log', 'reachable': True}]
        self.assertEqual(controller.choose(o, 'gather_wood'), {'kind': 'mine', 'pos': [1, 64, 0]})
        self.assertEqual(controller.compact(o)['survival_profile'], 'vanilla')

    def test_early_food_harvest_preempts_work_and_unidentified_item_detour(self):
        o = frame()
        o['entities'] = [{'id': 7, 'hostile': False, 'position': [-2.5, 64, .5]}]
        o['blocks'] = [
            {'pos': [1, 64, 0], 'block': 'minecraft:oak_log', 'reachable': True},
            {'pos': [2, 64, 0], 'block': 'minecraft:carrots', 'mature': True, 'reachable': True},
        ]
        action = controller.choose(o, 'industrialise')
        self.assertEqual(action['kind'], 'mine')
        self.assertEqual(action['pos'], [2, 64, 0])
        # After harvest, recover the actual drop and consume only once the next
        # authoritative inventory observation says an edible item was received.
        o['current_activity'] = action
        o['blocks'] = [{'pos': [3, 64, 0], 'block': 'minecraft:carrots', 'mature': True, 'reachable': True}]
        o['entities'] = [{'id': 8, 'hostile': False, 'position': [2.5, 64, .5]}]
        self.assertEqual(controller.choose(o, 'industrialise')['pickup_id'], 8)
        o['inventory'] = [{'slot': 0, 'item': 'minecraft:carrot', 'count': 2, 'food': True}]
        self.assertEqual(controller.choose(o, 'industrialise'), {'kind': 'eat'})

    def test_unreachable_crop_does_not_trigger_repeated_futile_approach(self):
        o = frame()
        o['food'] = 2
        o['walkable'] = [{'pos': [0, 64, 0]}, {'pos': [10, 64, 0]}]
        o['blocks'] = [{'pos': [10, 64, 1], 'block': 'minecraft:potatoes', 'mature': True, 'reachable': False}]
        action = controller.choose(o, 'industrialise')
        self.assertEqual(action['kind'], 'idle')
        self.assertIn('Food', action['reason'])

    def test_critical_hunger_pauses_nonfood_work_and_wandering(self):
        for goal in ('industrialise', 'gather_wood', 'gather_food', 'explore', 'build_shelter'):
            with self.subTest(goal=goal):
                o = frame()
                o['food'] = 6
                o['blocks'] = [{'pos': [1, 64, 0], 'block': 'minecraft:oak_log', 'reachable': True}]
                action = controller.choose(o, goal)
                self.assertEqual(action['kind'], 'idle')
                self.assertIn('Food', action['reason'])

    def test_wheat_and_unknown_crops_are_not_assumed_immediately_edible(self):
        for crop in ('minecraft:wheat', 'example:unknown_crop'):
            with self.subTest(crop=crop):
                o = frame()
                o['food'] = 4
                o['blocks'] = [{'pos': [1, 64, 0], 'block': crop, 'mature': True, 'reachable': True}]
                self.assertEqual(controller.choose(o, 'industrialise')['kind'], 'idle')

    def test_owned_wheat_can_be_crafted_from_cover_without_spending_it_twice(self):
        o = frame()
        o.update(food=2, health=3, night=True, sheltered=True)
        o['inventory'] = [
            {'slot': 0, 'item': 'minecraft:wheat', 'count': 2},
            {'slot': 4, 'item': 'minecraft:wheat', 'count': 1},
        ]
        o['workstations'] = [{'pos': [1, 64, 0], 'block': 'minecraft:crafting_table', 'reachable': True}]
        self.assertEqual(controller.choose(o, 'industrialise'), {
            'kind': 'craft', 'width': 3, 'height': 1,
            'slots': [0, 0, 4], 'output': 'minecraft:bread'})
        o['inventory'][-1]['count'] = 0
        self.assertEqual(controller.choose(o, 'industrialise')['kind'], 'idle')

    def test_bread_requires_adapter_reachable_table_and_nonfailed_recipe(self):
        for absent in ('adapter', 'table', 'recipe'):
            with self.subTest(absent=absent):
                o = frame()
                o['food'] = 3
                o['inventory'] = [{'slot': 0, 'item': 'minecraft:wheat', 'count': 3}]
                o['workstations'] = [{'pos': [1, 64, 0], 'block': 'minecraft:crafting_table', 'reachable': True}]
                if absent == 'adapter':
                    o['capabilities'] = []
                elif absent == 'table':
                    o['workstations'][0]['reachable'] = False
                else:
                    o['_failed_recipes'] = ['minecraft:bread']
                self.assertEqual(controller.choose(o, 'industrialise')['kind'], 'idle')

    def test_food_gathering_keeps_stop_follow_and_danger_priority(self):
        o = frame()
        o['food'] = 3
        o['blocks'] = [{'pos': [2, 64, 0], 'block': 'minecraft:carrots', 'mature': True, 'reachable': True}]
        o['humans'] = [{'name': 'Jamie_Syn', 'position': [-3.5, 64, .5]}]
        self.assertEqual(controller.choose(o, 'rest')['kind'], 'idle')
        self.assertEqual(controller.choose(o, 'follow')['target'], [-.5, 64, .5])
        o['entities'] = [{'id': 9, 'type': 'minecraft:zombie', 'hostile': True, 'position': [2.5, 64, .5]}]
        action = controller.choose(o, 'industrialise')
        self.assertEqual(action['kind'], 'move')
        self.assertLess(action['target'][0], o['position'][0])
        o['entities'] = []
        o.update(night=True, sheltered=True)
        self.assertEqual(controller.choose(o, 'industrialise')['kind'], 'idle')

    def test_stop_and_follow_do_not_start_bread_crafting(self):
        o = frame()
        o['inventory'] = [{'slot': 0, 'item': 'minecraft:wheat', 'count': 3}]
        o['workstations'] = [{'pos': [1, 64, 0], 'block': 'minecraft:crafting_table', 'reachable': True}]
        o['humans'] = [{'name': 'Jamie_Syn', 'position': [-3.5, 64, .5]}]
        self.assertEqual(controller.choose(o, 'rest')['kind'], 'idle')
        self.assertEqual(controller.choose(o, 'follow')['kind'], 'move')

    def test_old_work_detour_cannot_override_food_survival(self):
        o = frame()
        c = object.__new__(controller.Controller)
        for action in (
            {'kind': 'eat'}, {'kind': 'drink'},
            {'kind': 'mine', 'pos': [2, 64, 0], 'food_target': [2, 64, 0]},
            {'kind': 'craft', 'output': 'minecraft:bread'},
        ):
            with self.subTest(action=action):
                c.skills = {'Syn_Test': {'detour': {'target': [6, 64, 0], 'until': 108}}}
                self.assertEqual(c.recover_route(o, action, 'industrialise', 100), action)
                self.assertNotIn('detour', c.skills['Syn_Test'])
        o['food'] = 2
        c.skills = {'Syn_Test': {'detour': {'target': [6, 64, 0], 'until': 108}}}
        action = controller.choose(o, 'industrialise')
        self.assertEqual(action['kind'], 'idle')
        self.assertEqual(c.recover_route(o, action, 'industrialise', 100), action)


if __name__ == '__main__':
    unittest.main()
