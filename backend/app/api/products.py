from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.product import ProductListResponse, ProductRead
from app.services.product_service import get_product, list_products


router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=ProductListResponse)
def get_products(
    category: str | None = None,
    search: str | None = None,
    min_rating: float | None = Query(default=None, ge=0, le=5),
    max_price: float | None = Query(default=None, ge=0),
    min_stock: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ProductListResponse:
    products = list_products(
        category=category,
        search=search,
        min_rating=min_rating,
        max_price=max_price,
        min_stock=min_stock,
    )
    window = products[offset : offset + limit]
    return ProductListResponse(items=[ProductRead(**product) for product in window], total=len(products))


@router.get("/{product_id}", response_model=ProductRead)
def get_product_detail(product_id: str) -> ProductRead:
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductRead(**product)
