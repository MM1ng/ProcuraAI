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
