"""Read-only checks to run before switching the application to OpenSearch v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify_local(path: str) -> dict:
    rows = 0
    unique_ids = set()
    bad_dimensions = 0
    with Path(path).open("r", encoding="utf-8") as source:
        for line in source:
            product = json.loads(line)
            rows += 1
            unique_ids.add(product.get("product_id"))
            bad_dimensions += len(product.get("embedding") or []) != 768
    return {
        "rows": rows,
        "unique_product_ids": len(unique_ids),
        "bad_dimensions": bad_dimensions,
        "ready": rows == 100_000 and len(unique_ids) == 100_000 and bad_dimensions == 0,
    }


def verify_remote(index: str) -> dict:
    from tools.search_products import client

    count = client.count(index=index, body={"query": {"match_all": {}}}, request_timeout=120)["count"]
    mapping = client.indices.get_mapping(index=index, request_timeout=120)
    dimension = mapping[index]["mappings"]["properties"]["embedding"]["dimension"]
    return {
        "index": index,
        "documents": count,
        "embedding_dimension": dimension,
        "ready": count == 100_000 and dimension == 768,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default="data/amazon_fashion/products_embedded.jsonl")
    parser.add_argument("--remote", action="store_true", help="Also query OpenSearch; never changes the index.")
    parser.add_argument("--index", default="products-amazon-fashion-v2")
    args = parser.parse_args()
    result = {"local": verify_local(args.file)}
    if args.remote:
        result["remote"] = verify_remote(args.index)
    print(json.dumps(result, indent=2))
