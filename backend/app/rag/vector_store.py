from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR


INDEX_FILE = DATA_DIR / "retrieval_index.json"


def build_local_index(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = []
    for product in products:
        text = (
            f"{product.get('name')} {product.get('brand')} {product.get('category')} "
            f"{product.get('supplier')} {product.get('description')} {product.get('tags')} "
            f"price {product.get('price')} rating {product.get('rating')} stock {product.get('stock')} "
            f"delivery {product.get('delivery_days')} compliance {product.get('compliance_level')}"
        )
        index.append({"product_id": product.get("product_id"), "text": text, "metadata": product})
    return index


def save_local_index(index: list[dict[str, Any]], path: Path = INDEX_FILE) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def load_local_index(path: Path = INDEX_FILE) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
