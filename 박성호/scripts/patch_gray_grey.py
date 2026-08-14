"""One-off patch: unify color="Grey" -> color="Gray" so the two spellings
stop registering as *conflicting* colors in the hybrid_search hard-check
(same remediation pattern as scripts/patch_color_taxonomy.py's Red Bull fix).

Re-embeds and re-uploads only the affected subset; does not touch
OpenSearch's image_embedding (partial `update`, not `index`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import ollama
from opensearchpy.helpers import bulk

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.embed_catalog import MODEL_NAME, EMBEDDING_DIMENSION, make_product_text
from tools.search_products import INDEX_NAME, client

PRODUCTS_PATH = ROOT / "data" / "amazon_fashion" / "products.jsonl"
EMBEDDED_PATH = ROOT / "data" / "amazon_fashion" / "products_embedded.jsonl"
EMBED_BATCH_SIZE = 128


def patch_products_jsonl() -> set[str]:
    products = []
    changed_ids = set()
    with PRODUCTS_PATH.open("r", encoding="utf-8") as source:
        for line in source:
            product = json.loads(line)
            if product.get("color") == "Grey":
                product["color"] = "Gray"
                changed_ids.add(product["product_id"])
            products.append(product)

    with PRODUCTS_PATH.open("w", encoding="utf-8", newline="\n") as target:
        for product in products:
            target.write(json.dumps(product, ensure_ascii=False, default=str) + "\n")

    print(f"products.jsonl rewritten: {len(changed_ids)} colors changed (Grey -> Gray)")
    return changed_ids


def reembed_changed(changed_ids: set[str], products_by_id: dict[str, dict]) -> dict[str, list[float]]:
    ids = list(changed_ids)
    embeddings = {}
    for start in range(0, len(ids), EMBED_BATCH_SIZE):
        batch_ids = ids[start:start + EMBED_BATCH_SIZE]
        texts = [make_product_text(products_by_id[pid]) for pid in batch_ids]
        response = ollama.embed(model=MODEL_NAME, input=texts)
        batch_embeddings = response["embeddings"]
        if len(batch_embeddings) != len(batch_ids):
            raise ValueError("Embedding result count does not match input count.")
        for pid, embedding in zip(batch_ids, batch_embeddings):
            if len(embedding) != EMBEDDING_DIMENSION:
                raise ValueError(f"Unexpected embedding dimension for {pid}: {len(embedding)}")
            embeddings[pid] = embedding
        print(f"re-embedded {min(start + EMBED_BATCH_SIZE, len(ids))}/{len(ids)}", flush=True)
    return embeddings


def patch_products_embedded_jsonl(changed_ids: set[str], embeddings: dict[str, list[float]]) -> None:
    rows = []
    with EMBEDDED_PATH.open("r", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            pid = row["product_id"]
            if pid in changed_ids:
                row["color"] = "Gray"
                row["embedding"] = embeddings[pid]
            rows.append(row)

    with EMBEDDED_PATH.open("w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    print(f"products_embedded.jsonl rewritten: {len(changed_ids)} rows patched")


def push_partial_updates(changed_ids: set[str], embeddings: dict[str, list[float]]) -> None:
    def actions():
        for pid in changed_ids:
            yield {
                "_op_type": "update",
                "_index": INDEX_NAME,
                "_id": pid,
                "doc": {"color": "Gray", "embedding": embeddings[pid]},
            }

    success, errors = bulk(client, actions(), chunk_size=500, raise_on_error=False, request_timeout=180)
    print(f"OpenSearch partial updates: success={success}, errors={len(errors)}")
    if errors:
        print(json.dumps(errors[:5], ensure_ascii=False, default=str)[:3000])
    client.indices.refresh(index=INDEX_NAME, request_timeout=120)


def main() -> None:
    changed_ids = patch_products_jsonl()
    if not changed_ids:
        print("no colors changed, nothing to re-embed or upload")
        return

    products_by_id = {}
    with PRODUCTS_PATH.open("r", encoding="utf-8") as source:
        for line in source:
            product = json.loads(line)
            if product["product_id"] in changed_ids:
                products_by_id[product["product_id"]] = product

    embeddings = reembed_changed(changed_ids, products_by_id)
    patch_products_embedded_jsonl(changed_ids, embeddings)
    push_partial_updates(changed_ids, embeddings)


if __name__ == "__main__":
    main()
