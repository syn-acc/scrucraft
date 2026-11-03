"""EXEC-05 / SDK-05: public HTTP/WSS schema and advertised-operation parity."""
import copy
import json
import re
import threading
import unittest
import urllib.error
import urllib.request

import test_controller_gateway as fixtures

try:
    from websockets.sync.client import connect
    AVAILABLE=True
except ImportError:
    AVAILABLE=False


SESSION={'session_id':'fixture-session','revision':0}
VALID={
    'move_to':{'target':[1.5,64,1.5]},'look_at':{'target':[1,65,1]},'stop':{},
    'cancel':{'action_id':'cancel_target_00001'},'select_slot':{'slot':8},'swap_hands':{},
    'drop':{'slot':40,'count':99},'jump':{'enabled':False},'sneak':{'enabled':True},'sprint':{'enabled':False},
    'dig':{'target':[1,64,1]},'place':{'target':[1,64,1],'face':'up','hand':'off'},
    'use_item':{'hand':'main'},'release_use':{},'use_on':{'target':[1,64,1],'face':'east'},
    'attack':{'entity_id':42},'chat':{'text':'Wire parity fixture'},
    'query_blocks':{'target':[1,64,1],'radius':1},'query_recipes':{'offset':0,'limit':64},
    'query_recipe':{'recipe_id':'minecraft:stick'},'query_inventory':{'slot':-1},
    'open_container':{'target':[1,64,1]},
    'move_item':dict(SESSION,**{'from':{'inventory':'player','slot':35},'to':{'inventory':'container','slot':255},'count':64}),
    'close_container':dict(SESSION),'craft':{'recipe_id':'minecraft:stick','count':1},
}
VARIANTS=[
    ('use_on',{'entity_id':42,'hand':'off'}),
    ('query_blocks',{'positions':[[1,64,1],[2,64,2]]}),
    ('query_inventory',dict(SESSION,inventory='container',slot=255)),
    ('open_container',{'target':[1,64,1],'face':'west'}),
    ('query_inventory',{'slot':40,'offset':1,'limit':128,'stack_revision':'a'*64}),
    ('query_recipe',{'recipe_id':'minecraft:stick','offset':1,'limit':128,'recipe_revision':'b'*64}),
    ('craft',{'recipe_id':'minecraft:stick','count':2,'target':[1,64,1]}),
]


