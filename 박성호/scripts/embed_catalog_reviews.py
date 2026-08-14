"""Create extractive review summaries and review vectors, then patch OpenSearch.

This is fully local: nomic-embed-text runs through Ollama and no OpenAI API is
called. The checkpoint is the input line number, making the job resumable.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

import ollama
from opensearchpy.helpers import bulk

from tools.search_products import client


MODEL = "nomic-embed-text"
DIMENSION = 768


def _sentence(text: str, limit: int = 220) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0][:limit].rstrip(" ,;:-")


def build_review_summary(product: dict) -> list[str]:
    lines: list[str] = []
    for label, field in (("Positive", "positive_review_evidence"), ("Caution", "negative_review_evidence")):
        values = product.get(field) or []
        excerpts = []
        for value in values[:2]:
            text = value.get("text") if isinstance(value, dict) else value
            if excerpt := _sentence(text):
                excerpts.append(excerpt)
        if excerpts:
            lines.append(f"{label}: {' / '.join(excerpts)}"[:440])
    return lines[:3]


def ensure_mapping(index: str) -> None:
    properties = client.indices.get_mapping(index=index)[index]["mappings"].get("properties", {})
    additions = {}
    if "review_summary" not in properties:
        additions["review_summary"] = {"type": "text", "index": False}
    if "review_embedding" not in properties:
        additions["review_embedding"] = {
            "type": "knn_vector",
            "dimension": DIMENSION,
            "method": {
                "name": "hnsw", "space_type": "cosinesimil", "engine": "faiss",
                "parameters": {"ef_construction": 128, "m": 16},
            },
        }
    if additions:
        client.indices.put_mapping(index=index, body={"properties": additions}, request_timeout=120)


def run(input_path: Path, index: str, checkpoint_path: Path, batch_size: int) -> None:
    ensure_mapping(index)
    completed = 0
    if checkpoint_path.exists():
        completed = int(json.loads(checkpoint_path.read_text(encoding="utf-8")).get("completed_lines", 0))

    batch: list[tuple[str, list[str]]] = []

    def flush(rows: list[tuple[str, list[str]]], line_number: int) -> None:
        summaries = ["\n".join(summary) or "No review evidence available." for _, summary in rows]
        vectors = ollama.embed(model=MODEL, input=summaries, keep_alive="30m")["embeddings"]
        if any(len(vector) != DIMENSION for vector in vectors):
            raise ValueError("Unexpected review embedding dimension")
        actions = [
            {
                "_op_type": "update", "_index": index, "_id": product_id,
                "doc": {"review_summary": summary, "review_embedding": vector},
                "retry_on_conflict": 5,
            }
            for (product_id, summary), vector in zip(rows, vectors)
        ]
        succeeded, errors = bulk(
            client, actions, chunk_size=len(actions), raise_on_error=False,
            request_timeout=180,
        )
        if errors:
            raise RuntimeError(f"Review bulk update failed: {errors[0]}")
        checkpoint_path.write_text(json.dumps({
            "input": str(input_path.resolve()), "index": index,
            "completed_lines": line_number, "complete": False,
            "updated": succeeded,
        }, indent=2), encoding="utf-8")
        print(f"review embeddings: {line_number:,}", flush=True)

    with input_path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if line_number <= completed:
                continue
            product = json.loads(line)
            batch.append((product["product_id"], build_review_summary(product)))
            if len(batch) >= batch_size:
                flush(batch, line_number)
                batch = []
        if batch:
            flush(batch, line_number)

    checkpoint_path.write_text(json.dumps({
        "input": str(input_path.resolve()), "index": index,
        "completed_lines": line_number, "complete": True,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/amazon_fashion/products.jsonl"))
    parser.add_argument("--index", default="products-amazon-fashion-v2")
    parser.add_argument("--checkpoint", type=Path, default=Path("data/amazon_fashion/review_embedding.checkpoint.json"))
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()
    run(args.input, args.index, args.checkpoint, args.batch_size)

