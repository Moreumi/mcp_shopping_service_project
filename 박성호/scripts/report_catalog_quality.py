"""Offline completeness report for the normalized Amazon Fashion catalog."""

from __future__ import annotations

import argparse
import json
from collections import Counter


FIELDS = (
    "title", "brand", "category", "audience", "bullet_points", "description",
    "color", "material", "style", "price", "image_url",
    "positive_review_evidence", "negative_review_evidence",
)


def report(path: str) -> dict:
    rows = 0
    present = Counter()
    categories = Counter()
    audiences = Counter()
    review_counts = []
    with open(path, "r", encoding="utf-8") as source:
        for line in source:
            product = json.loads(line)
            rows += 1
            for field in FIELDS:
                present[field] += product.get(field) not in (None, "", [])
            categories[product.get("category") or "missing"] += 1
            audiences[product.get("audience") or "missing"] += 1
            review_counts.append(int(product.get("review_count") or 0))
    return {
        "products": rows,
        "field_coverage": {
            field: {"count": present[field], "rate": round(present[field] / rows, 4)}
            for field in FIELDS
        },
        "categories": dict(categories.most_common()),
        "audiences": dict(audiences.most_common()),
        "review_count": {
            "minimum": min(review_counts),
            "maximum": max(review_counts),
            "average": round(sum(review_counts) / rows, 2),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="data/amazon_fashion/products.jsonl")
    args = parser.parse_args()
    print(json.dumps(report(args.catalog), ensure_ascii=False, indent=2))
