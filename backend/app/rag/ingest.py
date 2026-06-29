from __future__ import annotations

from app.core.config import DATA_DIR
from app.rag.knowledge_base import load_procurement_policies, load_supplier_profiles
from app.rag.vector_store import build_local_index, rebuild_vector_collections, save_local_index
from app.services.product_service import load_products_from_csv


def ingest_products() -> int:
    products = load_products_from_csv()
    index = build_local_index(products)
    save_local_index(index)
    rebuild_vector_collections(
        products=products,
        policies=load_procurement_policies(),
        suppliers=load_supplier_profiles(),
    )
    bm25_cache = DATA_DIR / "bm25_index.pkl"
    if bm25_cache.exists():
        bm25_cache.unlink()
    embed_cache = DATA_DIR / "embedding_cache.pkl"
    if embed_cache.exists():
        embed_cache.unlink()
    return len(index)
