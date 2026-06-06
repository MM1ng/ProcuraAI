from app.agent.plan_variants import generate_plan_options


def test_generate_plan_options_returns_cost_balanced_and_premium_choices():
    products = [
        {
            "product_id": "K-LOW",
            "name": "Value Keyboard",
            "category": "Keyboard",
            "brand": "Logitech",
            "price": 20,
            "rating": 4.1,
            "stock": 20,
            "supplier": "Acme",
            "delivery_days": 7,
        },
        {
            "product_id": "K-BAL",
            "name": "Balanced Keyboard",
            "category": "Keyboard",
            "brand": "Dell",
            "price": 35,
            "rating": 4.6,
            "stock": 20,
            "supplier": "Acme",
            "delivery_days": 3,
        },
        {
            "product_id": "K-PRE",
            "name": "Premium Keyboard",
            "category": "Keyboard",
            "brand": "Razer",
            "price": 60,
            "rating": 4.9,
            "stock": 20,
            "supplier": "Acme",
            "delivery_days": 4,
        },
        {
            "product_id": "M-LOW",
            "name": "Value Mouse",
            "category": "Mouse",
            "brand": "Logitech",
            "price": 10,
            "rating": 4.0,
            "stock": 20,
            "supplier": "Acme",
            "delivery_days": 8,
        },
        {
            "product_id": "M-BAL",
            "name": "Balanced Mouse",
            "category": "Mouse",
            "brand": "Dell",
            "price": 22,
            "rating": 4.5,
            "stock": 20,
            "supplier": "Acme",
            "delivery_days": 2,
        },
        {
            "product_id": "M-PRE",
            "name": "Premium Mouse",
            "category": "Mouse",
            "brand": "Razer",
            "price": 45,
            "rating": 4.9,
            "stock": 20,
            "supplier": "Acme",
            "delivery_days": 5,
        },
    ]
    intent = {
        "people_count": 5,
        "categories": ["Keyboard", "Mouse"],
        "quantity_by_category": {"Keyboard": 5, "Mouse": 5},
        "budget": 500,
    }

    options = generate_plan_options(products, intent)

    assert [option["id"] for option in options] == ["plan_a", "plan_b", "plan_c"]
    assert [option["name"] for option in options] == ["Plan A", "Plan B", "Plan C"]
    assert [option["strategy"] for option in options] == ["cost_optimized", "balanced", "premium"]
    assert options[0]["plan"]["total_amount"] == 150
    assert options[1]["plan"]["total_amount"] == 285
    assert options[2]["plan"]["total_amount"] == 525
    assert options[0]["plan"]["items"][0]["product_id"] == "K-LOW"
    assert options[1]["plan"]["items"][0]["product_id"] == "K-BAL"
    assert options[2]["plan"]["items"][0]["product_id"] == "K-PRE"


def test_generate_plan_options_omits_strategies_without_matching_products():
    products = [
        {
            "product_id": "K-1",
            "name": "Keyboard",
            "category": "Keyboard",
            "brand": "Dell",
            "price": 35,
            "rating": 4.6,
            "stock": 20,
            "supplier": "Acme",
            "delivery_days": 3,
        }
    ]
    intent = {
        "people_count": 5,
        "categories": ["Keyboard", "Mouse"],
        "quantity_by_category": {"Keyboard": 5, "Mouse": 5},
    }

    options = generate_plan_options(products, intent)

    assert options == []
