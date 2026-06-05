from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR


PRODUCTS_CSV = DATA_DIR / "products.csv"


def _coerce_product(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": str(row.get("product_id", "")),
        "name": str(row.get("name", "")),
        "category": str(row.get("category", "")),
        "brand": str(row.get("brand", "")),
        "price": float(row.get("price", 0) or 0),
        "rating": float(row.get("rating", 0) or 0),
        "stock": int(float(row.get("stock", 0) or 0)),
        "supplier": str(row.get("supplier", "")),
        "delivery_days": int(float(row.get("delivery_days", 0) or 0)),
        "warranty_months": int(float(row.get("warranty_months", 0) or 0)),
        "compliance_level": str(row.get("compliance_level", "")),
        "description": str(row.get("description", "")),
        "tags": str(row.get("tags", "")),
    }


def load_products_from_csv(path: Path = PRODUCTS_CSV) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [_coerce_product(row) for row in reader]


def list_products(
    category: str | None = None,
    search: str | None = None,
    min_rating: float | None = None,
    max_price: float | None = None,
    min_stock: int | None = None,
) -> list[dict[str, Any]]:
    products = load_products_from_csv()
    if category:
        products = [product for product in products if product["category"].lower() == category.lower()]
    if search:
        query = search.lower()
        products = [
            product
            for product in products
            if query
            in " ".join(
                [
                    product["name"],
                    product["category"],
                    product["brand"],
                    product["supplier"],
                    product["description"],
                    product["tags"],
                ]
            ).lower()
        ]
    if min_rating is not None:
        products = [product for product in products if product["rating"] >= min_rating]
    if max_price is not None:
        products = [product for product in products if product["price"] <= max_price]
    if min_stock is not None:
        products = [product for product in products if product["stock"] >= min_stock]
    return products


def get_product(product_id: str) -> dict[str, Any] | None:
    for product in load_products_from_csv():
        if product["product_id"] == product_id:
            return product
    return None


def product_context(product: dict[str, Any]) -> str:
    return (
        f"{product.get('name')} by {product.get('brand')} is a {product.get('category')} "
        f"priced at ${product.get('price')} with rating {product.get('rating')}, "
        f"stock {product.get('stock')}, delivery in {product.get('delivery_days')} days. "
        f"Tags: {product.get('tags')}. {product.get('description')}"
    )
