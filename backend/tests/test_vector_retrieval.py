from fastapi.testclient import TestClient

import app.agent.procurement_agent as procurement_agent
import app.rag.retriever as retriever
from app.rag.knowledge_base import load_procurement_policies, load_supplier_profiles
from app.rag.vector_store import (
    PRODUCT_COLLECTION,
    POLICY_COLLECTION,
    SUPPLIER_COLLECTION,
    build_product_document,
    query_vector_collection,
    rebuild_vector_collections,
)
from main import app


PRODUCTS = [
    {
        "product_id": "monitor-dell",
        "name": "Dell UltraSharp Monitor",
        "category": "Monitor",
        "brand": "Dell",
        "supplier": "Contoso Business Tech",
        "price": 180.0,
        "rating": 4.8,
        "stock": 50,
        "delivery_days": 2,
        "description": "Color accurate 27 inch display for office work.",
        "tags": "display office monitor",
        "compliance_level": "ISO-Ready",
    },
    {
        "product_id": "headset-poly",
        "name": "Poly Remote Headset",
        "category": "Headset",
        "brand": "Poly",
        "supplier": "Northwind Office Supply",
        "price": 95.0,
        "rating": 4.6,
        "stock": 40,
        "delivery_days": 4,
        "description": "Noise cancelling headset for remote meetings.",
        "tags": "audio remote meeting",
        "compliance_level": "Standard",
    },
    {
        "product_id": "monitor-slow",
        "name": "Slow Budget Monitor",
        "category": "Monitor",
        "brand": "ViewBest",
        "supplier": "Budget Supply",
        "price": 90.0,
        "rating": 4.0,
        "stock": 3,
        "delivery_days": 12,
        "description": "Entry display with long delivery.",
        "tags": "display budget",
        "compliance_level": "Standard",
    },
]

POLICIES = [
    {
        "id": "policy-approved-suppliers",
        "title": "Approved Supplier Policy",
        "text": "Purchases over 1000 USD should prefer approved suppliers with ISO-ready compliance.",
        "category": "supplier_compliance",
    }
]

SUPPLIERS = [
    {
        "id": "supplier-contoso",
        "supplier": "Contoso Business Tech",
        "text": "Contoso Business Tech is an approved supplier for monitors with reliable two day delivery.",
        "risk_level": "low",
    }
]

class _MockEmptyBM25:
    """Mock BM25 retriever that returns no results."""
    def search(self, query, top_k=12):
        return []
    def search_with_synonym_boost(self, query, intent=None, top_k=12):
        return []
    def search_by_categories(self, query, categories=None, top_k=12):
        return []


class _MockDiverseBM25:
    def search(self, query, top_k=12):
        return []

    def search_with_synonym_boost(self, query, intent=None, top_k=12):
        return []

    def search_by_categories(self, query, categories=None, top_k=12):
        products_by_category = {
            "Webcam": {
                "product_id": "webcam-logi",
                "name": "Logitech Team Webcam",
                "category": "Webcam",
                "brand": "Logitech",
                "supplier": "Northwind Office Supply",
                "price": 80.0,
                "rating": 4.5,
                "stock": 25,
                "delivery_days": 3,
                "description": "Webcam for remote meetings.",
                "tags": "camera meeting remote",
                "bm25_score": 10.0,
                "bm25_matched_terms": ["webcam"],
            },
            "Headset": {
                "product_id": "headset-poly",
                "name": "Poly Remote Headset",
                "category": "Headset",
                "brand": "Poly",
                "supplier": "Northwind Office Supply",
                "price": 95.0,
                "rating": 4.6,
                "stock": 40,
                "delivery_days": 4,
                "description": "Noise cancelling headset for remote meetings.",
                "tags": "audio remote meeting",
                "bm25_score": 9.0,
                "bm25_matched_terms": ["headset"],
            },
            "Docking Station": {
                "product_id": "dock-hp",
                "name": "HP Travel Docking Station",
                "category": "Docking Station",
                "brand": "HP",
                "supplier": "Contoso Business Tech",
                "price": 130.0,
                "rating": 4.4,
                "stock": 30,
                "delivery_days": 2,
                "description": "USB-C dock for remote workers.",
                "tags": "dock remote workstation",
                "bm25_score": 8.0,
                "bm25_matched_terms": ["dock"],
            },
        }
        return [dict(products_by_category[category]) for category in categories or [] if category in products_by_category][:top_k]


