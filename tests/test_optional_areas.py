"""Default unrestricted work, with explicit boundaries and account controls intact."""
import unittest
import test_primitive_contract as fixtures


class OptionalAreaTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PrimitiveContractTests()
        self.f.setUp()
        body = self.f.g.body('Forge')
        body['data']['area'] = None
        self.f.g.save(body)

    def tearDown(self):
        self.f.tearDown()

    def test_resource_and_inventory_actions_without_area(self):
        cases = [('dig', dict(target=[20,64,0])),
                 ('place', dict(target=[20,64,0], face='up')),
                 ('open_container', dict(target=[20,64,0])),
                 ('craft', dict(recipe_id='minecraft:stick', count=1)),
                 ('close_container', dict(session_id='session', revision=0)),
                 ('move_item', {'session_id':'session', 'revision':0,
                               'from':{'inventory':'player','slot':0},
                               'to':{'inventory':'container','slot':0}, 'count':1})]
        for op, fields in cases:
            with self.subTest(op=op):
                self.assertEqual('accepted', self.f.submit(op, **fields)['state'])
        self.assertIsNone(self.f.grant()['area'])

    def test_dimension_is_not_restricted_without_area(self):
        self.f.sample.update(tick=102, dimension='minecraft:the_nether')
        self.f.g.frame(self.f.sample)
        self.assertEqual('accepted', self.f.submit('dig', target=[20,64,0])['state'])

    def test_explicit_bounds_still_reject_outside_and_wrong_dimension(self):
        body = self.f.g.body('Forge')
        body['data']['area'] = fixtures.fixtures.AREA
        self.f.g.save(body)
        self.f.f.error(403, lambda: self.f.submit('dig', target=[20,64,0]))
        self.f.sample.update(tick=102, dimension='minecraft:the_nether')
        self.f.g.frame(self.f.sample)
        self.f.f.error(403, lambda: self.f.submit('dig', target=[1,64,0]))

    def test_no_area_does_not_bypass_capability_or_coordinate_validation(self):
        self.f.f.error(400, lambda: self.f.submit('dig', target=[float('nan'),64,0]))
        self.f.sample['raw_capabilities'] = ['look_at']
        self.f.g.frame(self.f.sample)
        self.f.f.error(409, lambda: self.f.submit('dig', target=[20,64,0]))

    def test_no_area_does_not_bypass_whitelist(self):
        self.f.f.members.clear()
        self.f.f.error(403, lambda: self.f.submit('dig', target=[20,64,0]))


if __name__ == '__main__':
    unittest.main()
