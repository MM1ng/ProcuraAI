"""M3 bounded Chinese people count and actual HTTP canonical plan regression."""
import json

import pytest
from caller_test_support_m1 import direct_agent_context
from test_chat_language import CHAT_MESSAGE_ZH
from test_recommendation_context_m2 import observed_calls, assert_no_transaction, evidence
from app.agent.intent_parser import _extract_people_count, parse_purchase_request
from app.agent import session_state
from app.services import product_service


@pytest.mark.parametrize(('message','expected'),[
    ('请为20名新员工采购键盘',20),
    ('请为20 名新员工采购键盘',20),
    ('请为20名 新员工采购键盘',20),
    ('请为20 名 新员工采购键盘',20),
    ('请为20位新员工采购键盘',20),
    ('请为20位 新员工采购键盘',20),
    ('请为20名新实习生采购键盘',20),
    ('请为20名新用户采购键盘',20),
    ('请为20名员工采购键盘',20),
    ('请为20名实习生采购键盘',20),
    ('请为20员工采购键盘',20),
    ('请为20人采购键盘',20),
    ('请为20名人员采购键盘',20),
    ('请为20名用户采购键盘',20),
    ('请为1名员工采购键盘',1),
    ('We need equipment for 20 interns',20),
    ('Equipment for 10 employees',10),
    ('Equipment for 7 people',7),
    ('A team of 4 needs keyboards',4),
    ('A group of 3 needs keyboards',3),
    ('A department of 2 needs keyboards',2),
],ids=[
    'new-employees','space-before-classifier','space-after-classifier','spaces-around-classifier',
    'wei-new-employees','wei-space-new-employees','new-interns','new-users',
    'legacy-employees','legacy-interns','legacy-no-classifier','legacy-ren',
    'legacy-personnel','legacy-users','legacy-one-person',
    'legacy-english-interns','legacy-english-employees','legacy-english-people',
    'legacy-team','legacy-group','legacy-department',
])
def test_explicit_people_count_in_real_offline_parser(message,expected,tmp_path):
    extracted=_extract_people_count(message)
    intent=parse_purchase_request(message,previous_intent=None)
    (tmp_path/'m3-parser-evidence.json').write_text(json.dumps({'input':message,
        'expected_people_count':expected,'extracted_people_count':extracted,
        'parsed_intent':intent},ensure_ascii=False,indent=2),encoding='utf-8')
    assert extracted==expected
    assert intent['people_count']==expected
    assert intent['used_mock_llm'] is True
    assert all(quantity==expected for quantity in intent['quantity_by_category'].values())


@pytest.mark.parametrize('message',[
    '预算3000美元，新员工需要键盘',
    '预算20美元，新员工需要键盘',
    '预算20元，员工要用新键盘',
    '采购20个新键盘、20个鼠标和20个耳机',
    '预算3000美元，为新员工采购20件键盘和20件耳机',
    '采购20台新员工电脑',
    'Need 20 keyboards and 20 headsets',
    '型号20，新员工要买键盘',
],ids=['budget-3000','budget-20-dollars','budget-20-yuan','product-count-ge',
    'budget-and-product-count','product-count-tai','english-product-count','product-model-number'])
def test_budget_and_product_counts_do_not_become_people(message,tmp_path):
    intent=parse_purchase_request(message,previous_intent=None)
    (tmp_path/'m3-parser-evidence.json').write_text(json.dumps({'input':message,
        'expected_people_count':1,'parsed_intent':intent},ensure_ascii=False,indent=2),encoding='utf-8')
    assert _extract_people_count(message)==1
    assert intent['people_count']==1
    assert intent['used_mock_llm'] is True


def test_chinese_20_new_employees_http_three_canonical_snapshots_without_transactions(observed_calls,tmp_path):
    with direct_agent_context() as context:
        response=context.client.post('/api/chat',json={'message':CHAT_MESSAGE_ZH,'session_id':context.session_id})
        body=response.json()
        # Retain the actual red response before the first assertion can fail.
        evidence(tmp_path,body,observed_calls,scope='M3_PEOPLE_COUNT_CANONICAL_HTTP',phase='before_assertions')
        assert response.status_code==200
        assert body['parsed_intent']['people_count']==20
        assert body['parsed_intent']['quantity_by_category']=={'Keyboard':20,'Mouse':20,'Headset':20}
        assert body['parsed_intent']['budget']==3000
        assert body['parsed_intent']['response_language']=='zh'
        assert [option['id'] for option in body['plan_options']]==['plan_a','plan_b','plan_c']
        assert [option['strategy'] for option in body['plan_options']]==['cost_optimized','balanced','premium']
        assert [option['plan']['total_amount'] for option in body['plan_options']]==[1300,2100,2700]
        assert observed_calls['parser']==1 and observed_calls['retrieval']==1
        assert observed_calls['variants']==1 and observed_calls['session_save']==1
        catalog={product['product_id']:product for product in product_service.load_products_from_csv()}
        state=session_state.get_session_state(context.session_id)
        assert state['plan_options']==body['plan_options']
        plans=[option['plan'] for option in body['plan_options']]
        assert len({plan['plan_id'] for plan in plans})==3
        for plan in plans:
            assert len(plan['items'])==3
            assert {item['category'] for item in plan['items']}=={'Keyboard','Mouse','Headset'}
            assert plan['session_id']==context.session_id
            assert type(plan['plan_version']) is int and plan['plan_version']==1
            assert plan['plan_id'].startswith('plan-'+context.session_id+'-v')
            assert len(plan['plan_hash'])==64
            assert session_state.calculate_plan_hash(plan)==plan['plan_hash']
            assert session_state.validate_snapshot_content(plan)==[]
            assert plan['budget_status']=='within_budget'
            for item in plan['items']:
                product=catalog[item['product_id']]
                assert item['quantity']==20
                assert item['category']==product['category']
                assert item['unit_price']==product['price']
                assert item['subtotal']==round(product['price']*20,2)
                assert item['stock']==product['stock'] and item['stock']>=20
                assert item['delivery_days']==product['delivery_days']
            assert plan['total_amount']==round(sum(item['subtotal'] for item in plan['items']),2)
        chosen=body['recommended_plan']
        assert body['selected_plan_id']==chosen['plan_id']
        assert chosen==next(plan for plan in plans if plan['plan_id']==body['selected_plan_id'])
        snapshot,reasons=session_state.validate_plan_snapshot(context.session_id,chosen['plan_id'],chosen['plan_hash'],chosen['plan_version'])
        assert reasons==[] and snapshot==chosen
        assert_no_transaction(body,observed_calls)
        evidence(tmp_path,body,observed_calls,scope='M3_PEOPLE_COUNT_CANONICAL_HTTP',
            phase='all_assertions_passed',registered_state=state)
