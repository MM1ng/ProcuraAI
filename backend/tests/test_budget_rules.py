from app.agent.plan_generator import calculate_budget_status, generate_procurement_plan


def test_calculate_budget_status_identifies_within_budget():
    assert calculate_budget_status(total_amount=950, budget=1000) == "within_budget"


def test_calculate_budget_status_identifies_over_budget():
    assert calculate_budget_status(total_amount=1200, budget=1000) == "over_budget"


def test_generate_procurement_plan_computes_quantities_totals_and_statuses():
    products = [
        {
            "product_id": "P-101",
            "name": "Reliable Keyboard",
            "category": "Keyboard",
            "brand": "KeyPro",
            "price": 35.0,
            "rating": 4.6,
            "stock": 30,
            "supplier": "Northwind Office",
            "delivery_days": 3,
            "description": "Quiet keyboard",
            "tags": "keyboard typing office",
        },
        {
            "product_id": "P-102",
            "name": "Reliable Mouse",
            "category": "Mouse",
            "brand": "PointPro",
            "price": 18.0,
            "rating": 4.5,
            "stock": 30,
            "supplier": "Northwind Office",
            "delivery_days": 3,
            "description": "Wireless mouse",
            "tags": "mouse office",
        },
    ]
    intent = {
        "people_count": 10,
        "budget": 700,
        "categories": ["Keyboard", "Mouse"],
        "min_rating": 4.2,
        "max_delivery_days": 5,
    }

    plan = generate_procurement_plan(products, intent)

    assert plan["total_amount"] == 530.0
    assert plan["total"] == 530.0
    assert plan["budget_status"] == "within_budget"
    assert plan["over_budget"] is False
    assert plan["budget_gap"] == 0
    assert plan["selectable"] is True
    assert plan["status"] == "within_budget"
    assert plan["inventory_status"] == "valid"
    assert plan["constraint_satisfaction"] == "satisfied"
    assert [item["quantity"] for item in plan["items"]] == [10, 10]


def test_generate_procurement_plan_marks_over_budget_plan_not_selectable():
    products = [
        {
            "product_id": "P-expensive-headset",
            "name": "Premium Headset",
            "category": "Headset",
            "brand": "Sony",
            "price": 190,
            "rating": 4.8,
            "stock": 20,
            "supplier": "Contoso",
            "delivery_days": 3,
        }
    ]
    intent = {
        "people_count": 20,
        "categories": ["Headset"],
        "quantity_by_category": {"Headset": 20},
        "budget": 3000,
    }

    plan = generate_procurement_plan(products, intent)

    assert plan["total_amount"] == 3800.0
    assert plan["total"] == 3800.0
    assert plan["budget"] == 3000
    assert plan["over_budget"] is True
    assert plan["budget_gap"] == 800.0
    assert plan["selectable"] is False
    assert plan["status"] == "over_budget"
    assert plan["budget_status"] == "over_budget"


def test_generate_procurement_plan_prefers_budget_feasible_items_when_available():
    products = [
        {
            "product_id": "P-301",
            "name": "Premium Headset",
            "category": "Headset",
            "brand": "AudioMax",
            "price": 120.0,
            "rating": 4.8,
            "stock": 40,
            "supplier": "Northwind Office",
            "delivery_days": 1,
        },
        {
            "product_id": "P-302",
            "name": "Team Headset",
            "category": "Headset",
            "brand": "AudioMax",
            "price": 55.0,
            "rating": 4.4,
            "stock": 40,
            "supplier": "Northwind Office",
            "delivery_days": 4,
        },
        {
            "product_id": "P-303",
            "name": "Premium Keyboard",
            "category": "Keyboard",
            "brand": "KeyPro",
            "price": 95.0,
            "rating": 4.8,
            "stock": 40,
            "supplier": "Northwind Office",
            "delivery_days": 1,
        },
        {
            "product_id": "P-304",
            "name": "Team Keyboard",
            "category": "Keyboard",
            "brand": "KeyPro",
            "price": 35.0,
            "rating": 4.4,
            "stock": 40,
            "supplier": "Northwind Office",
            "delivery_days": 4,
        },
    ]
    intent = {
        "people_count": 20,
        "budget": 2000,
        "categories": ["Headset", "Keyboard"],
        "min_rating": 4.2,
        "max_delivery_days": 5,
    }

    plan = generate_procurement_plan(products, intent)

    assert plan["budget_status"] == "within_budget"
    assert plan["total_amount"] == 1800.0
    assert {item["product_id"] for item in plan["items"]} == {"P-302", "P-304"}


