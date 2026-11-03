"""Bounded full-component retrieval, including Unicode splits and stale stack protection."""
import base64
import hashlib
import json
import unittest
import test_controller_gateway as fixtures


class InventoryQueryTests(unittest.TestCase):
    def test_gateway_bounds_session_and_tick_fields(self):
        fixture=fixtures.GatewayTests();fixture.setUp()
        try:
            sample=fixtures.frame(tick=102)
            sample.update(body_epoch='epoch',world_tick=4567,average_tick_ms=12.3,control_protocol=2,
                          raw_capabilities=['query_inventory','query_recipe'],action_results=[])
            fixture.g.frame(sample);fixture.lease()
            self.assertEqual(4567,fixture.g.frames['Forge']['world_tick'])
            self.assertEqual(12.3,fixture.g.frames['Forge']['average_tick_ms'])
            index=0
            def submit(**fields):
                nonlocal index
                index+=1
                return fixture.call('POST','/v1/actions',dict(id='inventory_query_'+str(index),op='query_inventory',body_epoch='epoch',**fields))
            submit(slot=-1,offset=0,limit=16384)
            with fixture.g.changed:grant=fixture.g.realtime_control('Forge')
            self.assertEqual('player',grant['commands'][0]['inventory'])
            fixture.error(400,lambda:submit(slot=0,offset=1))
            fixture.error(400,lambda:submit(slot=41))
            fixture.error(400,lambda:submit(slot=0,limit=16385))
            fixture.error(400,lambda:submit(slot=0,inventory='container'))
            submit(slot=0,offset=2,stack_revision='a'*64)
            submit(slot=1,inventory='container',session_id='session',revision=2)
        finally:fixture.tearDown()

    def reader(self):
        value={'minecraft:custom_name':'A \U0001f600 pickaxe','mod:structured':{'nested':[1,2,3]}}
        # Use real multibyte UTF-8, intentionally fragmented into three-byte pages.
        value['minecraft:custom_name']='a'*(16382-len('{"minecraft:custom_name": "'.encode()))+chr(0x1f600)+' pickaxe'
        data=json.dumps(value,ensure_ascii=False).encode('utf-8')
        fingerprint=hashlib.sha256(b'minecraft:diamond_pickaxe\0' + b'1\0' + data).hexdigest()
        class Handle(dict):
            def result(self,timeout):return self.page
        class Reader(fixtures.sdk.PrimitiveMethods):
            def __init__(self):self.offsets=[];self.change_revision=False;self.change_epoch=False;self.bad_offset=False;self.bad_checksum=False;self.empty_chunk=False
            def query_inventory(self,slot,**kw):
                offset=kw['offset'];self.offsets.append(offset)
                if offset:self.expected_revision=kw['stack_revision']
                chunk=data[offset:offset+16384] if not self.empty_chunk else b''
                revision=('b'*64 if (offset and self.change_revision) or self.bad_checksum else fingerprint)
                page=dict(inventory='player',slot=slot,offset=offset,components_encoding='utf-8/base64',
                          total_bytes=len(data),stack_revision=revision,
                          stack={'item':'minecraft:diamond_pickaxe','count':1},components_chunk=base64.b64encode(chunk).decode())
                if offset+len(chunk)<len(data):page['next_offset']=offset+len(chunk)+(1 if self.bad_offset else 0)
                handle=Handle(body_epoch='other' if offset and self.change_epoch else 'epoch');handle.page=page
                return handle
        return Reader(),value,fingerprint

    def test_full_unicode_components_and_verified_checksum(self):
        reader,value,fingerprint=self.reader();result=reader.inventory_slot(0)
        self.assertEqual(value,result['components']);self.assertGreater(len(reader.offsets),1)
        self.assertEqual(fingerprint,reader.expected_revision)
        self.assertEqual(fingerprint,result['stack_revision'])

    def test_stale_body_or_stack_never_combines_pages(self):
        reader,_,_=self.reader();reader.change_revision=True
        with self.assertRaisesRegex(ValueError,'Stack or recipe changed'):reader.inventory_slot(0)
        reader,_,_=self.reader();reader.change_epoch=True
        with self.assertRaisesRegex(ValueError,'Body changed'):reader.inventory_slot(0)

    def test_pagination_and_byte_limits_fail_explicitly(self):
        reader,_,_=self.reader()
        with self.assertRaisesRegex(ValueError,'oversized'):reader.inventory_slot(0,max_bytes=1)
        for attr in ('bad_offset','empty_chunk'):
            reader,_,_=self.reader();setattr(reader,attr,True)
            with self.assertRaisesRegex(ValueError,'continuation'):reader.inventory_slot(0)
            self.assertEqual(1,len(reader.offsets))
        reader,_,_=self.reader();reader.bad_checksum=True
        with self.assertRaisesRegex(ValueError,'checksum'):reader.inventory_slot(0)
        with self.assertRaises(ValueError):reader.inventory_slot(0,timeout=0)

    def test_recipe_pages_preserve_descriptor_and_verify_hash(self):
        descriptor={'recipe_id':'minecraft:large_recipe','ingredients':[{'description':'x'*18000}]}
        encoded=json.dumps(descriptor).encode();revision=hashlib.sha256(encoded).hexdigest()
        class Handle(dict):
            def result(self,timeout):return self.page
        class Reader(fixtures.sdk.PrimitiveMethods):
            def __init__(self):self.bad=False;self.calls=[]
            def query_recipe(self,recipe_id,*,offset,recipe_revision):
                self.calls.append((offset,recipe_revision))
                data=encoded[offset:offset+16384]
                page=dict(recipe_id=recipe_id,offset=offset,total_bytes=len(encoded),encoding='utf-8/base64',
                          recipe_revision='b'*64 if self.bad else revision,recipe_chunk=base64.b64encode(data).decode())
                if offset+len(data)<len(encoded):page['next_offset']=offset+len(data)
                handle=Handle(body_epoch='epoch');handle.page=page;return handle
        reader=Reader();self.assertEqual(descriptor,reader.recipe('minecraft:large_recipe'))
        self.assertEqual([(0,None),(16384,revision)],reader.calls)
        reader.bad=True
        with self.assertRaisesRegex(ValueError,'checksum'):reader.recipe('minecraft:large_recipe')

    def test_recipe_request_validation_and_wrapper(self):
        fixture=fixtures.GatewayTests();fixture.setUp()
        try:
            sample=fixtures.frame(tick=102)
            sample.update(body_epoch='epoch',control_protocol=2,raw_capabilities=['query_recipe'],action_results=[])
            fixture.g.frame(sample);fixture.lease()
            base=dict(id='recipe_query_0001',op='query_recipe',body_epoch='epoch',recipe_id='minecraft:stick',limit=128)
            self.assertEqual('accepted',fixture.call('POST','/v1/actions',base)['state'])
            fixture.error(400,lambda:fixture.call('POST','/v1/actions',dict(base,id='recipe_query_0002',offset=1)))
            fixture.error(400,lambda:fixture.call('POST','/v1/actions',dict(base,id='recipe_query_0002',recipe_id='Bad Recipe')))
            fixture.error(400,lambda:fixture.call('POST','/v1/actions',dict(base,id='recipe_query_0002',limit=16385)))
        finally:fixture.tearDown()
