from __future__ import annotations

import hashlib
import math
import os
import pickle
import re
from collections.abc import Iterable
from typing import Any

from app.core.config import DATA_DIR, get_settings


DEFAULT_EMBEDDING_DIMENSION = 1024
EMBEDDING_DIMENSION = DEFAULT_EMBEDDING_DIMENSION
TONGYI_TEXT_EMBEDDING_BATCH_SIZE = 10
TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)
_EMBEDDING_CACHE: dict[str, list[float]] | None = None


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _hash_embed_text(text: str, dimension: int = DEFAULT_EMBEDDING_DIMENSION) -> list[float]:
    vector = [0.0] * dimension
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _embedding_cache_path():
    return DATA_DIR / "embedding_cache.pkl"


def _load_embedding_cache() -> dict[str, list[float]]:
    global _EMBEDDING_CACHE
    if _EMBEDDING_CACHE is not None:
        return _EMBEDDING_CACHE
    path = _embedding_cache_path()
    if not path.exists():
        _EMBEDDING_CACHE = {}
        return _EMBEDDING_CACHE
    try:
        with path.open("rb") as handle:
            cache = pickle.load(handle)
    except Exception:
        cache = {}
    _EMBEDDING_CACHE = cache if isinstance(cache, dict) else {}
    return _EMBEDDING_CACHE


def _save_embedding_cache() -> None:
    if _EMBEDDING_CACHE is None:
        return
    path = _embedding_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(_EMBEDDING_CACHE, handle)


def _embedding_cache_key(text: str, text_type: str, provider: str, model: str, dimension: int) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{provider}:{model}:{dimension}:{text_type}:{digest}"


def _dashscope_text_embedding_call(**kwargs: Any) -> Any:
    import dashscope

    return dashscope.TextEmbedding.call(**kwargs)


