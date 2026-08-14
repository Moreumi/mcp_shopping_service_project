"""Create read-only DynamoDB order suggestions from the active local catalog."""

from __future__ import annotations

import argparse
import json


def suggestions(path: str, user_id: str, limit: int) -> list[dict]:
    selected = []
    seen_categories = set()
    with open(path, "r", encoding="utf-8") as source:
        for line in source:
            product = json.loads(line)
            category = product.get("category")
            if not product.get("product_id") or not product.get("title") or category in seen_categories:
                continue
            selected.append({
                "user_id": user_id,
                "product_id": product["product_id"],
                "title": product["title"],
                "purchase_date": f"2026-0{max(1, 8-len(selected))}-01",
                "status": "delivered",
            })
            seen_categories.add(category)
            if len(selected) >= limit:
                break
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="data/amazon_fashion/products.jsonl")
    parser.add_argument("--user-id", default="user_001")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps({"orders": suggestions(args.catalog, args.user_id, args.limit)}, ensure_ascii=False, indent=2))