def test_generate_procurement_plan_cheaper_followup_uses_lower_cost_alternatives():
    products = [
        {
            "product_id": "P-premium-headset",
            "name": "Premium Headset",
            "category": "Headset",
            "brand": "AudioMax",
            "price": 120.0,
            "rating": 4.8,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 2,
        },
        {
            "product_id": "P-team-headset",
            "name": "Team Headset",
            "category": "Headset",
            "brand": "AudioMax",
            "price": 55.0,
            "rating": 4.4,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 4,
        },
        {
            "product_id": "P-premium-keyboard",
            "name": "Premium Keyboard",
            "category": "Keyboard",
            "brand": "KeyPro",
            "price": 95.0,
            "rating": 4.8,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 2,
        },
        {
            "product_id": "P-team-keyboard",
            "name": "Team Keyboard",
            "category": "Keyboard",
            "brand": "KeyPro",
            "price": 35.0,
            "rating": 4.4,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 4,
        },
    ]
    previous_plan = {
        "items": [
            {"product_id": "P-premium-headset", "category": "Headset", "quantity": 5, "subtotal": 600.0},
            {"product_id": "P-premium-keyboard", "category": "Keyboard", "quantity": 5, "subtotal": 475.0},
        ],
        "total_amount": 1075.0,
    }
    intent = {
        "people_count": 5,
        "categories": ["Headset", "Keyboard"],
        "quantity_by_category": {"Headset": 5, "Keyboard": 5},
        "revision_intent": "cheaper",
        "need_cheaper_plan": True,
        "min_rating": 4.2,
    }

    plan = generate_procurement_plan(products, intent, previous_plan=previous_plan)

    assert {item["product_id"] for item in plan["items"]} == {"P-team-headset", "P-team-keyboard"}
    assert plan["total_amount"] == 450.0
    assert plan["revision_type"] == "cheaper"
    assert plan["previous_total_amount"] == 1075.0
    assert plan["savings_amount"] == 625.0


def test_generate_procurement_plan_cheaper_followup_keeps_previous_when_candidates_cost_more():
    products = [
        {
            "product_id": "P-costly-headset",
            "name": "Costly Headset",
            "category": "Headset",
            "brand": "AudioMax",
            "price": 120.0,
            "rating": 4.6,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 2,
        },
        {
            "product_id": "P-costly-keyboard",
            "name": "Costly Keyboard",
            "category": "Keyboard",
            "brand": "KeyPro",
            "price": 95.0,
            "rating": 4.5,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 3,
        },
    ]
    previous_plan = {
        "items": [
            {
                "product_id": "P-current-headset",
                "name": "Current Headset",
                "category": "Headset",
                "quantity": 5,
                "unit_price": 60.0,
                "subtotal": 300.0,
            },
            {
                "product_id": "P-current-keyboard",
                "name": "Current Keyboard",
                "category": "Keyboard",
                "quantity": 5,
                "unit_price": 40.0,
                "subtotal": 200.0,
            },
        ],
        "total_amount": 500.0,
    }
    intent = {
        "people_count": 5,
        "categories": ["Headset", "Keyboard"],
        "quantity_by_category": {"Headset": 5, "Keyboard": 5},
        "revision_intent": "cheaper",
        "need_cheaper_plan": True,
        "min_rating": 4.2,
    }

    plan = generate_procurement_plan(products, intent, previous_plan=previous_plan)

    assert {item["product_id"] for item in plan["items"]} == {"P-current-headset", "P-current-keyboard"}
    assert plan["total_amount"] == 500.0
    assert plan["previous_total_amount"] == 500.0
    assert plan["savings_amount"] == 0.0
    assert plan["revision_type"] == "cheaper"
    assert plan["revision_note"] == "no_cheaper_option_found"