class _MockSingleCategoryBM25:
    def search(self, query, top_k=12):
        return []

    def search_with_synonym_boost(self, query, intent=None, top_k=12):
        return [
            {
                "product_id": "shared-keyboard",
                "name": "Shared Mechanical Keyboard",
                "category": "Keyboard",
                "brand": "KeyCo",
                "supplier": "Northwind Office Supply",
                "price": 70.0,
                "rating": 4.7,
                "stock": 30,
                "delivery_days": 2,
                "description": "Keyboard matched by both retrieval channels.",
                "tags": "keyboard mechanical office",
                "bm25_score": 10.0,
                "bm25_matched_terms": ["keyboard"],
            },
            {
                "product_id": "bm25-only-keyboard",
                "name": "BM25 Only Keyboard",
                "category": "Keyboard",
                "brand": "TextMatch",
                "supplier": "Contoso Business Tech",
                "price": 45.0,
                "rating": 4.6,
                "stock": 30,
                "delivery_days": 3,
                "description": "Keyboard matched only by BM25.",
                "tags": "keyboard office",
                "bm25_score": 9.0,
                "bm25_matched_terms": ["keyboard"],
            },
        ][:top_k]

    def search_by_categories(self, query, categories=None, top_k=12):
        return self.search_with_synonym_boost(query, {"categories": categories or []}, top_k=top_k)


class _MockBM25Only:
    def search(self, query, top_k=12):
        return []

    def search_with_synonym_boost(self, query, intent=None, top_k=12):
        return [
            {
                "product_id": "bm25-headset",
                "name": "BM25 Headset",
                "category": "Headset",
                "brand": "Poly",
                "supplier": "Northwind Office Supply",
                "price": 95.0,
                "rating": 4.6,
                "stock": 40,
                "delivery_days": 4,
                "description": "Noise cancelling headset.",
                "tags": "headset audio",
                "bm25_score": 42.0,
                "bm25_matched_terms": ["headset"],
            }
        ][:top_k]

    def search_by_categories(self, query, categories=None, top_k=12):
        return self.search_with_synonym_boost(query, {"categories": categories or []}, top_k=top_k)


def test_rrf_fusion_prefers_items_seen_by_vector_and_bm25():
    vector_hits = [
        {"id": "a", "metadata": {"product_id": "a", "category": "Keyboard", "rating": 4.5, "delivery_days": 3, "price": 50}},
        {"id": "shared", "metadata": {"product_id": "shared", "category": "Keyboard", "rating": 4.5, "delivery_days": 3, "price": 60}},
    ]
    bm25_products = [
        {"product_id": "shared", "category": "Keyboard", "rating": 4.5, "delivery_days": 3, "price": 60},
        {"product_id": "b", "category": "Keyboard", "rating": 4.5, "delivery_days": 3, "price": 40},
    ]

    fused = retriever._fuse_vector_and_bm25_results(vector_hits, bm25_products, retriever._constraints({}))

    assert [item["product_id"] for item in fused] == ["shared", "a", "b"]
    assert fused[0]["retrieval_reason"] == "hybrid_rrf_vector_bm25"
    assert fused[0]["vector_rank"] == 2
    assert fused[0]["bm25_rank"] == 1
    assert fused[0]["retrieval_channels"] == ["vector", "bm25"]


