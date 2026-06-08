from app.agent.intent_parser import parse_purchase_request
import app.agent.intent_parser as intent_parser


def test_parse_purchase_request_extracts_intern_equipment_constraints():
    message = (
        "We need to buy equipment for 20 interns. Budget is under $3000. "
        "Each person needs a keyboard, mouse and headset. Prefer high rating "
        "and fast delivery."
    )

    intent = parse_purchase_request(message)

    assert intent["people_count"] == 20
    assert intent["budget"] == 3000
    assert intent["categories"] == ["Keyboard", "Mouse", "Headset"]
    assert "high rating" in intent["preferences"]
    assert "fast delivery" in intent["preferences"]
    assert intent["min_rating"] >= 4.2
    assert intent["max_delivery_days"] <= 5


def test_parse_purchase_request_extracts_chinese_rating_and_delivery_preferences():
    intent = parse_purchase_request(
        "我们需要为20名实习生购买设备，预算在3000美元以内，每人需要键盘、鼠标和耳机。偏好高评分和快速配送。"
    )

    assert intent["people_count"] == 20
    assert intent["budget"] == 3000
    assert intent["categories"] == ["Keyboard", "Mouse", "Headset"]
    assert "high rating" in intent["preferences"]
    assert "fast delivery" in intent["preferences"]
    assert intent["min_rating"] == 4.2
    assert intent["max_delivery_days"] == 5


def test_parse_purchase_request_supports_followup_cheaper_revisions():
    intent = parse_purchase_request(
        "Make this procurement plan cheaper but keep rating above 4.2."
    )

    assert intent["revision_intent"] == "cheaper"
    assert intent["min_rating"] == 4.2
    assert intent["preferences"] == ["lower cost", "high rating"]


def test_parse_purchase_request_clears_previous_budget_when_user_says_no_budget():
    previous_intent = {
        "people_count": 10,
        "budget": 3000,
        "categories": ["Headset", "Webcam", "Docking Station"],
        "quantity_by_category": {"Headset": 10, "Webcam": 10, "Docking Station": 10},
    }

    intent = parse_purchase_request("请重新生成一个无预算限制的方案。", previous_intent)

    assert intent["budget"] is None
    assert "within budget" not in intent["constraints"]


def test_parse_purchase_request_uses_qwen_json_when_available(monkeypatch):
    def fake_llm(prompt: str, purpose: str):
        assert purpose == "intent_parser"
        assert "Return ONLY valid JSON" in prompt
        return {
            "content": """
            {
              "people_count": 8,
              "budget": 1200,
              "categories": ["keyboard", "mouse"],
              "quantity_per_category": {"keyboard": 8, "mouse": 8},
              "preferences": ["high rating"],
              "constraints": ["within budget"],
              "min_rating": 4.3,
              "max_delivery_days": 4,
              "need_cheaper_plan": false,
              "replacement_request": null
            }
            """,
            "model_provider": "tongyi",
            "model_name": "qwen3.7-max",
            "used_mock_llm": False,
            "error": None,
        }

    monkeypatch.setattr(intent_parser, "safe_llm_invoke", fake_llm)

    intent = parse_purchase_request("Need keyboards and mice for 8 interns under $1200.")

    assert intent["used_llm_parser"] is True
    assert intent["model_provider"] == "tongyi"
    assert intent["model_name"] == "qwen3.7-max"
    assert intent["used_mock_llm"] is False
    assert intent["llm_error"] is None
    assert intent["people_count"] == 8
    assert intent["categories"] == ["Keyboard", "Mouse"]
    assert intent["quantity_per_category"] == {"Keyboard": 8, "Mouse": 8}
    assert intent["quantity_by_category"] == {"Keyboard": 8, "Mouse": 8}


def test_parse_purchase_request_falls_back_to_rules_when_llm_json_is_invalid(monkeypatch):
    monkeypatch.setattr(
        intent_parser,
        "safe_llm_invoke",
        lambda prompt, purpose: {
            "content": "not json",
            "model_provider": "tongyi",
            "model_name": "qwen3.7-max",
            "used_mock_llm": False,
            "error": None,
        },
    )

    intent = parse_purchase_request("Buy headsets for 5 people under $500 with rating above 4.2.")

    assert intent["used_llm_parser"] is False
    assert intent["model_provider"] == "tongyi"
    assert intent["model_name"] == "qwen3.7-max"
    assert intent["used_mock_llm"] is False
    assert "JSON" in intent["llm_error"]
    assert intent["people_count"] == 5
    assert intent["budget"] == 500
    assert intent["categories"] == ["Headset"]


def test_parse_purchase_request_normalizes_plural_llm_categories(monkeypatch):
    monkeypatch.setattr(
        intent_parser,
        "safe_llm_invoke",
        lambda prompt, purpose: {
            "content": """
            {
              "people_count": 5,
              "budget": null,
              "categories": ["Headsets", "Keyboards"],
              "quantity_per_category": {"Headsets": 5, "Keyboards": 5},
              "preferences": ["high rating"],
              "constraints": [],
              "min_rating": null,
              "max_delivery_days": null,
              "need_cheaper_plan": false,
              "replacement_request": null
            }
            """,
            "model_provider": "tongyi",
            "model_name": "qwen3.7-max",
            "used_mock_llm": False,
            "error": None,
        },
    )

    intent = parse_purchase_request("We need headsets and keyboards for 5 people.")

    assert intent["categories"] == ["Keyboard", "Headset"]
    assert intent["quantity_by_category"] == {"Keyboard": 5, "Headset": 5}


def test_parse_purchase_request_adds_category_normalization_trace_for_chinese_monitor(monkeypatch):
    def fake_safe_llm_invoke(prompt, purpose="general"):
        return {
            "content": """
            {
              "people_count": 1,
              "budget": 50000,
              "categories": ["显示器"],
              "quantity_per_category": {"显示器": 1},
              "preferences": [],
              "constraints": [],
              "min_rating": null,
              "max_delivery_days": null,
              "need_cheaper_plan": false,
              "replacement_request": null,
              "replacement_categories": [],
              "replacement_brand": null
            }
            """,
            "model_provider": "tongyi",
            "model_name": "qwen3.7-max",
            "used_mock_llm": False,
            "error": None,
            "fallback_reason": None,
            "latency_ms": 1,
        }

    monkeypatch.setattr("app.agent.intent_parser.safe_llm_invoke", fake_safe_llm_invoke)

    intent = parse_purchase_request("我们要采购一批显示器给新办公室使用，预算5万元")

    assert intent["categories"] == ["Monitor"]
    assert intent["quantity_by_category"] == {"Monitor": 1}
    assert intent["category_normalization"][0]["original_category"] == "显示器"
    assert intent["category_normalization"][0]["normalized_category"] == "Monitor"
    assert intent["category_normalization"][0]["normalization_method"] == "alias"
    assert "Monitor" in intent["category_normalization"][0]["allowed_categories"]
    assert intent["category_normalization"][0]["warning"] is None
