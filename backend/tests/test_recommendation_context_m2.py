"""M2: real offline HTTP recommendations; no replacement catalog/plan results."""
import csv
from functools import wraps
import json
from pathlib import Path

import pytest
from caller_test_support_m1 import direct_agent_context
from test_chat_language import CHAT_MESSAGE, CHAT_MESSAGE_ZH

from app.agent import procurement_agent as agent, session_state
from app.api import chat as chat_api
from app.core import config
from app.observability import local_tracer
from app.services import confirmed_transaction, order_service, product_service
from app.services.caller_identity import resources_for_owner

AMBIGUOUS_FPS = '我喜欢打fps游戏，给我推荐适合我的'


@pytest.fixture
def observed_calls(monkeypatch):
    """Count calls while preserving every real implementation and return value."""
    counts = {}
    def observe(module, name, key):
        original = getattr(module, name)
        counts[key] = 0
        @wraps(original)
        def counted(*args, **kwargs):
            counts[key] += 1
            return original(*args, **kwargs)
        monkeypatch.setattr(module, name, counted)
    for module, name, key in (
        (agent,'parse_purchase_request','parser'),
        (agent,'_retrieve_products_for_agent','retrieval'),
        (agent,'generate_procurement_plan','plan_generation'),
        (agent,'generate_plan_options','variants'),
        (agent,'should_rewrite','rewrite_decision'),
        (agent,'rewrite_query','rewrite'),
        (agent,'save_session_state','session_save'),
        (session_state,'with_plan_snapshot','snapshot'),
        (session_state,'calculate_plan_hash','hash'),
        (agent,'with_plan_snapshot','fallback_snapshot'),
        (agent,'create_confirmed_order','confirmed_order'),
        (agent,'require_confirmed_order_for_payment','payment_order_lookup'),
        (agent,'create_checkout_for_selected_plan','checkout'),
        (order_service,'save_order','order_save'),
        (confirmed_transaction,'issue_confirmation','confirmation_service'),
        (chat_api,'issue_confirmation','confirmation_api'),
    ):
        observe(module,name,key)
    return counts


def trace_for(body):
    traces = json.loads(local_tracer.TRACE_FILE.read_text(encoding='utf-8'))
    return next(row for row in traces if row.get('trace_id')==body['trace_id'] and row.get('decision_source'))


def assert_no_transaction(body, counts):
    assert body['order_id'] is None
    assert body['checkout_url'] is None
    assert body['order_status'] is None
    assert json.loads(order_service.ORDERS_FILE.read_text(encoding='utf-8')) == []
    assert confirmed_transaction._CONFIRMATIONS == {}
    assert resources_for_owner('confirmation') == {}
    assert resources_for_owner('cart_quote') == {}
    for name in ('confirmed_order','payment_order_lookup','checkout','order_save','confirmation_service','confirmation_api'):
        assert counts[name] == 0, (name, counts)


def evidence(tmp_path, body, counts, **extra):
    trace = trace_for(body)
    assert trace['decision_source']=='baseline'
    assert trace['authoritative'] is True
    assert trace['authority_traffic_percent']==0
    assert trace['jev_label'] is None
    assert body['used_mock_llm'] is True
    (tmp_path / 'm2-case-evidence.json').write_text(json.dumps({
        'source':'TASK_SYNTHETIC', 'response':body, 'trace':trace,
        'real_call_counts':counts, 'model_evaluation':'NOT_EXECUTED',
        'browser_acceptance':'NOT_EXECUTED', **extra}, ensure_ascii=False, indent=2), encoding='utf-8')
    return trace


def test_extended_catalog_preserves_original_rows_and_canonical_fields(tmp_path):
    # The runner provides data; this test does not create or replace products.
    run = Path(config.DATA_DIR).parent
    checks = json.loads((run/'catalog-checks.json').read_text(encoding='utf-8'))
    assert checks['catalog_mode']=='extended'
    assert checks['source']=='TASK_SYNTHETIC'
    assert checks['schema_matches'] and checks['unique_ids']
    assert checks['original_rows_preserved_all_fields']
    assert checks['original_count']==4
    with (run/'catalog-before.csv').open(encoding='utf-8',newline='') as source:
        original=list(csv.DictReader(source))
    with (config.DATA_DIR/'products.csv').open(encoding='utf-8',newline='') as source:
        actual=list(csv.DictReader(source))
    assert actual[:len(original)]==original
    for category in ('Keyboard','Headset'):
        rows=[p for p in actual if p['category']==category]
        assert len(rows)>=2
        assert len({p['price'] for p in rows})>=2
        assert len({p['delivery_days'] for p in rows})>=2
        for row in rows:
            assert float(row['price'])>0 and float(row['rating'])>=4.5
            assert int(row['stock'])>=20 and int(row['delivery_days'])<=3
            assert row['supplier']=='Synthetic fixture supplier'
            assert row['compliance_level']=='approved'
            assert all(row[key] for key in checks['schema'])
    (tmp_path/'m2-catalog-evidence.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')


