"""Verify the configured OpenSearch index without printing review bodies."""

import argparse
import json

from tools.hybrid_search import hybrid_search
from tools.search_products import INDEX_NAME, client, search_products


def summarize(products):
    fields = (
        "product_id", "title", "brand", "category", "audience", "color",
        "price", "average_rating", "review_count", "image_url",
    )
    return [{key: product.get(key) for key in fields} for product in products]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="black women's shoes")
    args = parser.parse_args()
    print(json.dumps({"index": INDEX_NAME, "count": client.count(index=INDEX_NAME)["count"]}, indent=2))
    keyword = search_products(
        query=args.query,
        size=3,
        category="Shoes",
        audience="Women",
        required_color="Black",
    )
    hybrid = hybrid_search(
        query=args.query,
        size=3,
        category="Shoes",
        audience="Women",
        required_color="Black",
    )
    print(json.dumps({"keyword": summarize(keyword), "hybrid": summarize(hybrid)}, ensure_ascii=True, indent=2))
