"""Method A: resumably embed all catalog images and update OpenSearch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opensearchpy.helpers import bulk

from tools.search_products import INDEX_NAME, client
from tools.siglip_vision import MODEL_ID, image_features_batch, runtime_status


DEFAULT_INPUT = ROOT / "data" / "amazon_fashion" / "products.jsonl"
DEFAULT_CHECKPOINT = ROOT / "data" / "amazon_fashion" / "siglip_method_a.checkpoint.json"
DEFAULT_ERRORS = ROOT / "data" / "amazon_fashion" / "siglip_method_a.errors.jsonl"
DIMENSION = 768


def load_checkpoint(path: Path) -> dict:
    if not path.exists():
        return {"line": 0, "indexed": 0, "failed": 0}
    return json.loads(path.read_text(encoding="utf-8"))


def save_checkpoint(path: Path, state: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def ensure_mapping() -> None:
    mapping = client.indices.get_mapping(index=INDEX_NAME)[INDEX_NAME]["mappings"].get("properties", {})
    existing = mapping.get("image_embedding")
    if existing:
        if existing.get("dimension") != DIMENSION:
            raise RuntimeError(f"image_embedding dimension is {existing.get('dimension')}, expected {DIMENSION}")
        return
    client.indices.put_mapping(
        index=INDEX_NAME,
        body={
            "properties": {
                "image_embedding": {
                    "type": "knn_vector",
                    "dimension": DIMENSION,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "faiss",
                        "parameters": {"ef_construction": 128, "m": 16},
                    },
                },
                "image_embedding_model": {"type": "keyword", "index": False},
            }
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERRORS)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="0 processes the full remaining catalog")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    state = load_checkpoint(args.checkpoint)
    print(json.dumps({
        "mode": "apply" if args.apply else "dry_run",
        "model": MODEL_ID,
        "index": INDEX_NAME,
        "input": str(args.input),
        "resume": state,
        "runtime": runtime_status(),
    }, ensure_ascii=False), flush=True)
    if not args.apply:
        return 0

    ensure_mapping()
    started = time.time()
    processed_this_run = 0
    batch: list[tuple[int, dict]] = []

    def process_batch(items: list[tuple[int, dict]]) -> None:
        nonlocal processed_this_run, state
        urls = [product.get("image_url") for _, product in items if product.get("image_url")]
        features, errors = image_features_batch(urls, workers=args.workers)
        actions = []
        failed_rows = []
        for line_number, product in items:
            product_id = product.get("product_id")
            image_url = product.get("image_url")
            vector = features.get(image_url) if image_url else None
            if product_id and vector is not None:
                actions.append({
                    "_op_type": "update",
                    "_index": INDEX_NAME,
                    "_id": product_id,
                    "doc": {"image_embedding": vector.tolist(), "image_embedding_model": MODEL_ID},
                })
            else:
                failed_rows.append({
                    "line": line_number,
                    "product_id": product_id,
                    "image_url": image_url,
                    "error": errors.get(image_url, "missing_product_id_or_image"),
                })
        if actions:
            succeeded, bulk_errors = bulk(
                client,
                actions,
                chunk_size=args.batch_size,
                request_timeout=120,
                raise_on_error=False,
                refresh=False,
            )
            state["indexed"] += succeeded
            if bulk_errors:
                failed_rows.extend({"error": error} for error in bulk_errors)
        if failed_rows:
            args.errors.parent.mkdir(parents=True, exist_ok=True)
            with args.errors.open("a", encoding="utf-8") as handle:
                for row in failed_rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            state["failed"] += len(failed_rows)
        state["line"] = items[-1][0]
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        state["elapsed_seconds"] = round(time.time() - started, 1)
        processed_this_run += len(items)
        save_checkpoint(args.checkpoint, state)
        print(json.dumps({"progress": state, "processed_this_run": processed_this_run}), flush=True)

    with args.input.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line_number <= state["line"]:
                continue
            if args.limit and processed_this_run + len(batch) >= args.limit:
                break
            try:
                product = json.loads(line)
            except json.JSONDecodeError as error:
                state["failed"] += 1
                state["line"] = line_number
                with args.errors.open("a", encoding="utf-8") as error_handle:
                    error_handle.write(json.dumps({"line": line_number, "error": str(error)}) + "\n")
                continue
            batch.append((line_number, product))
            if len(batch) >= args.batch_size:
                process_batch(batch)
                batch = []
        if batch:
            process_batch(batch)

    print(json.dumps({"complete": True, "state": state}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
