"""Build a 100k-product Amazon Fashion catalog from Amazon Reviews 2023.

The pipeline is streaming and keeps large product metadata in a temporary
SQLite database. Reviews are read twice: once for ranking and once for a small
amount of grounded review evidence for the selected products.
"""

from __future__ import annotations

import argparse
import ast
import heapq
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path


DEFAULT_REVIEW_PATH = "data/amazon_fashion/Amazon_Fashion.jsonl"
DEFAULT_META_PATH = "data/amazon_fashion/meta_Amazon_Fashion.jsonl"
DEFAULT_OUTPUT_PATH = "data/amazon_fashion/products.jsonl"


def iter_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as source:
        for line in source:
            try:
                yield json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue


def aggregate_reviews(path):
    stats = defaultdict(lambda: [0, 0.0, 0])
    for number, review in enumerate(iter_jsonl(path), start=1):
        product_id = review.get("parent_asin")
        if not product_id:
            continue
        rating = float(review.get("rating") or 0)
        item = stats[product_id]
        item[0] += 1
        item[1] += rating
        item[2] += int(bool(review.get("verified_purchase")))
        if number % 500_000 == 0:
            print(f"reviews aggregated: {number:,}", flush=True)
    return stats


def select_candidates(stats, candidate_limit=130_000, min_reviews=3):
    ranked = heapq.nlargest(
        candidate_limit,
        (
            (values[0], values[2], values[1] / values[0], product_id)
            for product_id, values in stats.items()
            if values[0] >= min_reviews
        ),
    )
    return {
        product_id: {
            "rank": rank,
            "review_count": count,
            "verified_review_count": verified,
            "average_rating": round(average, 2),
        }
        for rank, (count, verified, average, product_id) in enumerate(ranked)
    }


def parse_price(value):
    if isinstance(value, (int, float)):
        return float(value)
    if not value:
        return None
    match = re.search(r"\d+(?:,\d{3})*(?:\.\d+)?", str(value))
    return float(match.group(0).replace(",", "")) if match else None


def limited_strings(values, count=8, width=500):
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return [str(value).strip()[:width] for value in values[:count] if str(value).strip()]


def first_image(images):
    if not isinstance(images, list):
        return None
    for image in images:
        if isinstance(image, dict):
            for field in ("hi_res", "large", "thumb"):
                if image.get(field):
                    return image[field]
    return None


def parse_details(value):
    if isinstance(value, dict):
        details = value
    elif isinstance(value, str):
        try:
            details = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return {}
    else:
        return {}
    allowed = (
        "Department", "Fabric type", "Care instructions", "Origin",
        "Sole material", "Outer material", "Closure type", "Color",
        "Material", "Pattern", "Style",
    )
    return {key: str(details[key])[:300] for key in allowed if details.get(key)}


def infer_taxonomy(title, categories, details, brand=None):
    text = " ".join([str(title), *categories, *details.values()]).lower()
    groups = (
        ("Shoes", ("shoe", "sneaker", "sandal", "boot", "loafer", "slipper", "heel", "pump", "clog")),
        ("Watches", ("watch", "smartwatch")),
        ("Jewelry", ("necklace", "earring", "bracelet", "ring", "jewelry", "jewellery")),
        ("Bags", ("handbag", "backpack", "purse", "wallet", "tote", "duffel", "bag")),
        ("Clothing", ("shirt", "dress", "jacket", "coat", "pants", "jeans", "shorts", "skirt", "sweater", "hoodie", "sock", "underwear", "bra", "swimsuit")),
        ("Accessories", ("belt", "hat", "cap", "scarf", "glove", "sunglass", "tie")),
    )
    category = next((name for name, terms in groups if any(term in text for term in terms)), "Other")
    if any(term in text for term in ("women's", "womens", " women ", "ladies", "female")):
        audience = "Women"
    elif any(term in text for term in ("men's", " mens", " men ", "male")):
        audience = "Men"
    elif any(term in text for term in ("girl", "boy", "kid", "toddler", "child")):
        audience = "Kids"
    elif "unisex" in text:
        audience = "Unisex"
    else:
        audience = None
    colors = {
        "black": "Black", "white": "White", "red": "Red", "blue": "Blue",
        "brown": "Brown", "green": "Green", "pink": "Pink",
        # gray/grey both map to "Gray" - keeping them separate meant otherwise
        # identical products could end up with different stored color values
        # purely based on which spelling the title happened to use, which
        # then registered as *conflicting* colors at search time.
        "grey": "Gray", "gray": "Gray", "beige": "Beige", "navy": "Navy", "purple": "Purple",
        "yellow": "Yellow", "orange": "Orange", "gold": "Gold", "silver": "Silver",
    }
    # A color word inside the brand name itself (e.g. a "Red Bull" tee, a
    # "Black+Decker" tool belt) is not evidence of the item's actual color -
    # strip it out before scanning. When several color words appear in the
    # title, the apparel's own color tends to trail the brand/product name
    # ("... Team Hat (Flatbrim) Blue"), so prefer the last mention over a
    # fixed scan order.
    color_scan_text = text.replace(str(brand).lower(), " ") if brand else text
    color_matches = [
        (match.start(), value)
        for term, value in colors.items()
        for match in re.finditer(rf"\b{term}\b", color_scan_text)
    ]
    color = details.get("Color") or (
        max(color_matches, key=lambda item: item[0])[1] if color_matches else None
    )
    return category, audience, color


