import asyncio
import json
from connection_diagnostics import ConnectionDiagnostics

async def run():
    events=[]
    messages=[]
    mode='normal'
    async def app(scope, receive, send):
        if scope['type']=='http':
            await send({'type':'http.response.start','status':401,'headers':[]})
            return
        await send({'type':'websocket.accept'})
        if mode=='denied':
            await send({'type':'websocket.close','code':4401})
            return
        await send({'type':'websocket.send','text':json.dumps({'type':'state','state':{
            'hand':{'id':'private-hand','phase':'flop','action_seat':2,'cards':['As','Ad']},
            'legal':{'can_act':True},'secret':'never-log'}})})
        await receive()
        await receive()
        if mode=='error':
            raise RuntimeError('secret exception message')
    middleware=ConnectionDiagnostics(app)
    middleware.emit=lambda event,**kw:events.append(dict(event=event,**kw))
    async def send(message): messages.append(message)
    async def receive():
        return queue.pop(0)
    scope={'type':'websocket','path':'/ws/tables/private-table','headers':[(b'cookie',b'secret-cookie')]}
    for _ in range(2):
        queue=[{'type':'websocket.receive','text':'ping'}, {'type':'websocket.disconnect','code':1006}]
        await middleware(scope,receive,send)
    assert events[4]['previous_connection_id']==events[0]['connection_id']
    assert events[2]['event']=='ws_first_state'
    ends=[e for e in events if e['event']=='ws_end']
    assert ends[0]['code']==1006 and ends[0]['last_delivered_state']['can_act']
    assert ends[0]['last_ping_age_ms'] is not None
    mode='denied'
    await middleware(scope,receive,send)
    assert events[-1]['code']==4401 and events[-1]['last_state_age_ms'] is None
    mode='error'
    queue=[{'type':'websocket.receive','text':'ping'}, {'type':'websocket.disconnect','code':1006}]
    try: await middleware(scope,receive,send)
    except RuntimeError: pass
    else: raise AssertionError('exception swallowed')
    assert events[-1]['error']=='RuntimeError'
    await middleware({'type':'http','path':'/api/quiz/question','headers':[
        (b'x-jj-quiz-source',b'browser-call-3'),(b'user-agent',b'Mozilla/5.0'),
        (b'authorization',b'secret-bearer')]},receive,send)
    assert events[-1]['source']=='browser-call-3' and events[-1]['status']==401
    await middleware({'type':'http','method':'POST','path':'/api/tables/private-table/action',
                      'headers':[(b'cookie',b'secret-cookie')]},receive,send)
    assert events[-1]['event']=='table_http' and events[-1]['operation']=='action'
    assert events[-1]['table_ref']==events[0]['table_ref']
    assert events[-1]['session_ref']==events[0]['session_ref']
    await middleware({'type':'http','method':'GET','path':'/api/tables/private-table',
                      'headers':[(b'cookie',b'secret-cookie')]},receive,send)
    assert events[-1]['operation']=='state_fetch'
    logged=json.dumps(events)
    for secret in ('secret-cookie','secret-bearer','private-hand','private-table','never-log','secret exception','As','Ad'):
        assert secret not in logged,secret
    print('CONNECTION_DIAGNOSTICS_OK')

if __name__=='__main__': asyncio.run(run())