@unittest.skipUnless(AVAILABLE,'Install stream dependencies for real HTTP/WSS parity checks')
class ActionWireParityTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.GatewayTests();self.f.setUp();self.g=self.f.g
        self.sample=fixtures.frame(tick=101)
        self.sample.update(body_epoch='epoch',control_protocol=2,raw_capabilities=sorted(fixtures.gateway.PRIMITIVES),action_results=[])
        self.g.frame(self.sample);self.lease=self.f.lease()
        streaming=fixtures.module('action_wire_streaming','agent-gateway/streaming.py')
        self.http=fixtures.gateway.Server(('127.0.0.1',0),self.g)
        self.websocket=streaming.make_server(self.g,port=0)
        self.threads=[threading.Thread(target=server.serve_forever,daemon=True) for server in (self.http,self.websocket)]
        for thread in self.threads:thread.start()
        self.socket=connect('ws://127.0.0.1:'+str(self.websocket.socket.getsockname()[1])+'/v1/events',proxy=None,close_timeout=.2)
        self.socket.send(json.dumps({'token':self.f.token,'agent':'Forge'}));self.sequence=0

    def tearDown(self):
        self.socket.close();self.websocket.shutdown();self.websocket.socket.close();self.http.shutdown();self.http.server_close()
        for thread in self.threads:thread.join(3)
        self.f.tearDown()

    def request(self,transport,value,*,method='POST',path='/v1/actions'):
        with self.g.changed:self.f.now+=.02
        if transport=='http':
            request=urllib.request.Request('http://127.0.0.1:'+str(self.http.server_port)+path,
                data=json.dumps(value).encode(),method=method,headers={**self.f.h,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(request,timeout=2) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        self.sequence+=1;rid='wire_'+str(self.sequence)
        self.socket.send(json.dumps({'request_id':rid,'method':method,'path':path,'lease_id':self.lease['lease_id'],'body':value}))
        while True:
            response=json.loads(self.socket.recv(timeout=2))
            if response.get('request_id')==rid:return response['status'],response.get('result',response)

    def value(self,index,op,fields):return dict(id='wire_action_'+str(index).zfill(8),op=op,body_epoch='epoch',**copy.deepcopy(fields))

    def test_all_advertised_operations_and_variants_accept_identical_wire_contract(self):
        self.assertEqual(set(VALID),fixtures.gateway.PRIMITIVES)
        java=(fixtures.ROOT/'agent-mod/src/main/java/gl/syn/minecraft/PrimitiveControl.java').read_text(encoding='utf-8')
        declaration=re.search(r'CAPABILITIES=List.of\(([^;]+)\)',java).group(1)
        self.assertEqual(set(VALID),set(re.findall(r'"([a-z_]+)"',declaration)),'Native and gateway capability declarations drifted')
        for index,(op,fields) in enumerate(list(VALID.items())+VARIANTS):
            value=self.value(index,op,fields)
            with self.subTest(operation=op,variant=index):
                status,first=self.request('http',value);self.assertEqual(200,status,first)
                status,second=self.request('wss',value);self.assertEqual(200,status,second);self.assertEqual(first,second)
                self.assertEqual('accepted',first['state'])
                control=self.g.actions['Forge'][first['id']]['control']
                for key,expected in fields.items():self.assertEqual(expected,control[key])
        self.assertEqual(32,len(self.g.actions['Forge']),'Exact cross-transport retry must not enqueue twice')

    def test_every_operation_rejects_boolean_ttl_and_unknown_fields_before_acceptance(self):
        for index,(op,fields) in enumerate(VALID.items()):
            for bad,expected in [({'ttl_seconds':True},'invalid_request'),({'unexpected':1},'unknown_action_fields')]:
                value=self.value(index,op,fields);value.update(bad)
                for transport in ('http','wss'):
                    with self.subTest(operation=op,transport=transport,bad=bad):
                        status,response=self.request(transport,value)
                        self.assertEqual((400,expected),(status,response['error']))
        self.assertEqual({},self.g.actions.get('Forge',{}))

    def test_missing_capability_rejects_each_operation_on_both_transports(self):
        self.sample['raw_capabilities']=[];self.g.frame(self.sample)
        for index,(op,fields) in enumerate(VALID.items()):
            value=self.value(index,op,fields)
            for transport in ('http','wss'):
                with self.subTest(operation=op,transport=transport):
                    status,response=self.request(transport,value)
                    self.assertEqual((409,'adapter_upgrade_required'),(status,response['error']))
        self.assertEqual({},self.g.actions.get('Forge',{}))

    def test_typed_union_and_boundary_errors_match_transports(self):
        cases=[('open_container',{'target':[1,64,1],'face':[]} ,'invalid_request'),
               ('use_on',{'target':[1,64,1],'face':'up','entity_id':1},'unknown_action_fields'),
               ('query_blocks',{'positions':[[1,64,1]],'target':[1,64,1],'radius':1},'unknown_action_fields'),
               ('query_inventory',{'slot':0,'offset':1},'invalid_request'),
               ('query_recipe',{'recipe_id':'minecraft:stick','offset':1},'invalid_request'),
               ('craft',{'recipe_id':'minecraft:'+'a'*247,'count':1},'invalid_request'),
               ('dig',{'target':[1.0,64,1]},'block_coordinates_required'),
               ('chat',{'text':'/op player'},'commands_not_supported'),
               ('chat',{'text':'x'*221},'chat_too_long')]
        for index,(op,fields,expected) in enumerate(cases):
            for transport in ('http','wss'):
                with self.subTest(operation=op,transport=transport):
                    status,response=self.request(transport,self.value(index,op,fields))
                    self.assertEqual((400,expected),(status,response['error']))
        for malformed in ('',0,False,[],None):
            for transport in ('http','wss'):
                with self.subTest(result_id=malformed,transport=transport):
                    status,response=self.request(transport,{'action_id':malformed},method='GET',path='/v1/action-results')
                    self.assertEqual((400,'invalid_request'),(status,response['error']))
        self.assertEqual({},self.g.actions.get('Forge',{}))


class SessionWrapperTests(unittest.TestCase):
    def test_result_lookup_does_not_silently_broaden_falsy_ids_to_all_history(self):
        from scru_minecraft.realtime import RealtimeClient
        client=fixtures.sdk.AgentClient('https://example.invalid','synthetic-test-token-1234','Forge')
        stream=RealtimeClient(client);requests=[]
        def request(method,path,body=None):requests.append(body);return {'results':[]}
        client._request=request;stream.request=request
        for interface in (client,stream):
            for invalid in ('',False,0,[]):
                interface.action_results(invalid);self.assertEqual({'action_id':invalid},requests[-1])
            interface.action_results();self.assertIsNone(requests[-1])

    def test_explicit_session_does_not_read_or_substitute_observed_container(self):
        class Client(fixtures.sdk.PrimitiveMethods):
            def observe(self):raise AssertionError('Explicit handle must not cause a fresh container read')
            def action(self,op,**fields):return dict(op=op,**fields)
        client=Client()
        self.assertEqual('old-session',client.close_container(session_id='old-session',revision=12)['session_id'])
        self.assertEqual(12,client.move_item({'inventory':'player','slot':0},{'inventory':'container','slot':0},1,
                                          session_id='old-session',revision=12)['revision'])
        self.assertEqual('east',client.open_container(1,64,1,face='east')['face'])
        self.assertNotIn('face',client.open_container(1,64,1))

    def test_incomplete_old_session_cannot_borrow_new_container_revision(self):
        class Client(fixtures.sdk.PrimitiveMethods):
            def observe(self):return {'container':{'session_id':'new-session','revision':8}}
            def action(self,op,**fields):raise AssertionError('Mismatched session must not submit an action')
        with self.assertRaisesRegex(ValueError,'differs from this session'):
            Client().close_container(session_id='old-session')
