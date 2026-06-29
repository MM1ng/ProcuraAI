import math
from types import SimpleNamespace

import pytest

import app.rag.embeddings as embeddings_module
from app.rag.embeddings import DEFAULT_EMBEDDING_DIMENSION, HashEmbeddingFunction, embed_text, embed_texts


@pytest.fixture(autouse=True)
def isolate_embedding_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(embeddings_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(embeddings_module, "_EMBEDDING_CACHE", None)


def test_hash_embedding_fallback_is_deterministic_and_normalized(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    from app.core.config import get_settings

    get_settings.cache_clear()
    first = embed_text("Dell business monitor with fast delivery")
    second = embed_text("Dell business monitor with fast delivery")

    assert first == second
    assert len(first) == DEFAULT_EMBEDDING_DIMENSION
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-6)


def test_hash_embedding_function_matches_chroma_callable_shape(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    from app.core.config import get_settings

    get_settings.cache_clear()
    function = HashEmbeddingFunction()

    embeddings = function(["policy requires approved suppliers", "supplier offers fast delivery"])

    assert len(embeddings) == 2
    assert len(embeddings[0]) == DEFAULT_EMBEDDING_DIMENSION
    assert embeddings[0] != embeddings[1]


def test_tongyi_embedding_uses_dashscope_text_embedding_api(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "tongyi")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")
    from app.core.config import get_settings
    import app.rag.embeddings as embeddings_module

    get_settings.cache_clear()
    expected = [1.0] + [0.0] * 1023
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status_code=200,
            output={"embeddings": [{"embedding": expected}]},
        )

    monkeypatch.setattr(
        embeddings_module,
        "_dashscope_text_embedding_call",
        fake_call,
    )

    assert embed_text("approved supplier monitor", text_type="document") == expected
    assert calls[0]["model"] == "text-embedding-v4"
    assert calls[0]["input"] == "approved supplier monitor"
    assert calls[0]["text_type"] == "document"
    assert calls[0]["dimension"] == 1024
    assert calls[0]["output_type"] == "dense"


def test_tongyi_embedding_uses_pickle_cache_for_repeated_text(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "tongyi")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")
    from app.core.config import get_settings
    import app.rag.embeddings as embeddings_module

    get_settings.cache_clear()
    expected = [1.0] + [0.0] * 1023
    calls = []
    monkeypatch.setattr(embeddings_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(embeddings_module, "_EMBEDDING_CACHE", None)

    def fake_call(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status_code=200,
            output={"embeddings": [{"embedding": expected}]},
        )

    monkeypatch.setattr(embeddings_module, "_dashscope_text_embedding_call", fake_call)

    assert embed_text("approved supplier monitor", text_type="document") == expected
    assert embed_text("approved supplier monitor", text_type="document") == expected

    assert len(calls) == 1
    assert (tmp_path / "embedding_cache.pkl").exists()


def test_tongyi_embedding_cache_key_includes_text_type(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "tongyi")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")
    from app.core.config import get_settings
    import app.rag.embeddings as embeddings_module

    get_settings.cache_clear()
    calls = []
    monkeypatch.setattr(embeddings_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(embeddings_module, "_EMBEDDING_CACHE", None)

    def fake_call(**kwargs):
        calls.append(kwargs)
        value = float(len(calls))
        return SimpleNamespace(
            status_code=200,
            output={"embeddings": [{"embedding": [value] + [0.0] * 1023}]},
        )

    monkeypatch.setattr(embeddings_module, "_dashscope_text_embedding_call", fake_call)

    document_embedding = embed_text("monitor", text_type="document")
    query_embedding = embed_text("monitor", text_type="query")

    assert document_embedding != query_embedding
    assert len(calls) == 2


def test_tongyi_embedding_batches_texts_in_one_dashscope_call(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "tongyi")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")
    from app.core.config import get_settings
    import app.rag.embeddings as embeddings_module

    get_settings.cache_clear()
    first = [1.0] + [0.0] * 1023
    second = [0.0, 1.0] + [0.0] * 1022
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status_code=200,
            output={"embeddings": [{"embedding": first}, {"embedding": second}]},
        )

    monkeypatch.setattr(
        embeddings_module,
        "_dashscope_text_embedding_call",
        fake_call,
    )

    assert embed_texts(["first document", "second document"], text_type="document") == [first, second]
    assert len(calls) == 1
    assert calls[0]["input"] == ["first document", "second document"]


def test_tongyi_embedding_batches_only_uncached_texts(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "tongyi")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")
    from app.core.config import get_settings
    import app.rag.embeddings as embeddings_module

    get_settings.cache_clear()
    first = [1.0] + [0.0] * 1023
    second = [0.0, 1.0] + [0.0] * 1022
    calls = []
    monkeypatch.setattr(embeddings_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(embeddings_module, "_EMBEDDING_CACHE", None)

    def fake_call(**kwargs):
        calls.append(kwargs)
        vectors = [first if text == "first document" else second for text in kwargs["input"]]
        return SimpleNamespace(
            status_code=200,
            output={"embeddings": [{"embedding": vector} for vector in vectors]},
        )

    monkeypatch.setattr(embeddings_module, "_dashscope_text_embedding_call", fake_call)

    assert embed_texts(["first document", "second document"], text_type="document") == [first, second]
    assert embed_texts(["second document", "first document"], text_type="document") == [second, first]

    assert len(calls) == 1


def test_tongyi_embedding_batches_large_inputs_in_chunks(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "tongyi")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")
    from app.core.config import get_settings
    import app.rag.embeddings as embeddings_module

    get_settings.cache_clear()
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        vectors = [[float(len(calls))] + [0.0] * 1023 for _text in kwargs["input"]]
        return SimpleNamespace(
            status_code=200,
            output={"embeddings": [{"embedding": vector} for vector in vectors]},
        )

    monkeypatch.setattr(
        embeddings_module,
        "_dashscope_text_embedding_call",
        fake_call,
    )

    embeddings = embed_texts([f"document {index}" for index in range(25)], text_type="document")

    assert len(embeddings) == 25
    assert [len(call["input"]) for call in calls] == [10, 10, 5]


def test_tongyi_embedding_strict_mode_raises_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "tongyi")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_STRICT", "true")
    from app.core.config import get_settings
    import app.rag.embeddings as embeddings_module

    get_settings.cache_clear()

    def fake_call(**_kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(
        embeddings_module,
        "_dashscope_text_embedding_call",
        fake_call,
    )

    try:
        embed_text("approved supplier monitor")
    except RuntimeError as exc:
        assert "model unavailable" in str(exc)
    else:
        raise AssertionError("strict embedding mode should not fall back to hash embeddings")
