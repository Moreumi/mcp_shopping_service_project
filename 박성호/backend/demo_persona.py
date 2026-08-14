"""Stable demo persona shared by local fallback and DynamoDB seeding."""

DEMO_PERSONA = {
    "display_name": "Minjun",
    "preferred_gender": "Men",
    "shopping_style": "미니멀한 스포티 캐주얼",
    "preferred_styles": ["Minimal", "Sporty casual"],
    "preferred_categories": ["Shoes", "Jackets", "Bags"],
    "preferred_colors": ["Black", "Navy", "Gray", "White"],
    "preferred_brands": ["ASICS", "New Balance", "Nike"],
    "preferred_use_cases": ["Daily commute", "Walking", "Light workouts"],
    "preferred_fit": "Regular or relaxed fit",
    "budget_range": "$40-$120",
    "avoid_features": ["Neon colors", "Kids products", "High heels"],
}


# Every product below exists in data/amazon_fashion/products_demo_20k.jsonl.
DEMO_ORDERS = [
    {
        "user_id": "user_001",
        "order_id": "order_001",
        "purchase_date": "2026-08-03",
        "product_id": "B087SWVC6L",
        "title": "Shoes for Crews Men's Cambridge Sneaker",
        "brand": "Shoes for Crews",
        "category": "Shoes",
        "price": 66.48,
        "status": "Delivered",
    },
    {
        "user_id": "user_001",
        "order_id": "order_002",
        "purchase_date": "2026-07-12",
        "product_id": "B01N9GSNY6",
        "title": "MAGCOMSEN Men's Water Resistant Winter Jacket",
        "brand": "MAGCOMSEN",
        "category": "Jackets",
        "price": 61.98,
        "status": "Delivered",
    },
    {
        "user_id": "user_001",
        "order_id": "order_003",
        "purchase_date": "2026-06-21",
        "product_id": "B07L5DPJ82",
        "title": "Augus Leather Messenger Laptop Bag",
        "brand": "Augus",
        "category": "Bags",
        "price": 108.65,
        "status": "Delivered",
    },
]
