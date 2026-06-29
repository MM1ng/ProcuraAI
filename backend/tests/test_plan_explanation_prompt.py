from app.agent.plan_generator import build_plan_explanation_prompt


PRODUCTS = [
    {
        "product_id": "keyboard-1",
        "name": "KeyCo Mechanical Keyboard",
        "category": "Keyboard",
        "brand": "KeyCo",
        "supplier": "Northwind Office Supply",
        "price": 70.0,
        "rating": 4.7,
        "stock": 30,
        "delivery_days": 2,
    }
]


PLAN = {
    "items": [
        {
            "product_id": "keyboard-1",
            "name": "KeyCo Mechanical Keyboard",
            "quantity": 10,
            "unit_price": 70.0,
            "subtotal": 700.0,
        }
    ],
    "total_amount": 700.0,
    "budget_status": "within_budget",
    "inventory_status": "valid",
}


def test_plan_explanation_prompt_enforces_english_source_citations():
    prompt = build_plan_explanation_prompt(
        {"categories": ["Keyboard"], "people_count": 10},
        PRODUCTS,
        PLAN,
        language="en",
    )

    assert "If the provided materials do not contain enough information" in prompt
    assert "existing materials cannot answer" in prompt
    assert "Every factual claim" in prompt
    assert "[来源N]" in prompt
    assert '"source_id": "来源1"' in prompt


def test_plan_explanation_prompt_enforces_chinese_source_citations():
    prompt = build_plan_explanation_prompt(
        {"categories": ["Keyboard"], "people_count": 10},
        PRODUCTS,
        PLAN,
        language="zh",
    )

    assert "如果参考资料不足以回答用户问题" in prompt
    assert "根据现有资料无法回答" in prompt
    assert "每个事实陈述" in prompt
    assert "[来源N]" in prompt
    assert '"source_id": "来源1"' in prompt
