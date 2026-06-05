from __future__ import annotations

from pydantic import BaseModel


class ProductRead(BaseModel):
    product_id: str
    name: str
    category: str
    brand: str
    price: float
    rating: float
    stock: int
    supplier: str
    delivery_days: int
    warranty_months: int
    compliance_level: str
    description: str
    tags: str


class ProductListResponse(BaseModel):
    items: list[ProductRead]
    total: int
