import math

from app.rag.embeddings import HashEmbeddingFunction, embed_text


def test_hash_embedding_is_deterministic_and_normalized():
    first = embed_text("Dell business monitor with fast delivery")
    second = embed_text("Dell business monitor with fast delivery")

    assert first == second
    assert len(first) == 384
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-6)


def test_hash_embedding_function_matches_chroma_callable_shape():
    function = HashEmbeddingFunction()

    embeddings = function(["policy requires approved suppliers", "supplier offers fast delivery"])

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 384
    assert embeddings[0] != embeddings[1]
