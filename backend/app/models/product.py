from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    brand: Mapped[str] = mapped_column(String(100), index=True)
    price: Mapped[float] = mapped_column(Float)
    rating: Mapped[float] = mapped_column(Float)
    stock: Mapped[int] = mapped_column(Integer)
    supplier: Mapped[str] = mapped_column(String(120))
    delivery_days: Mapped[int] = mapped_column(Integer)
    warranty_months: Mapped[int] = mapped_column(Integer)
    compliance_level: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(Text)