def clean_metadata(meta, review_stats):
    product_id = meta.get("parent_asin")
    title = str(meta.get("title") or "").strip()
    if not product_id or not title:
        return None
    categories = limited_strings(meta.get("categories"), count=10, width=120)
    features = limited_strings(meta.get("features"), count=10, width=500)
    descriptions = limited_strings(meta.get("description"), count=3, width=1000)
    details = parse_details(meta.get("details"))
    brand = str(meta.get("store") or "").strip()[:200] or None
    normalized_category, audience, color = infer_taxonomy(title, categories, details, brand=brand)
    return {
        "product_id": product_id,
        "dataset": "Amazon-Reviews-2023",
        "main_category": meta.get("main_category") or "Amazon Fashion",
        "title": title[:500],
        "brand": brand,
        "product_type": "Amazon_Fashion",
        "category": f"Amazon Fashion > {normalized_category}",
        "categories": list(dict.fromkeys([*categories, normalized_category])),
        "audience": audience,
        "bullet_points": features,
        "description": " ".join(descriptions),
        "color": color,
        "material": details.get("Material") or details.get("Fabric type") or details.get("Outer material"),
        "style": details.get("Style") or details.get("Pattern"),
        "price": parse_price(meta.get("price")),
        "average_rating": review_stats["average_rating"],
        "review_count": review_stats["review_count"],
        "verified_review_count": review_stats["verified_review_count"],
        "image_url": first_image(meta.get("images")),
        "details": details,
        "bought_together": limited_strings(meta.get("bought_together"), count=10, width=20),
    }


def stage_metadata(meta_path, candidates, database_path):
    connection = sqlite3.connect(database_path)
    connection.execute("CREATE TABLE IF NOT EXISTS products (rank INTEGER PRIMARY KEY, product_id TEXT UNIQUE, document TEXT NOT NULL)")
    pending = []
    for number, meta in enumerate(iter_jsonl(meta_path), start=1):
        product_id = meta.get("parent_asin")
        stats = candidates.get(product_id)
        if not stats:
            continue
        product = clean_metadata(meta, stats)
        if not product:
            continue
        pending.append((stats["rank"], product_id, json.dumps(product, ensure_ascii=False, separators=(",", ":"))))
        if len(pending) >= 1000:
            connection.executemany("INSERT OR REPLACE INTO products VALUES (?, ?, ?)", pending)
            connection.commit()
            pending.clear()
        if number % 250_000 == 0:
            print(f"metadata scanned: {number:,}", flush=True)
    if pending:
        connection.executemany("INSERT OR REPLACE INTO products VALUES (?, ?, ?)", pending)
        connection.commit()
    return connection


def _review_evidence(review):
    text = " ".join(str(review.get(field) or "").strip() for field in ("title", "text")).strip()
    return {
        "rating": float(review.get("rating") or 0),
        "helpful_vote": int(review.get("helpful_vote") or 0),
        "verified_purchase": bool(review.get("verified_purchase")),
        "text": text[:500],
    }


def collect_evidence(review_path, selected_ids, per_sentiment=2):
    evidence = {product_id: {"positive": [], "negative": []} for product_id in selected_ids}
    for number, review in enumerate(iter_jsonl(review_path), start=1):
        product_id = review.get("parent_asin")
        if product_id not in evidence:
            continue
        item = _review_evidence(review)
        if not item["text"]:
            continue
        sentiment = "positive" if item["rating"] >= 4 else "negative" if item["rating"] <= 2 else None
        if not sentiment:
            continue
        bucket = evidence[product_id][sentiment]
        bucket.append(item)
        bucket.sort(key=lambda value: (value["verified_purchase"], value["helpful_vote"], len(value["text"])), reverse=True)
        del bucket[per_sentiment:]
        if number % 500_000 == 0:
            print(f"review evidence scanned: {number:,}", flush=True)
    return evidence


def build_catalog(review_path, meta_path, output_path, limit=100_000, candidate_limit=130_000, min_reviews=3):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    database = output.with_suffix(".sqlite")
    if database.exists():
        database.unlink()

    stats = aggregate_reviews(review_path)
    candidates = select_candidates(stats, candidate_limit, min_reviews)
    del stats
    connection = stage_metadata(meta_path, candidates, database)
    rows = list(connection.execute("SELECT rank, product_id FROM products ORDER BY rank LIMIT ?", (limit,)))
    if len(rows) < limit:
        raise RuntimeError(f"Only {len(rows):,} selected products have metadata; increase --candidate-limit.")
    selected_ids = {row[1] for row in rows}
    evidence = collect_evidence(review_path, selected_ids)

    written = 0
    minimum_count = None
    with output.open("w", encoding="utf-8", newline="\n") as target:
        for _, product_id, document in connection.execute(
            "SELECT rank, product_id, document FROM products ORDER BY rank LIMIT ?", (limit,)
        ):
            product = json.loads(document)
            product["positive_review_evidence"] = evidence[product_id]["positive"]
            product["negative_review_evidence"] = evidence[product_id]["negative"]
            target.write(json.dumps(product, ensure_ascii=False, separators=(",", ":")) + "\n")
            written += 1
            minimum_count = product["review_count"]

    connection.close()
    database.unlink(missing_ok=True)
    result = {
        "products": written,
        "minimum_review_count": minimum_count,
        "output": str(output),
        "bytes": output.stat().st_size,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", default=DEFAULT_REVIEW_PATH)
    parser.add_argument("--metadata", default=DEFAULT_META_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--limit", type=int, default=100_000)
    parser.add_argument("--candidate-limit", type=int, default=130_000)
    parser.add_argument("--min-reviews", type=int, default=3)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_catalog(args.reviews, args.metadata, args.output, args.limit, args.candidate_limit, args.min_reviews)
