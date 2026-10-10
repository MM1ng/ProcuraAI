"""B7 real non-stream HTTP contracts; payment uses the isolated native mock."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent import procurement_agent as agent, session_state as sessions
from app.services import order_service, stripe_payment_service, confirmed_transaction as transactions
from app.services.caller_identity import CURRENT_CALLER, COOKIE_NAME, resolve_credential
from main import app


def initialize(client):
    response = client.post('/api/caller/init', headers={'Origin':'http://127.0.0.1:3000'})
    assert response.status_code == 200
    client.headers.update({'Origin':'http://127.0.0.1:3000', 'X-CSRF-Token':response.json()['csrf_token']})
    return resolve_credential(client.cookies.get(COOKIE_NAME))[0]


def binding(plan, sid):
    return {'session_id':sid, 'plan_id':plan['plan_id'], 'plan_hash':plan['plan_hash'], 'plan_version':plan['plan_version']}


def displayed(client):
    sid = client.post('/api/chat/session').json()['session_id']
    response = client.post('/api/chat', json={'session_id':sid, 'message':'Recommend 2 monitors with budget 500'})
    assert response.status_code == 200
    plan = response.json()['recommended_plan']
    assert plan['items'] and plan['plan_hash']
    return sid, plan


@pytest.fixture
def http_ctx(monkeypatch):
    with TestClient(app, base_url='http://127.0.0.1:8000', client=('127.0.0.1',50000)) as client:
        caller = initialize(client)
        current = CURRENT_CALLER.set(caller)
        try:
            sid, plan = displayed(client)
            counts = {'rewrite':0,'retrieval':0,'save_snapshot':0,'new_hash':0,'issue_confirmation':0,'checkout':0}
            def watch(target, name, counter):
                original = getattr(target,name)
                def observed(*args,**kwargs):
                    counts[counter] += 1
                    return original(*args,**kwargs)
                monkeypatch.setattr(target,name,observed)
            for target,name,counter in ((agent,'rewrite_query','rewrite'),(agent,'_retrieve_products_for_agent','retrieval'),
                (agent,'save_session_state','save_snapshot'),(agent,'with_plan_snapshot','new_hash'),
                (transactions,'issue_confirmation','issue_confirmation'),
                (agent,'create_checkout_for_selected_plan','checkout')):
                watch(target,name,counter)
            if hasattr(agent,'issue_confirmation'):
                watch(agent,'issue_confirmation','issue_confirmation')
            yield SimpleNamespace(client=client, caller=caller, sid=sid, plan=plan, counts=counts)
        finally:
            CURRENT_CALLER.reset(current)


def sign(ctx, plan=None, sid=None, client=None):
    response = (client or ctx.client).post('/api/chat/confirm',json=binding(plan or ctx.plan,sid or ctx.sid))
    assert response.status_code == 200
    return response.json()['confirmation_id']


def create(ctx, token, client=None, plan=None, sid=None):
    response = (client or ctx.client).post('/api/orders',json={**binding(plan or ctx.plan,sid or ctx.sid),
        'confirmation_id':token,'plan':plan or ctx.plan})
    assert response.status_code == 200
    return response.json()


def foreign_order(ctx):
    with TestClient(app,base_url='http://127.0.0.1:8000',client=('127.0.0.1',50001)) as other:
        other_caller=initialize(other)
        current=CURRENT_CALLER.set(other_caller)
        try:
            sid,plan=displayed(other)
            token=sign(ctx,plan,sid,other)
            return create(ctx,token,other,plan,sid),token
        finally:
            CURRENT_CALLER.reset(current)


def chat(ctx, message, token=None, payload=None):
    before_state = deepcopy(sessions.get_session_state(ctx.sid))
    before_orders = deepcopy(order_service.list_orders())
    before_counts = ctx.counts.copy()
    data = {'message':message, **binding(ctx.plan,ctx.sid)}
    if token is not None:
        data['confirmation_id'] = token
    data.update(payload or {})
    response = ctx.client.post('/api/chat',json=data,headers={'Accept':'application/json'})
    result = response.json()
    observed = {key:value-before_counts[key] for key,value in ctx.counts.items()}
    record = {'message':message,'http_status':response.status_code,'type':result.get('type'),
        'error_code':result.get('error_code'),'snapshot_drift':result.get('snapshot_drift'),
        'order_delta':len(order_service.list_orders())-len(before_orders),
        'snapshot_unchanged':sessions.get_session_state(ctx.sid)==before_state,
        'orders_unchanged':order_service.list_orders()==before_orders,
        'order_returned':bool(result.get('order_id')),'checkout_returned':bool(result.get('checkout_url')),
        'observed':observed}
    # Under the batch runner cwd is the new RUN; no credential or token is logged.
    with (Path.cwd() / 'http-chat-results.jsonl').open('a',encoding='utf-8') as output:
        output.write(json.dumps(record,ensure_ascii=False)+'\n')
    assert response.status_code == 200
    assert observed['rewrite']==observed['retrieval']==observed['save_snapshot']==observed['new_hash']==0
    assert observed['issue_confirmation']==0
    assert record['snapshot_unchanged']
    return result,record


def blocked(result, record):
    assert result.get('order_id') is None and result.get('checkout_url') is None
    assert record['order_delta']==0 and record['orders_unchanged']
    assert record['observed']['checkout']==0


@pytest.mark.parametrize('token_mode',['missing','unissued','foreign','expired'])
def test_http_confirm_requires_prior_bound_confirmation(http_ctx, token_mode):
    ctx=http_ctx
    token=None if token_mode=='missing' else 'unissued-token'
    if token_mode=='foreign':
        with TestClient(app,base_url='http://127.0.0.1:8000',client=('127.0.0.1',50001)) as other:
            other_caller=initialize(other)
            current=CURRENT_CALLER.set(other_caller)
            try:
                sid,plan=displayed(other)
                token=sign(ctx,plan,sid,other)
            finally:
                CURRENT_CALLER.reset(current)
    if token_mode=='expired':
        token=sign(ctx)
        sessions._SESSIONS[ctx.sid]['recommended_plan']['created_at']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    result,record=chat(ctx,'确认这个方案并下单',token)
    blocked(result,record)
    assert result['error_code']=='PLAN_SNAPSHOT_INVALID'


@pytest.mark.parametrize('field,value',[('plan_id',None),('plan_id','wrong'),('plan_hash',None),('plan_hash','wrong'),
    ('plan_version',None),('plan_version',999)])
def test_http_presigned_token_still_requires_exact_snapshot(http_ctx,field,value):
    ctx=http_ctx
    result,record=chat(ctx,'确认这个方案并下单',sign(ctx),{field:value})
    blocked(result,record)
    assert result['error_code']=='PLAN_SNAPSHOT_INVALID'


def test_http_presigned_confirm_is_idempotent_and_existing_order_can_pay(http_ctx):
    ctx=http_ctx
    token=sign(ctx)
    first,record=chat(ctx,'确认这个方案并下单',token)
    assert first['order_id'] and first['checkout_url'] is None and record['order_delta']==1
    retry,record=chat(ctx,'确认这个方案并下单',token)
    assert retry['order_id']==first['order_id'] and record['order_delta']==0
    paid,record=chat(ctx,'Pay now',token)
    assert paid['order_id']==first['order_id'] and paid['checkout_url']
    assert record['order_delta']==0 and record['observed']['checkout']==1
    assert len(order_service.list_orders())==1


@pytest.mark.parametrize('message',['Pay now','checkout this order now'])
@pytest.mark.parametrize('has_token',[False,True])
def test_http_payment_never_creates_missing_order(http_ctx,message,has_token):
    ctx=http_ctx
    result,record=chat(ctx,message,sign(ctx) if has_token else None)
    blocked(result,record)


@pytest.mark.parametrize('status',['pending_payment','paid','cancelled','expired'])
@pytest.mark.parametrize('message',['Pay now','checkout this order now'])
def test_http_payment_reuses_only_owned_payable_order(http_ctx,status,message):
    ctx=http_ctx
    token=sign(ctx)
    order=create(ctx,token)
    if status!='pending_payment':
        order_service.update_order(order['order_id'],{'status':status})
    result,record=chat(ctx,message,token)
    assert record['order_delta']==0
    if status=='pending_payment':
        assert result['order_id']==order['order_id'] and result['checkout_url']
        assert record['observed']['checkout']==1
    else:
        blocked(result,record)


@pytest.mark.parametrize('mode',['missing_token','wrong_token','foreign_order','snapshot_expired','concurrent_update',
    'price_drift','stock_drift','delivery_drift'])
def test_http_existing_order_does_not_bypass_binding_or_drift(http_ctx,mode,monkeypatch):
    ctx=http_ctx
    token=sign(ctx)
    order,token=foreign_order(ctx) if mode=='foreign_order' else (create(ctx,token),token)
    if mode=='missing_token': token=None
    if mode=='wrong_token': token='wrong-token'
    if mode=='snapshot_expired':
        sessions._SESSIONS[ctx.sid]['recommended_plan']['created_at']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    if mode=='concurrent_update':
        state=sessions.get_session_state(ctx.sid)
        updated=deepcopy(state['recommended_plan'])
        updated['items'][0]['quantity']+=1
        updated=order_service.create_order_from_plan(updated)['procurement_plan']
        replacement=sessions.save_session_state(ctx.sid,state['parsed_intent'],updated,state['retrieved_products'],'concurrent-update')
        assert replacement['recommended_plan']['plan_version']>ctx.plan['plan_version']
    if mode.endswith('_drift'):
        from app.services import product_service
        original=product_service.load_products_from_csv
        def drifted():
            products=deepcopy(original())
            product=next(p for p in products if p['product_id']==ctx.plan['items'][0]['product_id'])
            field={'price_drift':'price','stock_drift':'stock','delivery_drift':'delivery_days'}[mode]
            product[field]+=1
            return products
        monkeypatch.setattr(product_service,'load_products_from_csv',drifted)
    result,record=chat(ctx,'Pay now',token)
    blocked(result,record)


@pytest.mark.parametrize('mode',['missing','owned','foreign'])
@pytest.mark.parametrize('explicit_reference',[False,True])
def test_http_order_status_short_circuits_without_leaking_or_mutating(http_ctx,mode,explicit_reference):
    ctx=http_ctx
    order=None
    if mode=='owned':
        order=create(ctx,sign(ctx))
    if mode=='foreign':
        order,_=foreign_order(ctx)
    message='查询订单状态'
    if explicit_reference:
        message+=' '+(order['order_id'] if order else 'missing-order-id')
    result,record=chat(ctx,message)
    assert result['type'] in ('order_status','clarify')
    assert record['order_delta']==record['observed']['checkout']==0 and record['orders_unchanged']
    assert result['checkout_url'] is None
    if mode=='owned':
        assert result['order_id']==order['order_id'] and result['order_status']=='pending_payment'
    else:
        assert result['order_id'] is None and result['order_status'] is None
        if order: assert order['order_id'] not in result['answer']


@pytest.mark.parametrize('message',['不要付款','如果便宜就付款','How do I pay?','取消支付','稍后再付款'])
def test_http_payment_safety_counterexamples_keep_order_untouched(http_ctx,message):
    ctx=http_ctx
    token=sign(ctx)
    create(ctx,token)
    # Informational turns may produce a recommendation; only transaction/status
    # turns have a strict no-retrieval contract. Check actual side effects here.
    before=deepcopy(order_service.list_orders())
    checkout_before=ctx.counts['checkout']
    response=ctx.client.post('/api/chat',json={'message':message,**binding(ctx.plan,ctx.sid),'confirmation_id':token})
    assert response.status_code==200
    assert response.json()['order_id'] is None and response.json()['checkout_url'] is None
    assert order_service.list_orders()==before and ctx.counts['checkout']==checkout_before