@pytest.mark.parametrize('message',[CHAT_MESSAGE, CHAT_MESSAGE_ZH],ids=['original-english','explicit-chinese-budget'])
def test_real_http_three_plans_have_all_categories_and_server_snapshots(message, observed_calls, tmp_path):
    with direct_agent_context() as context:
        response=context.client.post('/api/chat',json={'message':message,'session_id':context.session_id})
        body=response.json()
        # Preserve the full actual response even when a later business assertion
        # exposes a parser capability gap; never remove or soften that failure.
        evidence(tmp_path,body,observed_calls,assertion_phase='before_three_plan_business_assertions')
        # All assertions from the frozen original comparison test, without weakening.
        assert response.status_code==200
        assert [option['id'] for option in body['plan_options']]==['plan_a','plan_b','plan_c']
        assert [option['strategy'] for option in body['plan_options']]==['cost_optimized','balanced','premium']
        selected_option=next(option for option in body['plan_options'] if option['plan']['plan_id']==body['selected_plan_id'])
        assert body['recommended_plan']==selected_option['plan']
        assert body['recommended_plan']['budget_status'] in ('within_budget','no_budget_provided')
        assert set(body['parsed_intent']['categories'])=={'Keyboard','Mouse','Headset'}
        assert body['parsed_intent']['people_count']==20
        assert observed_calls['parser']==1 and observed_calls['retrieval']==1
        assert observed_calls['variants']==1 and observed_calls['session_save']==1
        catalog={p['product_id']:p for p in product_service.load_products_from_csv()}
        state=session_state.get_session_state(context.session_id)
        assert state['plan_options']==body['plan_options']
        plans=[option['plan'] for option in body['plan_options']]
        assert len({p['plan_id'] for p in plans})==3
        assert len({tuple(i['product_id'] for i in p['items']) for p in plans})==3
        for plan in plans:
            assert plan['plan_id'].startswith('plan-'+context.session_id+'-v')
            assert plan['session_id']==context.session_id
            assert type(plan['plan_version']) is int and plan['plan_version']==1
            assert len(plan['plan_hash'])==64
            assert session_state.calculate_plan_hash(plan)==plan['plan_hash']
            assert session_state.validate_snapshot_content(plan)==[]
            assert len(plan['items'])==3
            assert {i['category'] for i in plan['items']}=={'Keyboard','Mouse','Headset'}
            for item in plan['items']:
                current=catalog[item['product_id']]
                assert item['quantity']==20
                assert item['category']==current['category']
                assert item['unit_price']==current['price']
                assert item['stock']==current['stock'] and item['stock']>=20
                assert item['delivery_days']==current['delivery_days']
                assert item['subtotal']==round(current['price']*20,2)
            assert plan['total_amount']==round(sum(i['subtotal'] for i in plan['items']),2)
            if message==CHAT_MESSAGE_ZH:
                assert plan['total_amount']<=3000
                assert plan['budget_status']=='within_budget'
        chosen=body['recommended_plan']
        snapshot,reasons=session_state.validate_plan_snapshot(context.session_id,chosen['plan_id'],chosen['plan_hash'],chosen['plan_version'])
        assert reasons==[] and snapshot==chosen
        assert_no_transaction(body,observed_calls)
        evidence(tmp_path,body,observed_calls,registered_state=state)


def test_ambiguous_chinese_fps_clarifies_without_retrieval_save_hash_or_transactions(observed_calls,tmp_path):
    with direct_agent_context() as context:
        before=session_state.get_session_state(context.session_id)
        response=context.client.post('/api/chat',json={'message':AMBIGUOUS_FPS,'session_id':context.session_id})
        body=response.json()
        assert response.status_code==200
        assert body['type']=='clarify'
        assert body['parsed_intent']['response_language']=='zh'
        assert '请补充品类、数量' in body['answer']
        assert body['parsed_intent']['categories']==[]
        assert body['parsed_intent']['budget'] is None
        assert body['parsed_intent']['constraints']==[] and body['parsed_intent']['preferences']==[]
        assert body['used_previous_context'] is False
        assert body['retrieved_products']==[] and body['plan_options']==[]
        assert body['selected_plan_id'] is None
        assert not body['recommended_plan'].get('plan_hash')
        assert not body['recommended_plan'].get('plan_version')
        assert not body['recommended_plan']['items']
        assert session_state.get_session_state(context.session_id)==before
        assert observed_calls['parser']==1
        for name in ('retrieval','plan_generation','variants','rewrite_decision','rewrite','session_save','snapshot','hash','fallback_snapshot'):
            assert observed_calls[name]==0,(name,observed_calls)
        assert_no_transaction(body,observed_calls)
        trace=evidence(tmp_path,body,observed_calls,
            spec_semantic_intent='recommend', semantic_intent_source='M2_BOUNDED_SPEC_ADJUDICATION_NOT_HUMAN_GOLD',
            baseline_semantic_intent='NOT_COMPARABLE_FIELD_ABSENT', safe_next_action='clarify',
            side_effect_authorization=False)
        assert trace['mapped_route']=='clarify'
        assert trace['transaction_gate']=='block'
        assert 'semantic_intent' not in trace


@pytest.mark.parametrize(('message','category'),[
    ('我喜欢打FPS游戏，请推荐适合我的鼠标','Mouse'),
    ('Recommend a keyboard for FPS gaming','Keyboard'),
],ids=['chinese-fps-explicit-mouse','english-fps-explicit-keyboard'])
def test_explicit_fps_category_returns_real_matches_without_transactions(message,category,observed_calls,tmp_path):
    with direct_agent_context() as context:
        response=context.client.post('/api/chat',json={'message':message,'session_id':context.session_id})
        body=response.json()
        assert response.status_code==200
        assert category in body['parsed_intent']['categories']
        assert body['type'] in ('product_results','recommendation_plan')
        assert observed_calls['parser']==1 and observed_calls['retrieval']==1
        assert body['retrieved_products']
        catalog={p['product_id']:p for p in product_service.load_products_from_csv()}
        matching=[p for p in body['retrieved_products'] if p['category']==category]
        assert matching
        for product in matching:
            current=catalog[product['product_id']]
            assert product['price']==current['price']
            assert product['stock']==current['stock']
            assert product['delivery_days']==current['delivery_days']
        assert any(p['category']==category for p in (body['products'] or body['recommended_plan']['items']))
        assert_no_transaction(body,observed_calls)
        evidence(tmp_path,body,observed_calls,explicit_category=category)
