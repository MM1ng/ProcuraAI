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


def test_retrieve_products_with_evidence_uses_vector_top_k_and_structured_filters(tmp_path):
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
    assert result.products[0]["retrieval_reason"] == "vector_recall_structured_filter"
    assert result.products[0]["constraints_applied"]["categories"] == ["Monitor"]
    assert result.evidence["products"][0]["product_id"] == "monitor-dell"
    assert result.evidence["policies"][0]["id"] == "policy-approved-suppliers"
    assert result.evidence["suppliers"][0]["id"] == "supplier-contoso"


def test_retrieve_products_with_evidence_relaxes_filters_when_no_product_survives(tmp_path):
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
    assert result.products[0]["retrieval_reason"] == "vector_recall_constraints_relaxed"


def test_retrieve_products_falls_back_to_local_index_when_vector_store_unavailable(monkeypatch):
    monkeypatch.setattr(retriever, "query_vector_collection", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        retriever,
        "load_local_index",
        lambda: [{"metadata": product, "text": build_product_document(product)} for product in PRODUCTS],
    )

    products = retriever.retrieve_products(
        "Need monitor",
        {"categories": ["Monitor"], "people_count": 10, "max_delivery_days": 5},
        top_k=5,
    )

    assert [item["product_id"] for item in products] == ["monitor-dell"]
    assert products[0]["retrieval_reason"] == "fallback_text_structured_filter"


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
