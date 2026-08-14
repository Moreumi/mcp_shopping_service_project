"""One-off patch: retag products whose `color` field was mis-inferred from
brand/product-name text (e.g. a black "Red Bull" tee tagged color=Red), then
re-embed and re-upload only the affected subset.

Root cause fixed in build_amazon_fashion.infer_taxonomy(): the old color
guesser scanned the whole title with no brand awareness and picked the
first color word in a fixed priority order, so a brand name that happens
to contain a color word could win outright, and a title with two color
words always picked the same one regardless of position.

This script does NOT touch the other ~94% of the catalog, and does NOT
touch OpenSearch's image_embedding field - it uses a partial `update`
(not `index`) so SigLIP vectors already computed for these products are
preserved untouched.
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

from scripts.build_amazon_fashion import infer_taxonomy
from scripts.embed_catalog import MODEL_NAME, EMBEDDING_DIMENSION, make_product_text
from tools.search_products import INDEX_NAME, client

PRODUCTS_PATH = ROOT / "data" / "amazon_fashion" / "products.jsonl"
EMBEDDED_PATH = ROOT / "data" / "amazon_fashion" / "products_embedded.jsonl"
EMBED_BATCH_SIZE = 128


def recompute_color(product: dict) -> str | None:
    title = product.get("title") or ""
    categories = product.get("categories") or []
    details = product.get("details") or {}
    brand = product.get("brand")
    _, _, color = infer_taxonomy(title, categories, details, brand=brand)
    return color


def patch_products_jsonl() -> dict[str, dict]:
    products = []
    changed = {}
    with PRODUCTS_PATH.open("r", encoding="utf-8") as source:
        for line in source:
            product = json.loads(line)
            new_color = recompute_color(product)
            old_color = product.get("color")
            if new_color != old_color:
                changed[product["product_id"]] = {"old": old_color, "new": new_color}
                product["color"] = new_color
            products.append(product)

    with PRODUCTS_PATH.open("w", encoding="utf-8", newline="\n") as target:
        for product in products:
            target.write(json.dumps(product, ensure_ascii=False, default=str) + "\n")

    print(f"products.jsonl rewritten: {len(changed)} colors changed out of {len(products)}")
    return changed


def reembed_changed(changed: dict[str, dict], products_by_id: dict[str, dict]) -> dict[str, list[float]]:
    ids = list(changed.keys())
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


def patch_products_embedded_jsonl(changed: dict[str, dict], embeddings: dict[str, list[float]]) -> None:
    rows = []
    with EMBEDDED_PATH.open("r", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            pid = row["product_id"]
            if pid in changed:
                row["color"] = changed[pid]["new"]
                row["embedding"] = embeddings[pid]
            rows.append(row)

    with EMBEDDED_PATH.open("w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    print(f"products_embedded.jsonl rewritten: {len(changed)} rows patched")


def push_partial_updates(changed: dict[str, dict], embeddings: dict[str, list[float]]) -> None:
    def actions():
        for pid in changed:
            yield {
                "_op_type": "update",
                "_index": INDEX_NAME,
                "_id": pid,
                "doc": {
                    "color": changed[pid]["new"],
                    "embedding": embeddings[pid],
                },
            }

    success, errors = bulk(client, actions(), chunk_size=500, raise_on_error=False, request_timeout=180)
    print(f"OpenSearch partial updates: success={success}, errors={len(errors)}")
    if errors:
        print(json.dumps(errors[:5], ensure_ascii=False, default=str)[:3000])
    client.indices.refresh(index=INDEX_NAME, request_timeout=120)


def main() -> None:
    changed = patch_products_jsonl()
    if not changed:
        print("no colors changed, nothing to re-embed or upload")
        return

    products_by_id = {}
    with PRODUCTS_PATH.open("r", encoding="utf-8") as source:
        for line in source:
            product = json.loads(line)
            if product["product_id"] in changed:
                products_by_id[product["product_id"]] = product

    embeddings = reembed_changed(changed, products_by_id)
    patch_products_embedded_jsonl(changed, embeddings)
    push_partial_updates(changed, embeddings)


if __name__ == "__main__":
    main()
