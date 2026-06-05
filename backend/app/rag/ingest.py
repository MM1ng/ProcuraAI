from __future__ import annotations

from app.rag.vector_store import build_local_index, save_local_index
from app.services.product_service import load_products_from_csv


def ingest_products() -> int:
    products = load_products_from_csv()
    index = build_local_index(products)
    save_local_index(index)
    return len(index)
