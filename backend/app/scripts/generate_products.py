from __future__ import annotations

import csv
import random

from app.agent.intent_parser import CATEGORIES
from app.core.config import DATA_DIR


BRANDS = {
    "Laptop": ["Lenovo", "Dell", "HP", "Asus", "Acer"],
    "Monitor": ["Dell", "LG", "Samsung", "BenQ", "ViewSonic"],
    "Keyboard": ["Logitech", "Keychron", "Microsoft", "Dell", "HP"],
    "Mouse": ["Logitech", "Microsoft", "Razer", "Dell", "Anker"],
    "Headset": ["Jabra", "Logitech", "Poly", "Anker", "Sony"],
    "Webcam": ["Logitech", "Anker", "Dell", "Razer", "Microsoft"],
    "Office Chair": ["Steelcase", "Herman Miller", "Branch", "Hon", "FlexiSpot"],
    "Docking Station": ["Anker", "Dell", "HP", "Lenovo", "CalDigit"],
    "Printer": ["HP", "Brother", "Canon", "Epson", "Xerox"],
    "Tablet": ["Apple", "Samsung", "Lenovo", "Microsoft", "Xiaomi"],
    "Router": ["Cisco", "TP-Link", "Netgear", "Ubiquiti", "Asus"],
    "External SSD": ["Samsung", "SanDisk", "Crucial", "Kingston", "WD"],
    "Projector": ["Epson", "BenQ", "ViewSonic", "Optoma", "Anker"],
    "Conference Speaker": ["Jabra", "Poly", "Logitech", "Anker", "Yealink"],
    "Standing Desk": ["FlexiSpot", "Uplift", "Vari", "Branch", "Ikea"],
}

PRICE_RANGES = {
    "Laptop": (520, 1650),
    "Monitor": (140, 680),
    "Keyboard": (18, 160),
    "Mouse": (12, 110),
    "Headset": (28, 260),
    "Webcam": (35, 240),
    "Office Chair": (120, 780),
    "Docking Station": (70, 360),
    "Printer": (90, 520),
    "Tablet": (180, 980),
    "Router": (55, 460),
    "External SSD": (45, 310),
    "Projector": (260, 1250),
    "Conference Speaker": (80, 430),
    "Standing Desk": (210, 920),
}

SUPPLIERS = [
    "Northwind Office Supply",
    "Contoso Business Tech",
    "Fabrikam Procurement",
    "Globex Workplace",
    "Initech Corporate Supply",
    "Umbrella Office Systems",
]

COMPLIANCE = ["Standard", "Business", "Enterprise", "ISO-Ready", "Eco-Preferred"]


def _product_name(category: str, brand: str, index: int) -> str:
    series = ["Essential", "Pro", "Plus", "Ultra", "Team", "Secure", "Ergo", "Fleet"]
    return f"{brand} {random.choice(series)} {category} {100 + index}"


def generate_products(count: int = 375) -> list[dict[str, object]]:
    random.seed(20260604)
    products: list[dict[str, object]] = []
    per_category = max(count // len(CATEGORIES), 20)
    product_number = 1

    for category in CATEGORIES:
        low, high = PRICE_RANGES[category]
        for index in range(per_category):
            brand = random.choice(BRANDS[category])
            price = round(random.uniform(low, high), 2)
            rating = round(random.uniform(3.8, 4.9), 1)
            stock = random.randint(8, 260)
            supplier = random.choice(SUPPLIERS)
            delivery_days = random.randint(1, 12)
            warranty = random.choice([12, 24, 36, 48])
            compliance = random.choice(COMPLIANCE)
            tags = [
                category.lower().replace(" ", "-"),
                "office",
                "enterprise",
                "fast-delivery" if delivery_days <= 5 else "standard-delivery",
                "high-rating" if rating >= 4.4 else "value",
            ]
            products.append(
                {
                    "product_id": f"P-{product_number:04d}",
                    "name": _product_name(category, brand, index),
                    "category": category,
                    "brand": brand,
                    "price": price,
                    "rating": rating,
                    "stock": stock,
                    "supplier": supplier,
                    "delivery_days": delivery_days,
                    "warranty_months": warranty,
                    "compliance_level": compliance,
                    "description": (
                        f"{brand} {category.lower()} for enterprise procurement, "
                        f"team onboarding and managed office equipment refreshes."
                    ),
                    "tags": ", ".join(tags),
                }
            )
            product_number += 1
    return products[:count]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = generate_products()
    path = DATA_DIR / "products.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {len(rows)} products at {path}")


if __name__ == "__main__":
    main()
