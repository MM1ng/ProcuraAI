from __future__ import annotations

from app.core.database import SessionLocal, create_tables
from app.models.product import Product
from app.models.user import User
from app.services.product_service import load_products_from_csv


def seed_db() -> int:
    create_tables()
    products = load_products_from_csv()
    db = SessionLocal()
    try:
        db.merge(
            User(
                user_id="demo-user",
                name="Demo Procurement Manager",
                department="Operations",
                role="Requester",
                purchase_limit=10000,
            )
        )
        for product in products:
            db.merge(Product(**product))
        db.commit()
        return len(products)
    finally:
        db.close()


def main() -> None:
    count = seed_db()
    print(f"Seeded {count} products and demo user")


if __name__ == "__main__":
    main()
