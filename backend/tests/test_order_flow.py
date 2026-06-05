from app.services.order_service import create_order_from_plan


def test_create_order_from_plan_returns_pending_payment_order_with_items():
    plan = {
        "items": [
            {
                "product_id": "P-201",
                "name": "Reliable Keyboard",
                "quantity": 5,
                "unit_price": 40.0,
                "subtotal": 200.0,
            },
            {
                "product_id": "P-202",
                "name": "Reliable Mouse",
                "quantity": 5,
                "unit_price": 20.0,
                "subtotal": 100.0,
            },
        ],
        "total_amount": 300.0,
    }

    order = create_order_from_plan(plan=plan, user_id="demo-user")

    assert order["user_id"] == "demo-user"
    assert order["status"] == "pending_payment"
    assert order["total_amount"] == 300.0
    assert len(order["order_items"]) == 2
    assert order["order_items"][0]["subtotal"] == 200.0
