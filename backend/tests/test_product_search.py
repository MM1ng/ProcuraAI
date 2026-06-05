from app.rag.hybrid_search import search_products


def test_search_products_filters_and_ranks_by_constraints():
    products = [
        {
            "product_id": "P-001",
            "name": "Budget Headset",
            "category": "Headset",
            "price": 42.0,
            "rating": 4.0,
            "stock": 100,
            "delivery_days": 2,
            "tags": "budget audio",
            "description": "Entry headset",
        },
        {
            "product_id": "P-002",
            "name": "Fast Rated Headset",
            "category": "Headset",
            "price": 65.0,
            "rating": 4.7,
            "stock": 30,
            "delivery_days": 2,
            "tags": "remote meeting",
            "description": "Noise cancelling headset",
        },
        {
            "product_id": "P-003",
            "name": "Slow Premium Headset",
            "category": "Headset",
            "price": 80.0,
            "rating": 4.8,
            "stock": 30,
            "delivery_days": 9,
            "tags": "premium",
            "description": "Premium headset",
        },
    ]

    results = search_products(
        products=products,
        query="need fast delivery headset for remote interns",
        categories=["Headset"],
        max_price=90,
        min_rating=4.2,
        min_stock=20,
        max_delivery_days=5,
        top_k=3,
    )

    assert [item["product_id"] for item in results] == ["P-002"]


def test_search_products_can_find_multiple_requested_categories():
    products = [
        {
            "product_id": "P-010",
            "name": "Office Keyboard",
            "category": "Keyboard",
            "price": 35.0,
            "rating": 4.4,
            "stock": 80,
            "delivery_days": 3,
            "tags": "typing office",
            "description": "Keyboard for office kits",
        },
        {
            "product_id": "P-011",
            "name": "Office Mouse",
            "category": "Mouse",
            "price": 20.0,
            "rating": 4.5,
            "stock": 90,
            "delivery_days": 3,
            "tags": "office",
            "description": "Mouse for office kits",
        },
    ]

    results = search_products(
        products=products,
        query="keyboard mouse equipment",
        categories=["Keyboard", "Mouse"],
        min_stock=10,
        top_k=5,
    )

    assert {item["category"] for item in results} == {"Keyboard", "Mouse"}
