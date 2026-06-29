"""Deterministic tests for intent repair, schema validation, and planner logic.
No LLM calls - safe to run with pytest."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agent.intent_repair import repair_intent
from app.agent.intent_schema import validate_intent_schema


def test_case1_budget_office_chair_and_monitor():
    """Case 1: Chinese dual-category + budget"""
    payload = {"intent": "recommendation", "categories": ["办公椅", "显示器"], "budget": 500}
    result = repair_intent(payload, "预算 500 美元买一台办公椅和一台显示器")
    assert "Office Chair" in result.get("categories", []), "Should resolve to Office Chair"
    assert "Monitor" in result.get("categories", []), "Should resolve to Monitor"
    assert result.get("budget") == 500, "Budget should be 500"
    assert result.get("quantity") == 1, "Quantity should be 1"
    valid, errors = validate_intent_schema(result)
    assert valid, f"Schema validation failed: {errors}"
    print("  PASS: case1")


def test_case2_dell_monitors_x10():
    """Case 2: Chinese brand + quantity + category"""
    payload = {"intent": "recommendation", "categories": ["显示器"], "quantity": 10}
    result = repair_intent(payload, "推荐10台戴尔显示器")
    assert result.get("brand") == "Dell", f"Brand should be Dell, got {result.get('brand')}"
    assert "Monitor" in result.get("categories", []), f"Should contain Monitor, got {result.get('categories')}"
    assert result.get("quantity") == 10, f"Quantity should be 10, got {result.get('quantity')}"
    valid, errors = validate_intent_schema(result)
    assert valid, f"Schema validation failed: {errors}"
    print("  PASS: case2")


def test_case3_budget_1000():
    """Case 3: Chinese general office setup with budget"""
    payload = {"intent": "recommendation", "categories": ["办公设备"], "budget": 1000}
    result = repair_intent(payload, "预算 1000 美元配一套办公设备")
    assert result.get("budget") == 1000, f"Budget should be 1000, got {result.get('budget')}"
    valid, errors = validate_intent_schema(result)
    assert valid, f"Schema validation failed: {errors}"
    print("  PASS: case3")


def test_case4_english_brand_budget():
    """Case 4: English brand + budget search"""
    payload = {"intent": "search", "brand": "dell"}
    result = repair_intent(payload, "Find Dell laptops under 1000 dollars")
    assert result.get("brand") == "Dell", f"Brand should be Dell, got {result.get('brand')}"
    assert result.get("budget") == 1000.0, f"Budget should be 1000, got {result.get('budget')}"
    print("  PASS: case4")


def test_budget_over_budget_detection():
    """Planner: over-budget detection logic"""
    from app.agent.plan_generator import calculate_budget_status
    assert calculate_budget_status(100, 50) == "over_budget", "100 > 50 should be over_budget"
    assert calculate_budget_status(50, 100) == "within_budget", "50 <= 100 should be within_budget"
    assert calculate_budget_status(50, None) == "no_budget_provided", "None budget should be no_budget_provided"
    print("  PASS: over_budget detection")


def test_quantity_times_price():
    """Planner: quantity * unit_price calculation"""
    from app.agent.plan_generator import generate_procurement_plan
    products = [{
        "product_id": "P-TEST",
        "name": "Test Monitor",
        "category": "Monitor",
        "brand": "Dell",
        "price": 150.0,
        "unit_price": 150.0,
        "rating": 4.5,
        "stock": 100,
        "delivery_days": 3,
        "supplier": "Test",
    }]
    intent = {
        "intent": "recommendation",
        "categories": ["Monitor"],
        "quantity": 10,
        "per_category_quantities": {"Monitor": 10},
        "people_count": 10,
        "budget": 2000,
    }
    plan = generate_procurement_plan(products, intent)
    items = plan.get("items", []) or []
    assert len(items) > 0, "Should have at least 1 item"
    item = items[0]
    qty = int(item.get("quantity", 0))
    unit_price = float(item.get("unit_price", 0))
    total = float(plan.get("total_amount", 0))
    assert qty == 10, f"Quantity should be 10, got {qty}"
    assert total == unit_price * qty, f"Total {total} != {unit_price} * {qty}"
    print(f"  PASS: quantity*price = {unit_price} * {qty} = {total}")


def test_schema_rejects_invalid():
    """Schema validator rejects invalid inputs"""
    valid, errors = validate_intent_schema({"intent": "invalid_intent"})
    assert not valid, "Should reject invalid intent"
    valid2, errors2 = validate_intent_schema({"budget": -100})
    assert not valid2, "Should reject negative budget"
    valid3, _ = validate_intent_schema({"intent": "recommendation", "budget": 500, "categories": ["Laptop"]})
    assert valid3, "Should accept valid schema"
    print("  PASS: schema validation")


if __name__ == "__main__":
    test_case1_budget_office_chair_and_monitor()
    test_case2_dell_monitors_x10()
    test_case3_budget_1000()
    test_case4_english_brand_budget()
    test_budget_over_budget_detection()
    test_quantity_times_price()
    test_schema_rejects_invalid()
    print("\nAll deterministic tests passed!")
