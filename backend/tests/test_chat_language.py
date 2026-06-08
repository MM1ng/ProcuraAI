from fastapi.testclient import TestClient

from main import app


CHAT_MESSAGE = (
    "We need to buy equipment for 20 interns. Budget is under $3000. "
    "Each person needs a keyboard, mouse and headset. Prefer high rating and fast delivery."
)


def test_chat_defaults_to_english_when_language_is_not_provided():
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"message": CHAT_MESSAGE, "session_id": "language-default"},
    )

    body = response.json()
    assert response.status_code == 200
    assert "I found" in body["answer"]
    assert "Budget status" in body["answer"]


def test_chat_returns_chinese_answer_when_language_is_zh():
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"message": CHAT_MESSAGE, "session_id": "language-zh", "language": "zh"},
    )

    body = response.json()
    assert response.status_code == 200
    assert "我找到了" in body["answer"]
    assert "预算状态" in body["answer"]


def test_chat_chinese_answer_translates_internal_status_values():
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "请为远程团队10人推荐办公设备。需要摄像头、耳机和扩展坞。",
            "session_id": "language-zh-no-budget-status",
            "language": "zh",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert "预算状态：未提供预算" in body["answer"]
    assert "库存状态：有效" in body["answer"]
    assert "约束状态：已满足" in body["answer"]
    assert "no_budget_provided" not in body["answer"]
    assert "valid" not in body["answer"]
    assert "satisfied" not in body["answer"]


def test_chat_chinese_answer_includes_recommended_item_details():
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "请为远程团队10人推荐办公设备。需要摄像头、耳机和扩展坞。",
            "session_id": "language-zh-item-details",
            "language": "zh",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert "推荐明细：" in body["answer"]
    for item in body["recommended_plan"]["items"]:
        assert item["name"] in body["answer"]
        assert f"数量 {item['quantity']}" in body["answer"]


def test_chat_returns_french_answer_when_language_is_fr():
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"message": CHAT_MESSAGE, "session_id": "language-fr", "language": "fr"},
    )

    body = response.json()
    assert response.status_code == 200
    assert "J'ai trouvé" in body["answer"]
    assert "Statut du budget" in body["answer"]


def test_chat_trace_records_language_metadata():
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"message": CHAT_MESSAGE, "session_id": "language-trace", "language": "zh"},
    )
    trace_id = response.json()["trace_id"]
    traces = client.get("/api/observability/traces").json()["items"]
    trace = next(item for item in traces if item["trace_id"] == trace_id)

    assert trace["language"] == "zh"


def test_chat_response_and_trace_include_llm_metadata():
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"message": CHAT_MESSAGE, "session_id": "llm-metadata"},
    )
    body = response.json()
    traces = client.get("/api/observability/traces").json()["items"]
    trace = next(item for item in traces if item["trace_id"] == body["trace_id"])

    assert response.status_code == 200
    assert "model_provider" in body
    assert "model_name" in body
    assert "used_mock_llm" in body
    assert "llm_error" in body
    assert trace["model_provider"] == body["model_provider"]
    assert trace["model_name"] == body["model_name"]
    assert trace["used_mock_llm"] == body["used_mock_llm"]
    assert trace["llm_error"] == body["llm_error"]


def test_chat_response_includes_compare_plan_options():
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"message": CHAT_MESSAGE, "session_id": "compare-plans-response"},
    )

    body = response.json()
    assert response.status_code == 200
    assert [option["id"] for option in body["plan_options"]] == ["plan_a", "plan_b", "plan_c"]
    assert [option["strategy"] for option in body["plan_options"]] == [
        "cost_optimized",
        "balanced",
        "premium",
    ]
    selected_option = next(option for option in body["plan_options"] if option["id"] == body["selected_plan_id"])
    assert body["recommended_plan"] == selected_option["plan"]
    assert body["recommended_plan"]["budget_status"] == "within_budget"


def test_followup_no_budget_clears_previous_budget_for_compare_plans():
    client = TestClient(app)
    session_id = "compare-plans-no-budget-followup"
    client.post(
        "/api/chat",
        json={"message": CHAT_MESSAGE, "session_id": session_id, "language": "zh"},
    )

    response = client.post(
        "/api/chat",
        json={
            "message": "请重新生成一个无预算限制的方案。",
            "session_id": session_id,
            "language": "zh",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["parsed_intent"]["budget"] is None
    assert body["recommended_plan"]["budget_status"] == "no_budget_provided"
    assert body["selected_plan_id"] == "plan_b"
    assert [option["plan"]["budget_status"] for option in body["plan_options"]] == [
        "no_budget_provided",
        "no_budget_provided",
        "no_budget_provided",
    ]
    assert all(option["plan"]["selectable"] is True for option in body["plan_options"])
