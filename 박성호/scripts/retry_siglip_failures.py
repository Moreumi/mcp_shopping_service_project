"""Retry transient image download failures and update OpenSearch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opensearchpy.helpers import bulk

from tools.search_products import INDEX_NAME, client
from tools.siglip_vision import MODEL_ID, image_features_batch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--errors", type=Path, default=Path("data/amazon_fashion/siglip_method_a_20k.errors.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("data/amazon_fashion/siglip_method_a_20k.retry.json"))
    args = parser.parse_args()

    failed = {}
    for line in args.errors.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("product_id") and row.get("image_url"):
            failed[row["product_id"]] = row["image_url"]

    features, errors = image_features_batch(list(failed.values()), workers=2)
    actions = []
    for product_id, url in failed.items():
        vector = features.get(url)
        if vector is not None:
            actions.append({
                "_op_type": "update",
                "_index": INDEX_NAME,
                "_id": product_id,
                "doc": {"image_embedding": vector.tolist(), "image_embedding_model": MODEL_ID},
            })
    indexed = 0
    bulk_errors = []
    if actions:
        indexed, bulk_errors = bulk(client, actions, request_timeout=120, raise_on_error=False, refresh=True)
    report = {
        "requested": len(failed),
        "indexed": indexed,
        "download_errors": errors,
        "bulk_errors": bulk_errors,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if indexed == len(failed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