def test_single_category_retrieval_uses_rrf_for_vector_and_bm25(monkeypatch, tmp_path):
    def fake_vector_collection(collection_name, query, top_k=12, persist_dir=None):
        if collection_name != PRODUCT_COLLECTION:
            return []
        return [
            {
                "id": "vector-only-keyboard",
                "metadata": {
                    "product_id": "vector-only-keyboard",
                    "name": "Vector Only Keyboard",
                    "category": "Keyboard",
                    "brand": "VectorCo",
                    "supplier": "Contoso Business Tech",
                    "price": 60.0,
                    "rating": 4.5,
                    "stock": 30,
                    "delivery_days": 3,
                    "description": "Keyboard matched only by vector search.",
                    "tags": "keyboard office",
                },
                "score": 0.99,
            },
            {
                "id": "shared-keyboard",
                "metadata": {
                    "product_id": "shared-keyboard",
                    "name": "Shared Mechanical Keyboard",
                    "category": "Keyboard",
                    "brand": "KeyCo",
                    "supplier": "Northwind Office Supply",
                    "price": 70.0,
                    "rating": 4.7,
                    "stock": 30,
                    "delivery_days": 2,
                    "description": "Keyboard matched by both retrieval channels.",
                    "tags": "keyboard mechanical office",
                },
                "score": 0.5,
            },
        ][:top_k]

    monkeypatch.setattr(retriever, "query_vector_collection", fake_vector_collection)
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda: _MockSingleCategoryBM25())

    result = retriever.retrieve_products_with_evidence(
        "Find keyboards",
        {"categories": ["Keyboard"], "people_count": 10},
        top_k=5,
        persist_dir=tmp_path,
    )

    assert [item["product_id"] for item in result.products][:3] == [
        "shared-keyboard",
        "vector-only-keyboard",
        "bm25-only-keyboard",
    ]
    assert result.products[0]["rrf_score"] == result.products[0]["retrieval_score"]
    assert result.products[0]["retrieval_channels"] == ["vector", "bm25"]
    assert result.evidence["retrieval_mode"] == "hybrid_rrf_vector_bm25"
    assert result.evidence["products"][0]["source_id"] == "来源1"
    assert result.evidence["products"][0]["source_index"] == 1


def test_vector_empty_bm25_results_still_use_rrf(monkeypatch, tmp_path):
    monkeypatch.setattr(retriever, "query_vector_collection", lambda *args, **kwargs: [])
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda: _MockBM25Only())

    result = retriever.retrieve_products_with_evidence(
        "Need headsets",
        {"categories": ["Headset"], "people_count": 10},
        top_k=5,
        persist_dir=tmp_path,
    )

    assert [item["product_id"] for item in result.products] == ["bm25-headset"]
    assert result.products[0]["retrieval_channels"] == ["bm25"]
    assert result.products[0]["rrf_score"] == result.products[0]["retrieval_score"]
    assert result.evidence["retrieval_mode"] == "hybrid_rrf_vector_bm25"
    assert "retrieval_fallback" not in result.evidence


def test_vector_and_bm25_empty_falls_back_to_local_products(monkeypatch):
    monkeypatch.setattr(retriever, "query_vector_collection", lambda *args, **kwargs: [])
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda: _MockEmptyBM25())
    monkeypatch.setattr(
        retriever,
        "load_local_index",
        lambda: [{"metadata": product, "text": build_product_document(product)} for product in PRODUCTS],
    )

    result = retriever.retrieve_products_with_evidence(
        "Need monitor",
        {"categories": ["Monitor"], "people_count": 10, "max_delivery_days": 5},
        top_k=5,
    )

    assert result.products
    assert result.evidence["retrieval_fallback"] == "text_products"
    assert result.evidence["retrieval_mode"] == "hybrid_vector_filter"


