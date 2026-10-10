"""U1 budget/summary tests: deterministic provider JSON, never a live LLM."""
from copy import deepcopy
import json

import pytest
from caller_test_support_m1 import direct_agent_context
from test_chat_language import CHAT_MESSAGE_ZH
from test_recommendation_context_m2 import observed_calls, assert_no_transaction
from app.agent import intent_parser as parser, procurement_agent as agent, session_state
from app.observability import local_tracer
from app.services import product_service

FOLLOWUP='人数改为10人，其他品类和要求保持不变。'
PREVIOUS={'people_count':20,'budget':3000,'categories':['Keyboard','Mouse','Headset'],
    'quantity_by_category':{'Keyboard':20,'Mouse':20,'Headset':20},'min_rating':4.2,'max_delivery_days':5}
POSITIVE=[FOLLOWUP,'请把人数改成10人，其余要求不变。',
    '仅将人数调整为10人，其他条件保持不变。','人数改为10人，其它品类及要求不变。']
NEGATIVE=[
    '人数改为10人。','人数改为10人，其他品类不变。',
    '推荐几款耳机','换个话题，推荐耳机，其他要求不变。',
    '他说“人数改为10人，其他品类和要求保持不变。”',
    '假设人数改为10人，其他品类和要求保持不变。',
    '如果人数改为10人，其他品类和要求保持不变。',
    '不要把人数改为10人，其他品类和要求保持不变。',
    '人数改为10人，其他品类和要求保持不变吗？',
    '“人数改为10人，其他品类和要求保持不变。”是什么意思？',
]

