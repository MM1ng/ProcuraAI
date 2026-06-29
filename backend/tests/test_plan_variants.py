from app.agent.plan_variants import generate_plan_options
from app.agent.procurement_agent import select_default_plan_option


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
    assert options[0]["plan"]["selectable"] is True
    assert options[1]["plan"]["selectable"] is True
    assert options[2]["plan"]["selectable"] is False
    assert options[2]["plan"]["over_budget"] is True
    assert options[2]["plan"]["budget_gap"] == 25
    assert options[2]["plan"]["status"] == "over_budget"
    assert options[0]["plan"]["items"][0]["product_id"] == "K-LOW"
    assert options[1]["plan"]["items"][0]["product_id"] == "K-BAL"
    assert options[2]["plan"]["items"][0]["product_id"] == "K-PRE"


def test_generate_plan_options_calculates_average_rating_from_selected_items():
    products = [
        {
            "product_id": "K-109",
            "name": "Logitech Team Keyboard 109",
            "category": "Keyboard",
            "brand": "Logitech",
            "price": 25.42,
            "rating": 4.6,
            "stock": 20,
            "supplier": "Northwind",
            "delivery_days": 7,
        },
        {
            "product_id": "M-107",
            "name": "Razer Ultra Mouse 107",
            "category": "Mouse",
            "brand": "Razer",
            "price": 17.94,
            "rating": 4.8,
            "stock": 20,
            "supplier": "Northwind",
            "delivery_days": 1,
        },
        {
            "product_id": "H-115",
            "name": "Sony Ergo Headset 115",
            "category": "Headset",
            "brand": "Sony",
            "price": 40.65,
            "rating": 4.7,
            "stock": 20,
            "supplier": "Contoso",
            "delivery_days": 9,
        },
    ]
    intent = {
        "people_count": 20,
        "categories": ["Keyboard", "Mouse", "Headset"],
        "quantity_by_category": {"Keyboard": 20, "Mouse": 20, "Headset": 20},
        "budget": 3000,
    }

    options = generate_plan_options(products, intent)

    assert options[0]["plan"]["avg_rating"] == 4.7


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


def test_default_plan_selection_prefers_within_budget_option_over_balanced():
    options = [
        {"id": "plan_a", "plan": {"total_amount": 1680.2, "budget_status": "within_budget"}},
        {"id": "plan_b", "plan": {"total_amount": 3827.8, "budget_status": "over_budget"}},
        {"id": "plan_c", "plan": {"total_amount": 3895.0, "budget_status": "over_budget"}},
    ]

    selected = select_default_plan_option(options)

    assert selected["id"] == "plan_a"


def test_default_plan_selection_uses_balanced_when_it_is_within_budget():
    options = [
        {"id": "plan_a", "plan": {"total_amount": 1680.2, "budget_status": "within_budget"}},
        {"id": "plan_b", "plan": {"total_amount": 2661.0, "budget_status": "within_budget"}},
        {"id": "plan_c", "plan": {"total_amount": 3895.0, "budget_status": "over_budget"}},
    ]

    selected = select_default_plan_option(options)

    assert selected["id"] == "plan_b"