def test_retrieve_products_with_evidence_uses_multi_category_quota(monkeypatch, tmp_path):
    def fake_vector_collection(collection_name, query, top_k=12, persist_dir=None):
        if collection_name != PRODUCT_COLLECTION:
            return []
        if "Webcam" in query:
            return [
                {
                    "id": "webcam-logi",
                    "metadata": {
                        "product_id": "webcam-logi",
                        "name": "Logitech Team Webcam",
                        "category": "Webcam",
                        "brand": "Logitech",
                        "supplier": "Northwind Office Supply",
                        "price": 80.0,
                        "rating": 4.5,
                        "stock": 25,
                        "delivery_days": 3,
                        "description": "Webcam for remote meetings.",
                        "tags": "camera meeting remote",
                    },
                    "score": 0.91,
                }
            ]
        if "Headset" in query:
            return [
                {
                    "id": "headset-poly",
                    "metadata": {
                        "product_id": "headset-poly",
                        "name": "Poly Remote Headset",
                        "category": "Headset",
                        "brand": "Poly",
                        "supplier": "Northwind Office Supply",
                        "price": 95.0,
                        "rating": 4.6,
                        "stock": 40,
                        "delivery_days": 4,
                        "description": "Noise cancelling headset for remote meetings.",
                        "tags": "audio remote meeting",
                    },
                    "score": 0.9,
                }
            ]
        if "Docking Station" in query:
            return [
                {
                    "id": "dock-hp",
                    "metadata": {
                        "product_id": "dock-hp",
                        "name": "HP Travel Docking Station",
                        "category": "Docking Station",
                        "brand": "HP",
                        "supplier": "Contoso Business Tech",
                        "price": 130.0,
                        "rating": 4.4,
                        "stock": 30,
                        "delivery_days": 2,
                        "description": "USB-C dock for remote workers.",
                        "tags": "dock remote workstation",
                    },
                    "score": 0.89,
                }
            ]
        return []

    monkeypatch.setattr(retriever, "query_vector_collection", fake_vector_collection)
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda: _MockDiverseBM25())

    result = retriever.retrieve_products_with_evidence(
        "Recommend webcams, headsets and docking stations for a remote team.",
        {"categories": ["Webcam", "Headset", "Docking Station"], "people_count": 10},
        top_k=5,
        persist_dir=tmp_path,
    )

    assert {"Webcam", "Headset", "Docking Station"} <= {item["category"] for item in result.products}
    assert all(item["rrf_score"] == item["retrieval_score"] for item in result.products)
    assert all(item["retrieval_channels"] for item in result.products)


def test_multi_category_quota_respects_structured_constraints(monkeypatch, tmp_path):
    def fake_vector_collection(collection_name, query, top_k=12, persist_dir=None):
        if collection_name != PRODUCT_COLLECTION:
            return []
        if "Webcam" in query:
            return [
                {
                    "id": "webcam-low",
                    "metadata": {
                        "product_id": "webcam-low",
                        "name": "Low Rated Webcam",
                        "category": "Webcam",
                        "rating": 3.5,
                        "stock": 25,
                        "delivery_days": 3,
                        "price": 45.0,
                    },
                    "score": 0.99,
                },
                {
                    "id": "webcam-good",
                    "metadata": {
                        "product_id": "webcam-good",
                        "name": "Good Webcam",
                        "category": "Webcam",
                        "rating": 4.6,
                        "stock": 25,
                        "delivery_days": 3,
                        "price": 80.0,
                    },
                    "score": 0.9,
                },
            ]
        return []

    monkeypatch.setattr(retriever, "query_vector_collection", fake_vector_collection)
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda: _MockEmptyBM25())

    result = retriever.retrieve_products_with_evidence(
        "Find high rating webcams.",
        {"categories": ["Webcam"], "people_count": 10, "min_rating": 4.5},
        top_k=5,
        persist_dir=tmp_path,
    )

    assert [item["product_id"] for item in result.products] == ["webcam-good"]


def test_rebuild_vector_collections_creates_product_policy_and_supplier_collections(tmp_path):
    counts = rebuild_vector_collections(
        products=PRODUCTS,
        policies=POLICIES,
        suppliers=SUPPLIERS,
        persist_dir=tmp_path,
    )

    assert counts == {
        PRODUCT_COLLECTION: 3,
        POLICY_COLLECTION: 1,
        SUPPLIER_COLLECTION: 1,
    }
    assert query_vector_collection(PRODUCT_COLLECTION, "office display", top_k=2, persist_dir=tmp_path)[0]["id"] == "monitor-dell"
    assert query_vector_collection(POLICY_COLLECTION, "approved supplier compliance", top_k=1, persist_dir=tmp_path)[0]["id"] == "policy-approved-suppliers"
    assert query_vector_collection(SUPPLIER_COLLECTION, "Contoso delivery", top_k=1, persist_dir=tmp_path)[0]["id"] == "supplier-contoso"


def test_retrieve_products_with_evidence_uses_vector_top_k_and_structured_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda: _MockEmptyBM25())
    rebuild_vector_collections(PRODUCTS, POLICIES, SUPPLIERS, persist_dir=tmp_path)

    result = retriever.retrieve_products_with_evidence(
        "Need office monitors quickly",
        {
            "categories": ["Monitor"],
            "people_count": 10,
            "min_rating": 4.5,
            "max_delivery_days": 5,
        },
        top_k=5,
        persist_dir=tmp_path,
    )

    assert [item["product_id"] for item in result.products] == ["monitor-dell"]
    assert result.products[0]["retrieval_score"] > 0
    assert result.products[0]["retrieval_reason"] == "vector_only"
    assert result.products[0]["retrieval_channels"] == ["vector"]
    assert result.products[0]["constraints_applied"]["categories"] == ["Monitor"]
    assert result.evidence["products"][0]["product_id"] == "monitor-dell"
    assert result.evidence["policies"][0]["id"] == "policy-approved-suppliers"
    assert result.evidence["suppliers"][0]["id"] == "supplier-contoso"


