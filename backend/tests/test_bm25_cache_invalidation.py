from __future__ import annotations

import app.rag.ingest as ingest_module


def test_ingest_products_deletes_retrieval_caches_after_rebuilding_vectors(tmp_path, monkeypatch):
    bm25_cache_file = tmp_path / "bm25_index.pkl"
    embedding_cache_file = tmp_path / "embedding_cache.pkl"
    bm25_cache_file.write_bytes(b"cached")
    embedding_cache_file.write_bytes(b"cached")
    products = [{"product_id": "p1"}]

    monkeypatch.setattr(ingest_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ingest_module, "load_products_from_csv", lambda: products)
    monkeypatch.setattr(ingest_module, "build_local_index", lambda loaded: loaded)
    monkeypatch.setattr(ingest_module, "save_local_index", lambda index: None)
    monkeypatch.setattr(ingest_module, "load_procurement_policies", lambda: [])
    monkeypatch.setattr(ingest_module, "load_supplier_profiles", lambda: [])
    monkeypatch.setattr(
        ingest_module,
        "rebuild_vector_collections",
        lambda products, policies, suppliers: {"products": len(products)},
    )

    count = ingest_module.ingest_products()

    assert count == 1
    assert not bm25_cache_file.exists()
    assert not embedding_cache_file.exists()
