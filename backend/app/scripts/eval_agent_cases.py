"""E2E agent evaluation script. Runs against real LLM or API.
python backend/app/scripts/eval_agent_cases.py
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TEST_CASES = [
    {
        "name": "case1_zh_budget_office_chair_monitor",
        "message": "预算 500 美元买一台办公椅和一台显示器",
        "checks": {
            "categories": ["Office Chair", "Monitor"],
            "budget": 500,
        },
    },
    {
        "name": "case2_zh_dell_monitor_x10",
        "message": "推荐10台戴尔显示器",
        "checks": {
            "brand": "Dell",
            "categories": ["Monitor"],
            "quantity": 10,
        },
    },
    {
        "name": "case3_zh_budget_1000",
        "message": "预算 1000 美元配一套办公设备",
        "checks": {
            "budget": 1000,
        },
    },
    {
        "name": "case4_en_brand_budget_search",
        "message": "Find Dell laptops under 1000 dollars",
        "checks": {
            "brand": "Dell",
            "budget": 1000,
            "max_price": 1000,
        },
    },
    {
        "name": "case5_fr_basic",
        "message": "Je cherche un ordinateur portable",
        "checks": {},
    },
    {
        "name": "case6_budget_50_monitor",
        "message": "预算 50 美元买一台显示器",
        "checks": {
            "budget": 50,
        },
    },
]


def run():
    from app.agent.intent_parser import parse_purchase_request
    from app.core.config import get_settings

    settings = get_settings()
    print(f"Using model: {settings.QWEN_INTENT_MODEL}")
    print(f"Timeout: {settings.QWEN_INTENT_TIMEOUT_SECONDS}s")
    print()

    results = []
    for case in TEST_CASES:
        msg = case["message"]
        print(f"--- {case['name']} ---")
        print(f"  Input: {msg}")
        start = time.time()
        intent = parse_purchase_request(msg, model_override=settings.QWEN_INTENT_MODEL, timeout_override=settings.QWEN_INTENT_TIMEOUT_SECONDS)
        elapsed = time.time() - start

        checks = case["checks"]
        passed = True
        details = []
        for key, expected in checks.items():
            actual = intent.get(key)
            if isinstance(expected, list):
                if set(actual or []) != set(expected):
                    passed = False
                    details.append(f"{key}: expected {expected}, got {actual}")
            elif key == "max_price" and not expected:
                pass  # max_price may be None, which is fine
            elif key == "budget" and not actual:
                # For search intents, budget is moved to max_price
                alt_price = intent.get("max_price")
                if alt_price == expected:
                    pass  # Accept budget via max_price
                else:
                    passed = False
                    details.append(f"{key}: expected {expected}, got {actual} (alt: max_price={alt_price})")
            elif actual != expected:
                passed = False
                details.append(f"{key}: expected {expected}, got {actual}")

        status = "PASS" if passed else "FAIL"
        print(f"  Result: [{status}] {elapsed:.1f}s")
        print(f"    intent={intent.get('intent')} budget={intent.get('budget')} brand={intent.get('brand')}")
        print(f"    categories={intent.get('categories')} quantity={intent.get('quantity')}")
        if details:
            for d in details:
                print(f"    ISSUE: {d}")
        print()
        results.append((case["name"], status, elapsed, details))

    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, status, elapsed, issues in results:
        print(f"  [{status}] {name:40s} {elapsed:.1f}s")
    fail_count = sum(1 for _, s, _, _ in results if s == "FAIL")
    print(f"\n{len(results) - fail_count}/{len(results)} passed")
    return fail_count == 0


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