def test_generate_procurement_plan_replacement_followup_preserves_unmentioned_categories():
    products = [
        {
            "product_id": "P-premium-headset",
            "name": "Premium Headset",
            "category": "Headset",
            "brand": "AudioMax",
            "price": 120.0,
            "rating": 4.8,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 2,
        },
        {
            "product_id": "P-team-headset",
            "name": "Team Headset",
            "category": "Headset",
            "brand": "AudioMax",
            "price": 55.0,
            "rating": 4.4,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 4,
        },
        {
            "product_id": "P-premium-keyboard",
            "name": "Premium Keyboard",
            "category": "Keyboard",
            "brand": "KeyPro",
            "price": 95.0,
            "rating": 4.8,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 2,
        },
        {
            "product_id": "P-team-keyboard",
            "name": "Team Keyboard",
            "category": "Keyboard",
            "brand": "KeyPro",
            "price": 35.0,
            "rating": 4.4,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 4,
        },
    ]
    previous_plan = {
        "items": [
            {
                "product_id": "P-premium-headset",
                "name": "Premium Headset",
                "category": "Headset",
                "quantity": 5,
                "unit_price": 120.0,
                "subtotal": 600.0,
            },
            {
                "product_id": "P-premium-keyboard",
                "name": "Premium Keyboard",
                "category": "Keyboard",
                "quantity": 5,
                "unit_price": 95.0,
                "subtotal": 475.0,
            },
        ],
        "total_amount": 1075.0,
    }
    intent = {
        "people_count": 5,
        "categories": ["Headset", "Keyboard"],
        "quantity_by_category": {"Headset": 5, "Keyboard": 5},
        "revision_intent": "replace_product",
        "replacement_request": "Replace the headset with a lower cost model delivered within 5 days.",
        "max_delivery_days": 5,
    }

    plan = generate_procurement_plan(products, intent, previous_plan=previous_plan)

    by_category = {item["category"]: item["product_id"] for item in plan["items"]}
    assert by_category == {
        "Headset": "P-team-headset",
        "Keyboard": "P-premium-keyboard",
    }
    preserved_keyboard = next(item for item in plan["items"] if item["category"] == "Keyboard")
    assert preserved_keyboard["unit_price"] == 95.0
    assert preserved_keyboard["subtotal"] == 475.0
    assert plan["total_amount"] == 750.0
    assert plan["revision_type"] == "replace_product"
    assert plan["replacement_categories"] == ["Headset"]


def test_generate_procurement_plan_replacement_followup_ignores_keep_unchanged_categories():
    products = [
        {
            "product_id": "P-team-headset",
            "name": "Team Headset",
            "category": "Headset",
            "brand": "AudioMax",
            "price": 55.0,
            "rating": 4.4,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 4,
        },
        {
            "product_id": "P-team-keyboard",
            "name": "Team Keyboard",
            "category": "Keyboard",
            "brand": "KeyPro",
            "price": 35.0,
            "rating": 4.4,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 4,
        },
        {
            "product_id": "P-team-mouse",
            "name": "Team Mouse",
            "category": "Mouse",
            "brand": "PointCo",
            "price": 18.0,
            "rating": 4.3,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 2,
        },
    ]
    previous_plan = {
        "items": [
            {
                "product_id": "P-current-headset",
                "name": "Current Headset",
                "category": "Headset",
                "quantity": 5,
                "unit_price": 80.0,
                "subtotal": 400.0,
            },
            {
                "product_id": "P-current-keyboard",
                "name": "Current Keyboard",
                "category": "Keyboard",
                "quantity": 5,
                "unit_price": 40.0,
                "subtotal": 200.0,
            },
            {
                "product_id": "P-current-mouse",
                "name": "Current Mouse",
                "category": "Mouse",
                "quantity": 5,
                "unit_price": 25.0,
                "subtotal": 125.0,
            },
        ],
        "total_amount": 725.0,
    }
    intent = {
        "people_count": 5,
        "categories": ["Headset", "Keyboard", "Mouse"],
        "quantity_by_category": {"Headset": 5, "Keyboard": 5, "Mouse": 5},
        "revision_intent": "replace_product",
        "replacement_request": "Replace the current headset with a lower cost alternative, keep the keyboard and mouse unchanged.",
    }

    plan = generate_procurement_plan(products, intent, previous_plan=previous_plan)

    by_category = {item["category"]: item["product_id"] for item in plan["items"]}
    assert by_category == {
        "Headset": "P-team-headset",
        "Keyboard": "P-current-keyboard",
        "Mouse": "P-current-mouse",
    }
    assert plan["replacement_categories"] == ["Headset"]


def test_generate_procurement_plan_lower_cost_replacement_keeps_previous_when_candidate_costs_more():
    products = [
        {
            "product_id": "P-expensive-headset",
            "name": "Expensive Headset",
            "category": "Headset",
            "brand": "AudioMax",
            "price": 120.0,
            "rating": 4.6,
            "stock": 20,
            "supplier": "Northwind Office",
            "delivery_days": 1,
        }
    ]
    previous_plan = {
        "items": [
            {
                "product_id": "P-current-headset",
                "name": "Current Headset",
                "category": "Headset",
                "quantity": 5,
                "unit_price": 60.0,
                "subtotal": 300.0,
            }
        ],
        "total_amount": 300.0,
    }
    intent = {
        "people_count": 5,
        "categories": ["Headset"],
        "quantity_by_category": {"Headset": 5},
        "revision_intent": "replace_product",
        "replacement_request": "Replace the headset with a lower cost alternative.",
    }

    plan = generate_procurement_plan(products, intent, previous_plan=previous_plan)

    assert plan["items"][0]["product_id"] == "P-current-headset"
    assert plan["replacement_categories"] == []
    assert plan["revision_note"] == "no_lower_cost_replacement_found"
