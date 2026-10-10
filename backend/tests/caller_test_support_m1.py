"""Explicit M1 identities; no global fixture or identity-success mocks."""
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient
from app.services.caller_identity import CURRENT_CALLER, COOKIE_NAME, resolve_credential
from main import app


@contextmanager
def api_test_context():
    with TestClient(app,base_url='http://127.0.0.1:8000',client=('127.0.0.1',50000)) as client:
        response=client.post('/api/caller/init',headers={'Origin':'http://127.0.0.1:3000'})
        assert response.status_code==200
        client.headers.update({'Origin':'http://127.0.0.1:3000','X-CSRF-Token':response.json()['csrf_token']})
        caller,_=resolve_credential(client.cookies.get(COOKIE_NAME))
        response=client.post('/api/chat/session')
        assert response.status_code==200
        client.session_id=response.json()['session_id']
        yield SimpleNamespace(client=client,caller=caller,session_id=client.session_id)


@contextmanager
def direct_agent_context():
    with api_test_context() as context:
        current=CURRENT_CALLER.set(context.caller)
        try:
            yield context
        finally:
            CURRENT_CALLER.reset(current)


def registered_confirmation(context, recipe):
    """Use a canonical catalog plan and the real pre-signing HTTP entrance."""
    from app.agent import session_state
    from app.services import order_service,product_service
    products=product_service.load_products_from_csv()
    mouse=next(p for p in products if p['category']=='Mouse')
    quantity=recipe['items'][0]['quantity']
    plan=order_service.create_order_from_plan({'items':[{'product_id':mouse['product_id'],'quantity':quantity}]})['procurement_plan']
    plan=session_state.save_session_state(context.session_id,{'categories':['Mouse'],'revision_intent':'new_plan'},
        plan,products,'m1-confirmation-fixture')['recommended_plan']
    response=context.client.post('/api/chat/confirm',json={'session_id':context.session_id,
        'plan_id':plan['plan_id'],'plan_hash':plan['plan_hash'],'plan_version':plan['plan_version']})
    assert response.status_code==200
    return plan,response.json()['confirmation_id']
