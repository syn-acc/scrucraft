"""Bidirectional public controls and a separate authenticated, loopback-only body bridge."""
import hmac
import json
import pathlib
import re
import threading
import time
import logging
from websockets.sync.server import serve
from websockets.protocol import State
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK


def make_server(gateway, host='127.0.0.1', port=8769):
    public_slots=threading.BoundedSemaphore(24)
    body_slots=threading.BoundedSemaphore(10)

    def close_error(connection, surface, phase, error):
        """Only static exception types and gateway error codes; never exception text or request data."""
        if isinstance(error,ConnectionClosedOK):return
        kind=type(error).__name__
        code=getattr(error,'__dict__',{}).get('code')
        safe_code=code if isinstance(code,str) and re.fullmatch(r'[a-z_]{1,60}',code) else None
        ws_code=error.rcvd.code if isinstance(error,ConnectionClosed) and error.rcvd is not None else None
        reason='stream_error_'+kind+('_'+safe_code if safe_code else '')
        logging.getLogger('scru.streaming').warning('stream_closed surface=%s phase=%s exception=%s code=%s ws_code=%s',surface,phase,kind,safe_code,ws_code)
        connection.close(1008 if getattr(error,'status',500)<500 else 1011,reason[:120])

    def body_stream(connection,auth):
        secret=pathlib.Path(gateway.settings()['internal_token_file']).read_text().strip()
        if not isinstance(auth.get('token'),str) or not hmac.compare_digest(auth['token'],secret):
            connection.close(1008,'unauthorized');return
        name=auth.get('agent');epoch=auth.get('body_epoch')
        if not isinstance(epoch,str) or not 1<=len(epoch)<=80:raise ValueError('invalid_epoch')
        with gateway.changed:
            gateway.body(name)
            if name in gateway.body_connections:
                raise ValueError('body_already_connected')
            gateway.body_connections[name]=connection
        ended=threading.Event()
        def receive():
            try:
                for message in connection:
                    value=json.loads(message)
                    if not isinstance(value,dict) or value.get('agent')!=name or value.get('body_epoch')!=epoch:
                        break
                    with gateway.changed:
                        gateway.frame(value)
            except Exception as error:
                close_error(connection,'body','receive',error)
            finally:
                ended.set()
                with gateway.changed:gateway.changed.notify_all()
        reader=threading.Thread(target=receive,daemon=True);reader.start()
        previous_payload=None;renew_at=0
        try:
            while not ended.is_set() and connection.state is State.OPEN:
                with gateway.changed:
                    revision=gateway.body_revisions.get(name,0)
                    try:reply=gateway.realtime_control(name)
                    except Exception:reply={'kind':'idle','body_epoch':epoch,'valid_for_ticks':4}
                    if reply.get('body_epoch')!=epoch:
                        reply={'kind':'idle','body_epoch':epoch,'valid_for_ticks':4}
                payload=json.dumps({'type':'control','action':reply})
                if payload!=previous_payload or time.monotonic()>=renew_at:
                    connection.send(payload)
                    previous_payload=payload;renew_at=time.monotonic()+.1
                with gateway.changed:
                    gateway.changed.wait_for(lambda:ended.is_set() or gateway.body_revisions.get(name,0)!=revision,
                                             timeout=max(0,renew_at-time.monotonic()))
        finally:
            ended.set();connection.close()
            with gateway.changed:gateway.release(name,'body_disconnected')
            with gateway.changed:
                if gateway.body_connections.get(name) is connection:gateway.body_connections.pop(name,None)
            reader.join(timeout=2)

    def player_stream(connection,auth):
        token=auth.get('token');name=auth.get('agent')
        if not isinstance(token,str):raise ValueError('unauthorized')
        with gateway.changed:
            principal=gateway.authenticate('Bearer '+token);gateway.body(name,principal)
        stopped=threading.Event()
        owned_lease=None
        send_lock=threading.Lock()
        def send(value):
            with send_lock:connection.send(json.dumps(value,allow_nan=False))
        def receive():
            nonlocal owned_lease
            try:
                for message in connection:
                    if len(message)>16384:break
                    value=json.loads(message)
                    if not isinstance(value,dict):break
                    rid=value.get('request_id')
                    if not isinstance(rid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',rid):break
                    method,path=value.get('method'),value.get('path')
                    if (method,path) not in {('POST','/v1/actions'),('POST','/v1/lease'),('PUT','/v1/lease'),
                        ('DELETE','/v1/lease'),('DELETE','/v1/goal'),('GET','/v1/action-results')}:
                        send({'type':'response','request_id':rid,'status':404,'error':'unsupported_stream_operation'});continue
                    headers={'Authorization':'Bearer '+token,'X-SCRU-Agent':name,'X-SCRU-Lease':value.get('lease_id','')}
                    started=time.perf_counter_ns()
                    try:
                        with gateway.changed:
                            if stopped.is_set():break
                            result=gateway.handle(method,path,headers,value.get('body',{}))
                            if method=='POST' and path=='/v1/lease':owned_lease=result['lease_id']
                        response={'type':'response','request_id':rid,'status':200,'result':result}
                    except (ValueError,TypeError,KeyError):
                        response={'type':'response','request_id':rid,'status':400,'error':'invalid_request'}
                    except Exception as error:
                        response={'type':'response','request_id':rid,'status':getattr(error,'status',503),
                                  'error':getattr(error,'code','service_unavailable'),'retry_after':getattr(error,'retry',None)}
                    response['gateway_processing_us']=(time.perf_counter_ns()-started)//1000
                    send(response)
            except Exception as error:
                close_error(connection,'player','receive',error)
            finally:
                stopped.set()
                with gateway.changed:gateway.changed.notify_all()
        reader=threading.Thread(target=receive,daemon=True);reader.start()
        previous_id=None;previous_terrain=None;sequence=0
        try:
            while not stopped.is_set() and connection.state is State.OPEN:
                with gateway.changed:
                    revision=gateway.body_revisions.get(name,0)
                    principal=gateway.authenticate('Bearer '+token);body=gateway.body(name,principal)
                    if body['data'].get('removed'):break
                    current=gateway.snapshot(body);frame_id=current['id'];event=None
                    if frame_id!=previous_id:
                        frame=dict(current);frame['action_results']=gateway.compact_results(gateway.result_rows(name))
                        sequence+=1
                        # Terrain is sent initially, then only when a fresh terrain sample arrives.
                        observation=frame if previous_id is None else {k:v for k,v in frame.items() if k not in {'blocks','walkable'}}
                        terrain=frame.get('terrain_captured_at')
                        if terrain!=previous_terrain:observation=frame
                        event={'type':'snapshot','sequence':sequence,'resync':previous_id is None,'observation':observation}
                        previous_id,previous_terrain=frame_id,terrain
                    if event is None:
                        gateway.changed.wait_for(lambda:stopped.is_set() or gateway.body_revisions.get(name,0)!=revision,timeout=.1);continue
                send(event)
                with gateway.changed:
                    gateway.changed.wait_for(lambda:stopped.is_set() or gateway.body_revisions.get(name,0)!=revision,timeout=.1)
        except Exception as error:
            close_error(connection,'player','snapshot',error)
        finally:
            stopped.set()
            with gateway.changed:
                lease=gateway.leases.get(name)
                if lease and lease['id']==owned_lease:
                    gateway.release(name,'stream_disconnected')
            connection.close();reader.join(timeout=2)

    def handler(connection):
        internal=connection.request.path=='/internal/body'
        slots=body_slots if internal else public_slots
        if not slots.acquire(blocking=False):connection.close(1013,'stream_capacity');return
        try:
            if connection.request.path not in {'/v1/events','/internal/body'}:
                connection.close(1008,'not_found');return
            message=connection.recv(timeout=5)
            if len(message)>16384:raise ValueError('authentication_too_large')
            auth=json.loads(message)
            if not isinstance(auth,dict):raise ValueError('authentication_required')
            (body_stream if internal else player_stream)(connection,auth)
        except Exception as error:
            close_error(connection,'body' if internal else 'player','handler',error)
        finally:slots.release()

    return serve(handler,host,port,max_size=1048576,max_queue=4,open_timeout=5,
                 close_timeout=2,ping_interval=10,ping_timeout=10,compression=None,server_header=None)