def record(tmp_path,name,value):
    (tmp_path/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def simulated_provider(monkeypatch,payload):
    monkeypatch.setattr(parser,'safe_llm_invoke',lambda prompt,purpose:dict(
        content=json.dumps(payload),used_mock_llm=False,model_provider='U1_PROVIDER_JSON_STUB',
        model_name='DETERMINISTIC_TEST_DOUBLE_NOT_LIVE_LLM',error=None,latency_ms=0))

@pytest.mark.parametrize('message',POSITIVE,ids=['exact-repro','qiyu','only-people','qita-pinlei'])
def test_rules_explicit_people_change_keeps_budget(message,tmp_path):
    previous=deepcopy(PREVIOUS)
    intent=parser.parse_purchase_request(message,previous)
    record(tmp_path,'budget',{'input':message,'actual':intent,'path':'RULES_MOCK_LLM'})
    assert intent['budget']==3000
    assert intent['budget_source']=='inherited'
    assert intent['constraint_sources']['budget']=='inherited'
    assert previous==PREVIOUS

@pytest.mark.parametrize('message',NEGATIVE,ids=['omission','category-only','new-topic','new-topic-rest',
    'quote','hypothesis','conditional','negation','question','quoted-question'])
def test_rules_omission_or_nonassertion_does_not_inherit(message,tmp_path):
    intent=parser.parse_purchase_request(message,deepcopy(PREVIOUS))
    record(tmp_path,'budget',{'input':message,'actual':intent,'path':'RULES_MOCK_LLM'})
    assert intent['budget'] is None
    assert intent['budget_source']=='none'

@pytest.mark.parametrize('model_budget',[None,3000,1500],ids=['null','old-value','wrong-new-value'])
def test_provider_json_cannot_override_explicit_keep(model_budget,monkeypatch,tmp_path):
    payload={'people_count':10,'budget':model_budget,'categories':['Keyboard','Mouse','Headset'],
        'quantity_per_category':{'Keyboard':10,'Mouse':10,'Headset':10},'min_rating':4.2,'max_delivery_days':5}
    simulated_provider(monkeypatch,payload)
    intent=parser.parse_purchase_request(FOLLOWUP,deepcopy(PREVIOUS))
    record(tmp_path,'budget',{'provider_json':payload,'actual':intent,'path':'DETERMINISTIC_PROVIDER_JSON_NOT_LIVE_LLM'})
    assert intent['used_llm_parser'] is True
    assert intent['budget']==3000
    assert intent['budget_source']=='inherited'
    assert intent['constraint_sources']['budget']=='inherited'

@pytest.mark.parametrize('message',NEGATIVE,ids=['omission','category-only','new-topic','new-topic-rest',
    'quote','hypothesis','conditional','negation','question','quoted-question'])
@pytest.mark.parametrize('model_budget',[None,3000],ids=['null','invented-old-budget'])
def test_provider_json_does_not_invent_budget_on_omission_or_nonassertion(message,model_budget,monkeypatch,tmp_path):
    payload={'people_count':10,'budget':model_budget,'categories':['Keyboard']}
    simulated_provider(monkeypatch,payload)
    intent=parser.parse_purchase_request(message,deepcopy(PREVIOUS))
    record(tmp_path,'budget',{'input':message,'provider_json':payload,'actual':intent,
        'path':'DETERMINISTIC_PROVIDER_JSON_NOT_LIVE_LLM'})
    assert intent['budget'] is None
    assert intent['budget_source']=='none'
    assert intent['constraint_sources']['budget']=='none'

@pytest.mark.parametrize(('message','budget','source'),[
    ('人数改为10人，无预算限制，其他要求不变。',None,'explicit'),
    ('人数改为10人，预算不限，其他要求保持不变。',None,'explicit'),
    ('人数改为10人，预算1500美元，其他要求不变。',1500,'explicit'),
    ('人数改为10人，无预算限制，预算1500美元，其他要求不变。',None,'explicit'),
],ids=['remove','unlimited','new-amount','remove-over-new-amount'])
@pytest.mark.parametrize('provider',[False,True],ids=['rules','provider-json'])
def test_budget_precedence_preserves_explicit_contract(message,budget,source,provider,monkeypatch,tmp_path):
    if provider:
        simulated_provider(monkeypatch,{'budget':999,'categories':['Keyboard'],'people_count':10})
    intent=parser.parse_purchase_request(message,deepcopy(PREVIOUS))
    record(tmp_path,'budget',{'input':message,'actual':intent,'provider_json_stub':provider})
    assert intent['budget']==budget
    assert intent['budget_source']==source
    assert intent['constraint_sources']['budget']==source

@pytest.mark.parametrize('previous',[None,{'budget':None}],ids=['new-context','no-prior-budget'])
@pytest.mark.parametrize('provider',[False,True],ids=['rules','provider-json'])
def test_explicit_keep_without_prior_budget_cannot_invent(previous,provider,monkeypatch,tmp_path):
    if provider:
        simulated_provider(monkeypatch,{'budget':3000,'people_count':10,'categories':['Keyboard']})
    intent=parser.parse_purchase_request(FOLLOWUP,previous)
    record(tmp_path,'budget',{'actual':intent,'previous':previous,'provider_json_stub':provider})
    assert intent['budget'] is None and intent['budget_source']=='none'

def fixture_plan(categories,quantities):
    items=[dict(product_id='u1-'+str(index),name='Fixture '+str(index),category=category,
        quantity=quantity,unit_price=10.0,subtotal=quantity*10.0,delivery_days=2)
        for index,(category,quantity) in enumerate(zip(categories,quantities))]
    plan=dict(items=items,total_amount=sum(i['subtotal'] for i in items),budget_status='within_budget',
        inventory_status='valid',constraint_satisfaction='satisfied',plan_id='u1-formatter-fixture',
        plan_version=1,confirmation_id='u1-formatter-sentinel',session_id='u1-formatter-session')
    plan['plan_hash']=session_state.calculate_plan_hash(plan)
    return plan

@pytest.mark.parametrize(('categories','quantities'),[
    (['Keyboard','Mouse','Headset'],[20,20,20]),(['Keyboard','Mouse','Headset'],[10,10,10]),
    (['Keyboard','Mouse','Headset'],[2,3,5]),(['Keyboard','Keyboard'],[2,3]),
    (['Keyboard','Keyboard','Mouse'],[2,3,4]),(['Keyboard','Mouse','Headset'],[1,1,1]),([],[]),
],ids=['twenty-people','ten-people','unequal','same-category-only','same-category-and-other','each-one','empty'])
@pytest.mark.parametrize('language',['zh','en'])
def test_formatter_counts_lines_and_units_without_mutating_plan(categories,quantities,language,tmp_path):
    plan=fixture_plan(categories,quantities)
    before=deepcopy(plan)
    # people_count deliberately differs: quantity is the source of truth.
    answer=agent._answer_from_plan(plan,language,intent={'people_count':999})
    record(tmp_path,'summary',{'plan':plan,'answer':answer,'language':language})
    line_count,unit_count=len(quantities),sum(quantities)
    if language=='zh':
        assert f'共 {line_count} 条商品明细，合计 {unit_count} 件' in answer
    else:
        assert f'{line_count} product lines, {unit_count} units in total' in answer
    for category in set(categories):
        units=sum(q for c,q in zip(categories,quantities) if c==category)
        assert (f'{category} {units}件' if language=='zh' else f'{category}: {units} units') in answer
    assert f'${plan["total_amount"]:.2f}' in answer
    assert plan==before
    assert session_state.calculate_plan_hash(plan)==plan['plan_hash']

@pytest.mark.parametrize('language',['zh','en'])
def test_formatter_does_not_repair_invalid_quantity(language):
    plan=fixture_plan(['Keyboard'],[2])
    plan['items'][0]['quantity']='invalid'
    before=deepcopy(plan)
    with pytest.raises(ValueError):
        agent._answer_from_plan(plan,language)
    assert plan==before

@pytest.mark.parametrize('model_budget',[None,3000,1500],ids=['null','old-value','wrong-new-value'])
def test_real_http_budget_summary_and_snapshots_with_provider_json_stub(model_budget,monkeypatch,observed_calls,tmp_path):
    supplied=[]
    def provider_json(prompt,purpose):
        assert purpose=='intent_parser'
        first=CHAT_MESSAGE_ZH in prompt
        quantity=20 if first else 10
        payload={'people_count':quantity,'budget':3000 if first else model_budget,
            'categories':['Keyboard','Mouse','Headset'],
            'quantity_per_category':{cat:quantity for cat in ('Keyboard','Mouse','Headset')},
            'min_rating':4.2,'max_delivery_days':5}
        supplied.append(payload)
        return dict(content=json.dumps(payload),used_mock_llm=False,
            model_provider='U1_PROVIDER_JSON_STUB',model_name='NOT_A_LIVE_MODEL',error=None,latency_ms=0)
    monkeypatch.setattr(parser,'safe_llm_invoke',provider_json)
    with direct_agent_context() as context:
        replies=[]
        for message in (CHAT_MESSAGE_ZH,FOLLOWUP):
            response=context.client.post('/api/chat',json={'message':message,'session_id':context.session_id})
            assert response.status_code==200
            replies.append(response.json())
        record(tmp_path,'http-combination',{'path':'DETERMINISTIC_PROVIDER_JSON_NOT_LIVE_LLM',
            'provider_json':supplied,'responses':replies,'real_call_counts':observed_calls,
            'traces':json.loads(local_tracer.TRACE_FILE.read_text(encoding='utf-8'))})
        first,second=replies
        assert first['parsed_intent']['budget']==3000 and first['parsed_intent']['budget_source']=='explicit'
        assert second['parsed_intent']['budget']==3000 and second['parsed_intent']['budget_source']=='inherited'
        assert second['parsed_intent']['constraint_sources']['budget']=='inherited'
        catalog={p['product_id']:p for p in product_service.load_products_from_csv()}
        for body,quantity in zip(replies,(20,10)):
            assert body['parsed_intent']['used_llm_parser'] is True
            assert body['parsed_intent']['model_provider']=='U1_PROVIDER_JSON_STUB'
            assert body['parsed_intent']['people_count']==quantity
            assert body['parsed_intent']['quantity_by_category']=={cat:quantity for cat in ('Keyboard','Mouse','Headset')}
            assert f'共 3 条商品明细，合计 {quantity*3} 件' in body['answer']
            for cat in ('Keyboard','Mouse','Headset'):
                assert f'{cat} {quantity}件' in body['answer']
            assert [option['plan']['total_amount'] for option in body['plan_options']]==[65*quantity,105*quantity,135*quantity]
            for option in body['plan_options']:
                plan=option['plan']
                assert session_state.validate_snapshot_content(plan)==[]
                assert session_state.calculate_plan_hash(plan)==plan['plan_hash']
                assert {item['category'] for item in plan['items']}=={'Keyboard','Mouse','Headset'}
                for item in plan['items']:
                    product=catalog[item['product_id']]
                    assert item['quantity']==quantity and item['unit_price']==product['price']
                    assert item['stock']==product['stock'] and item['delivery_days']==product['delivery_days']
            assert_no_transaction(body,observed_calls)
        state=session_state.get_session_state(context.session_id)
        chosen=second['recommended_plan']
        assert state['recommended_plan']==chosen and state['plan_options']==second['plan_options']
        snapshot,reasons=session_state.validate_plan_snapshot(context.session_id,chosen['plan_id'],chosen['plan_hash'],chosen['plan_version'])
        assert reasons==[] and snapshot==chosen
        assert chosen['plan_version']==first['recommended_plan']['plan_version']+1
        assert chosen['plan_id']!=first['recommended_plan']['plan_id']
        assert observed_calls['parser']==2 and observed_calls['retrieval']==2 and observed_calls['session_save']==2
        record(tmp_path,'http-combination-passed',{'responses':replies,'registered_state':state,
            'provider_json':supplied,'path':'DETERMINISTIC_PROVIDER_JSON_NOT_LIVE_LLM'})

def test_rules_only_other_fields_retention_gap_outside_u1(tmp_path):
    # Keep the already diagnosed broader rule-path failure visible; U1 may
    # change budget only and must not fix categories/rating/delivery/quantity.
    intent=parser.parse_purchase_request(FOLLOWUP,deepcopy(PREVIOUS))
    record(tmp_path,'outside-u1-rules-gap',{'actual':intent,'expected_categories':PREVIOUS['categories'],
        'scope':'OUTSIDE_U1_NOT_REPAIRED','path':'RULES_MOCK_LLM'})
    assert intent['categories']==PREVIOUS['categories']