def test_retrieve_products_with_evidence_relaxes_filters_when_no_product_survives(monkeypatch, tmp_path):
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda: _MockEmptyBM25())
    rebuild_vector_collections(PRODUCTS, POLICIES, SUPPLIERS, persist_dir=tmp_path)

    result = retriever.retrieve_products_with_evidence(
        "Need monitors",
        {
            "categories": ["Monitor"],
            "people_count": 1000,
            "min_rating": 4.9,
            "max_delivery_days": 1,
        },
        top_k=3,
        persist_dir=tmp_path,
    )

    assert result.products
    assert result.evidence["constraints_relaxed"] is True
    assert result.products[0]["retrieval_reason"] == "hybrid_rrf_constraints_relaxed"


def test_retrieve_products_falls_back_to_local_index_when_vector_store_unavailable(monkeypatch):
    monkeypatch.setattr(retriever, "query_vector_collection", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        retriever,
        "load_local_index",
        lambda: [{"metadata": product, "text": build_product_document(product)} for product in PRODUCTS],
    )
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda: _MockEmptyBM25())

    products = retriever.retrieve_products(
        "Need monitor",
        {"categories": ["Monitor"], "people_count": 10, "max_delivery_days": 5},
        top_k=5,
    )

    assert len(products) > 0
    reasons = {p.get("retrieval_reason", "") for p in products}
    assert "bm25_synonym_recall" in reasons or "fallback_text_structured_filter" in reasons


def test_retrieve_products_with_evidence_adds_local_knowledge_when_vector_products_fallback(monkeypatch):
    monkeypatch.setattr(retriever, "query_vector_collection", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        retriever,
        "load_local_index",
        lambda: [{"metadata": product, "text": build_product_document(product)} for product in PRODUCTS],
    )
    monkeypatch.setattr(retriever, "load_procurement_policies", lambda: POLICIES)
    monkeypatch.setattr(retriever, "load_supplier_profiles", lambda: SUPPLIERS)
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda: _MockEmptyBM25())

    result = retriever.retrieve_products_with_evidence(
        "Need monitors quickly from an approved supplier",
        {"categories": ["Monitor"], "people_count": 10, "max_delivery_days": 5},
        top_k=5,
    )

    assert len(result.products) > 0
    assert result.evidence["retrieval_mode"] == "hybrid_vector_filter"
    assert len(result.evidence["products"]) > 0
    assert result.evidence["policies"][0]["id"] == "policy-approved-suppliers"
    assert result.evidence["suppliers"][0]["id"] == "supplier-contoso"


def test_chat_response_includes_retrieval_evidence(monkeypatch):
    monkeypatch.setattr(
        procurement_agent,
        "retrieve_products_with_evidence",
        lambda *_args, **_kwargs: retriever.RetrievalResult(
            products=[{**PRODUCTS[0], "retrieval_score": 0.91, "retrieval_reason": "vector_recall_structured_filter"}],
            evidence={
                "products": [{"product_id": "monitor-dell", "score": 0.91, "reason": "vector_recall_structured_filter"}],
                "policies": [{"id": "policy-approved-suppliers", "title": "Approved Supplier Policy", "score": 0.82}],
                "suppliers": [{"id": "supplier-contoso", "supplier": "Contoso Business Tech", "score": 0.79}],
                "constraints": {"categories": ["Monitor"]},
                "constraints_relaxed": False,
            },
        ),
    )

    response = TestClient(app).post(
        "/api/chat",
        json={
            "session_id": "evidence-session",
            "message": "Buy monitors for 3 people with fast delivery.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["retrieval_evidence"]["products"][0]["product_id"] == "monitor-dell"
    assert payload["retrieval_evidence"]["policies"][0]["id"] == "policy-approved-suppliers"
