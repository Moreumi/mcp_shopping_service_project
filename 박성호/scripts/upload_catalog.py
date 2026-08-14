import argparse
import json
import time
from pathlib import Path

from opensearchpy.helpers import parallel_bulk

from tools.search_products import client


def actions(path, index_name, limit=None, skip_lines=0):
    with open(path, "r", encoding="utf-8") as source:
        for number, line in enumerate(source, start=1):
            if number <= skip_lines:
                continue
            if limit and number > limit:
                break

            product = json.loads(line)
            yield {
                "_op_type": "index",
                "_index": index_name,
                "_id": product["product_id"],
                "_source": product,
            }


def upload(
    path,
    index_name,
    chunk_size=500,
    limit=None,
    thread_count=2,
    skip_lines=0,
    delay_seconds=0.0,
    checkpoint_path=None,
):
    checkpoint = Path(checkpoint_path) if checkpoint_path else None
    if checkpoint and thread_count != 1:
        raise ValueError("Checkpoint uploads require --thread-count 1 for ordered progress.")
    if checkpoint and checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        if saved.get("index") != index_name or Path(saved.get("input", "")).resolve() != Path(path).resolve():
            raise ValueError("Checkpoint input or index does not match this upload.")
        skip_lines = max(skip_lines, int(saved.get("completed_lines", 0)))

    success = 0
    failed = 0

    for ok, item in parallel_bulk(
        client,
        actions(path, index_name, limit, skip_lines),
        chunk_size=chunk_size,
        max_chunk_bytes=10 * 1024 * 1024,
        thread_count=thread_count,
        queue_size=max(thread_count, 1),
        raise_on_error=False,
        raise_on_exception=False,
        request_timeout=180,
    ):
        if ok:
            success += 1
        else:
            failed += 1
            print(json.dumps(item, ensure_ascii=False, default=str)[:2000])
            raise RuntimeError(
                f"Upload stopped after {skip_lines + success:,} completed lines; rerun to resume."
            )

        processed = success + failed
        absolute_completed = skip_lines + success
        if checkpoint and success % chunk_size == 0:
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(
                json.dumps({
                    "input": str(Path(path).resolve()),
                    "index": index_name,
                    "completed_lines": absolute_completed,
                    "complete": False,
                }, indent=2),
                encoding="utf-8",
            )
        if processed % 10_000 == 0:
            print(
                f"uploaded total: {absolute_completed:,}, failed: {failed:,}",
                flush=True,
            )
        if delay_seconds and processed % chunk_size == 0:
            time.sleep(delay_seconds)

    client.indices.put_settings(
        index=index_name,
        body={"index": {"refresh_interval": "1s"}},
        request_timeout=120,
    )
    client.indices.refresh(index=index_name, request_timeout=120)
    if checkpoint:
        checkpoint.write_text(
            json.dumps({
                "input": str(Path(path).resolve()),
                "index": index_name,
                "completed_lines": skip_lines + success,
                "complete": True,
            }, indent=2),
            encoding="utf-8",
        )
    print(json.dumps({"success": success, "failed": failed}, indent=2))
    return success, failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/amazon_fashion/products_embedded.jsonl")
    parser.add_argument("--index", default="products-amazon-fashion-v2")
    parser.add_argument("--chunk-size", type=int, default=50)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--thread-count", type=int, default=1)
    parser.add_argument("--skip-lines", type=int, default=0)
    parser.add_argument("--delay-seconds", type=float, default=0.2)
    parser.add_argument("--checkpoint", default="data/amazon_fashion/upload_v2.checkpoint.json")
    args = parser.parse_args()
    upload(
        args.input,
        args.index,
        args.chunk_size,
        args.limit,
        args.thread_count,
        args.skip_lines,
        args.delay_seconds,
        args.checkpoint,
    )
