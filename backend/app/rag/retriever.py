from __future__ import annotations

from typing import Any

from app.rag.hybrid_search import search_products
from app.rag.vector_store import load_local_index
from app.services.product_service import load_products_from_csv


def retrieve_products(query: str, intent: dict[str, Any], top_k: int = 12) -> list[dict[str, Any]]:
    index = load_local_index()
    products = [row["metadata"] for row in index] if index else load_products_from_csv()
    people_count = int(intent.get("people_count") or 1)
    replacement_brand = intent.get("replacement_brand")
    replacement_categories = intent.get("replacement_categories") or []
    if intent.get("revision_intent") == "replace_product" and replacement_brand and replacement_categories:
        preserved_categories = [
            category
            for category in intent.get("categories") or []
            if category not in replacement_categories
        ]
        replacement_products = search_products(
            products=products,
            query=query,
            categories=replacement_categories,
            brand=str(replacement_brand),
            min_rating=intent.get("min_rating"),
            min_stock=people_count,
            max_delivery_days=intent.get("max_delivery_days"),
            top_k=top_k,
        )
        preserved_products = search_products(
            products=products,
            query=query,
            categories=preserved_categories,
            min_rating=intent.get("min_rating"),
            min_stock=people_count,
            max_delivery_days=intent.get("max_delivery_days"),
            top_k=top_k,
        )
        return [*replacement_products, *preserved_products][:top_k]

    return search_products(
        products=products,
        query=query,
        categories=intent.get("categories"),
        min_rating=intent.get("min_rating"),
        min_stock=people_count,
        max_delivery_days=intent.get("max_delivery_days"),
        top_k=top_k,
    )
