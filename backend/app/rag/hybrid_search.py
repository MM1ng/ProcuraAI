from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text_score(product: dict[str, Any], query: str) -> int:
    haystack = " ".join(
        str(product.get(field, ""))
        for field in ["name", "category", "brand", "supplier", "description", "tags"]
    ).lower()
    return sum(1 for token in set(query.lower().split()) if token.strip(".,") in haystack)


def filter_products_by_constraints(
    products: Iterable[dict[str, Any]],
    categories: list[str] | None = None,
    brand: str | None = None,
    max_price: float | None = None,
    min_rating: float | None = None,
    min_stock: int | None = None,
    max_delivery_days: int | None = None,
) -> list[dict[str, Any]]:
    category_set = {category.lower() for category in categories or []}
    brand_lower = brand.lower() if brand else None
    results: list[dict[str, Any]] = []
    for product in products:
        category = str(product.get("category", ""))
        product_brand = str(product.get("brand", ""))
        price = _as_float(product.get("price"))
        rating = _as_float(product.get("rating"))
        stock = _as_int(product.get("stock"))
        delivery_days = _as_int(product.get("delivery_days"))

        if category_set and category.lower() not in category_set:
            continue
        if brand_lower and product_brand.lower() != brand_lower:
            continue
        if max_price is not None and price > max_price:
            continue
        if min_rating is not None and rating < min_rating:
            continue
        if min_stock is not None and stock < min_stock:
            continue
        if max_delivery_days is not None and delivery_days > max_delivery_days:
            continue
        results.append(dict(product))
    return results


def search_products(
    products: Iterable[dict[str, Any]],
    query: str,
    categories: list[str] | None = None,
    brand: str | None = None,
    max_price: float | None = None,
    min_rating: float | None = None,
    min_stock: int | None = None,
    max_delivery_days: int | None = None,
    top_k: int = 12,
) -> list[dict[str, Any]]:
    filtered = filter_products_by_constraints(
        products,
        categories=categories,
        brand=brand,
        max_price=max_price,
        min_rating=min_rating,
        min_stock=min_stock,
        max_delivery_days=max_delivery_days,
    )
    ranked = sorted(
        filtered,
        key=lambda product: (
            -_text_score(product, query),
            -_as_float(product.get("rating")),
            _as_int(product.get("delivery_days"), 999),
            _as_float(product.get("price"), 999999),
        ),
    )
    return ranked[:top_k]
