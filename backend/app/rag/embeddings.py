from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable


EMBEDDING_DIMENSION = 384
TOKEN_PATTERN = re.compile(r"[\w-]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def embed_text(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
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


class HashEmbeddingFunction:
    def __call__(self, input: Iterable[str]) -> list[list[float]]:  # noqa: A002 - Chroma uses this name.
        return [embed_text(text) for text in input]
