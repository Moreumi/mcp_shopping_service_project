"""Build a review-ranked, category-balanced demo catalog subset."""

from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path


QUOTAS = {
    "Shoes": 5000,
    "Clothing": 5500,
    "Bags": 2500,
    "Jewelry": 2000,
    "Accessories": 2000,
    "Watches": 1500,
    "Other": 1500,
}


def category_bucket(value: str | None) -> str:
    text = value or ""
    for bucket in QUOTAS:
        if bucket != "Other" and bucket.lower() in text.lower():
            return bucket
    return "Other"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/amazon_fashion/products.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/amazon_fashion/products_demo_20k.jsonl"))
    args = parser.parse_args()

    selected = []
    counts = Counter()
    with args.input.open("r", encoding="utf-8") as source:
        for line in source:
            product = json.loads(line)
            bucket = category_bucket(product.get("category"))
            if counts[bucket] >= QUOTAS[bucket]:
                continue
            selected.append((bucket, product))
            counts[bucket] += 1
            if all(counts[bucket] >= quota for bucket, quota in QUOTAS.items()):
                break

    shortages = {bucket: QUOTAS[bucket] - counts[bucket] for bucket in QUOTAS if counts[bucket] < QUOTAS[bucket]}
    if shortages:
        raise RuntimeError(f"catalog cannot satisfy category quotas: {shortages}")

    # Preserve source rank globally so the best-reviewed products are indexed
    # first and a stopped job is still a useful demo catalog.
    rank = {product["product_id"]: number for number, (_, product) in enumerate(selected)}
    selected.sort(key=lambda item: rank[item[1]["product_id"]])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as target:
        for _, product in selected:
            target.write(json.dumps(product, ensure_ascii=False, separators=(",", ":")) + "\n")

    print(json.dumps({
        "output": str(args.output.resolve()),
        "products": len(selected),
        "categories": dict(counts),
        "bytes": args.output.stat().st_size,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