def _response_status_code(response: Any) -> int | None:
    value = response.get("status_code") if isinstance(response, dict) else getattr(response, "status_code", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _response_output(response: Any) -> dict[str, Any]:
    output = response.get("output", {}) if isinstance(response, dict) else getattr(response, "output", {})
    return output if isinstance(output, dict) else {}


def _response_message(response: Any) -> str:
    if isinstance(response, dict):
        message = response.get("message", "")
    else:
        message = getattr(response, "message", "")
    return str(message or "")


def _extract_embedding(response: Any) -> list[float]:
    return _extract_embeddings(response)[0]


def _extract_embeddings(response: Any) -> list[list[float]]:
    output = _response_output(response)
    embeddings = output.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        raise RuntimeError("DashScope embedding response did not include embeddings")
    vectors: list[list[float]] = []
    for item in embeddings:
        if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
            raise RuntimeError("DashScope embedding response had an unexpected shape")
        vectors.append([float(value) for value in item["embedding"]])
    return vectors


def _tongyi_embed_texts(texts: list[str], text_type: str = "document") -> list[list[float]]:
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured")
    provider = settings.embedding_provider.strip().lower()
    use_cache = os.getenv("EMBEDDING_STRICT", "").strip().lower() not in {"1", "true", "yes", "y", "on"}
    cache = _load_embedding_cache() if use_cache else {}
    keys = [
        _embedding_cache_key(text, text_type, provider, settings.embedding_model, settings.embedding_dimension)
        for text in texts
    ]
    all_embeddings: list[list[float] | None] = [cache.get(key) for key in keys]
    misses = [(index, text) for index, (text, cached) in enumerate(zip(texts, all_embeddings)) if cached is None]

    for start in range(0, len(misses), TONGYI_TEXT_EMBEDDING_BATCH_SIZE):
        chunk = misses[start:start + TONGYI_TEXT_EMBEDDING_BATCH_SIZE]
        chunk_texts = [text for _index, text in chunk]
        chunk_embeddings = _tongyi_embed_texts_chunk(chunk_texts, text_type=text_type)
        for (index, _text), embedding in zip(chunk, chunk_embeddings):
            all_embeddings[index] = embedding
            if use_cache:
                cache[keys[index]] = embedding

    if use_cache and misses:
        _save_embedding_cache()
    return [embedding for embedding in all_embeddings if embedding is not None]


def _tongyi_embed_texts_chunk(texts: list[str], text_type: str = "document") -> list[list[float]]:
    settings = get_settings()
    response = _dashscope_text_embedding_call(
        model=settings.embedding_model,
        input=texts,
        text_type=text_type,
        dimension=settings.embedding_dimension,
        output_type="dense",
        api_key=settings.dashscope_api_key,
    )
    status_code = _response_status_code(response)
    if status_code is not None and status_code >= 400:
        raise RuntimeError(f"DashScope embedding request failed: {_response_message(response) or status_code}")
    embeddings = _extract_embeddings(response)
    if len(embeddings) != len(texts):
        raise RuntimeError(f"DashScope returned {len(embeddings)} embeddings, expected {len(texts)}")
    for embedding in embeddings:
        if len(embedding) != settings.embedding_dimension:
            raise RuntimeError(
                f"DashScope returned {len(embedding)} dimensions, expected {settings.embedding_dimension}"
            )
    return embeddings


def _tongyi_embed_text(text: str, text_type: str = "document") -> list[float]:
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured")
    use_cache = os.getenv("EMBEDDING_STRICT", "").strip().lower() not in {"1", "true", "yes", "y", "on"}
    provider = settings.embedding_provider.strip().lower()
    key = _embedding_cache_key(text, text_type, provider, settings.embedding_model, settings.embedding_dimension)
    cache = _load_embedding_cache() if use_cache else {}
    if use_cache and key in cache:
        return cache[key]
    response = _dashscope_text_embedding_call(
        model=settings.embedding_model,
        input=text,
        text_type=text_type,
        dimension=settings.embedding_dimension,
        output_type="dense",
        api_key=settings.dashscope_api_key,
    )
    status_code = _response_status_code(response)
    if status_code is not None and status_code >= 400:
        raise RuntimeError(f"DashScope embedding request failed: {_response_message(response) or status_code}")
    embedding = _extract_embedding(response)
    if len(embedding) != settings.embedding_dimension:
        raise RuntimeError(
            f"DashScope returned {len(embedding)} dimensions, expected {settings.embedding_dimension}"
        )
    if use_cache:
        cache[key] = embedding
        _save_embedding_cache()
    return embedding


def embed_text(text: str, dimension: int | None = None, text_type: str = "document") -> list[float]:
    settings = get_settings()
    target_dimension = dimension or settings.embedding_dimension
    provider = settings.embedding_provider.strip().lower()
    if provider in {"tongyi", "dashscope", "bailian"}:
        try:
            return _tongyi_embed_text(text, text_type=text_type)
        except Exception:
            if os.getenv("EMBEDDING_STRICT", "").strip().lower() in {"1", "true", "yes", "y", "on"}:
                raise
            return _hash_embed_text(text, target_dimension)
    return _hash_embed_text(text, target_dimension)


def embed_texts(texts: list[str], dimension: int | None = None, text_type: str = "document") -> list[list[float]]:
    settings = get_settings()
    target_dimension = dimension or settings.embedding_dimension
    provider = settings.embedding_provider.strip().lower()
    if provider in {"tongyi", "dashscope", "bailian"}:
        try:
            return _tongyi_embed_texts(texts, text_type=text_type)
        except Exception:
            if os.getenv("EMBEDDING_STRICT", "").strip().lower() in {"1", "true", "yes", "y", "on"}:
                raise
            return [_hash_embed_text(text, target_dimension) for text in texts]
    return [_hash_embed_text(text, target_dimension) for text in texts]


class HashEmbeddingFunction:
    def __call__(self, input: Iterable[str]) -> list[list[float]]:  # noqa: A002 - Chroma uses this name.
        return [embed_text(text) for text in input]
