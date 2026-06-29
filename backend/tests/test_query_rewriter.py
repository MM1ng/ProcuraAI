from app.rag import query_rewriter


def test_should_rewrite_is_false_for_standalone_query_without_pronouns():
    calls = []

    def fake_llm(prompt, purpose="general", language="en"):
        calls.append(prompt)
        return {"content": "rewritten", "used_mock_llm": False}

    original = "Recommend several keyboards under $100."
    assert query_rewriter.should_rewrite(original, None) is False
    assert query_rewriter.rewrite_query(original, None, llm_invoke=fake_llm) == original
    assert calls == []


def test_should_rewrite_uses_previous_intent_and_rewrite_prompt_context():
    prompts = []

    def fake_llm(prompt, purpose="general", language="en"):
        prompts.append(prompt)
        return {
            "content": "采购键盘和鼠标，替换键盘，要求高评分",
            "used_mock_llm": False,
        }

    previous_intent = {
        "categories": ["Keyboard", "Mouse"],
        "people_count": 12,
    }

    assert query_rewriter.should_rewrite("上次那个方案里的键盘不太行", previous_intent) is True
    rewritten = query_rewriter.rewrite_query(
        "上次那个方案里的键盘不太行",
        previous_intent,
        llm_invoke=fake_llm,
    )

    assert rewritten == "采购键盘和鼠标，替换键盘，要求高评分"
    assert prompts
    assert "Keyboard" in prompts[0]
    assert "12" in prompts[0]
    assert "上次那个方案里的键盘不太行" in prompts[0]


def test_should_rewrite_detects_english_pronouns_without_previous_intent():
    assert query_rewriter.should_rewrite("Replace that with something cheaper", None) is True


def test_should_rewrite_respects_feature_flag(monkeypatch):
    monkeypatch.setattr(query_rewriter.settings, "query_rewrite_enabled", False)

    assert query_rewriter.should_rewrite("上次那个方案里的键盘不太行", {"categories": ["Keyboard"]}) is False


def test_rewrite_query_falls_back_to_original_on_llm_failure():
    def failing_llm(prompt, purpose="general", language="en"):
        raise RuntimeError("llm unavailable")

    message = "这个不太合适"
    assert query_rewriter.rewrite_query(message, {"categories": ["Keyboard"]}, llm_invoke=failing_llm) == message


def test_rewrite_query_falls_back_to_original_on_mock_llm_response():
    def mock_llm(prompt, purpose="general", language="en"):
        return {"content": "这是一条模拟响应", "used_mock_llm": True}

    message = "上次那个不太行"
    assert query_rewriter.rewrite_query(message, {"categories": ["Keyboard"]}, llm_invoke=mock_llm) == message
