"""Read-only audit of DynamoDB order IDs against the Amazon Fashion catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.customer_context import get_orders


def catalog_ids(path: str) -> set[str]:
    ids = set()
    with Path(path).open("r", encoding="utf-8") as source:
        for line in source:
            product_id = json.loads(line).get("product_id")
            if product_id:
                ids.add(product_id)
    return ids


def audit(user_id: str, catalog_path: str) -> dict:
    known = catalog_ids(catalog_path)
    orders = get_orders(user_id).get("orders", [])
    ordered_ids = [order.get("product_id") for order in orders if order.get("product_id")]
    matched = [product_id for product_id in ordered_ids if product_id in known]
    missing = [product_id for product_id in ordered_ids if product_id not in known]
    return {
        "user_id": user_id,
        "catalog_products": len(known),
        "orders_with_product_id": len(ordered_ids),
        "matched_orders": len(matched),
        "match_rate": round(len(matched) / len(ordered_ids), 3) if ordered_ids else None,
        "missing_product_ids": missing[:20],
        "recommendation_exclusion_ready": bool(ordered_ids) and not missing,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", default="user_001")
    parser.add_argument("--catalog", default="data/amazon_fashion/products.jsonl")
    args = parser.parse_args()
    print(json.dumps(audit(args.user_id, args.catalog), ensure_ascii=False, indent=2))
