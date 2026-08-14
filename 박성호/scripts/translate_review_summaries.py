"""Offline, resumable Korean translation of review summaries in OpenSearch.

The display text is stored as a normal field. Existing review vectors remain
unchanged because vectors are for retrieval, not for reconstructing translations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import ollama
from opensearchpy.helpers import bulk
from pydantic import BaseModel, Field

from scripts.embed_catalog_reviews import build_review_summary
from tools.search_products import client


DEFAULT_MODEL = os.getenv("OLLAMA_TRANSLATION_MODEL", os.getenv("OLLAMA_QUERY_MODEL", "qwen3:4b"))
KEEP_ALIVE = os.getenv("OLLAMA_QUERY_KEEP_ALIVE", "2h")


class TranslationBatch(BaseModel):
    translations: list[list[str]] = Field(description="One translated string list per input product")


class SingleTranslation(BaseModel):
    translation: list[str]


def _has_korean(lines: list[str]) -> bool:
    return any("가" <= char <= "힣" for line in lines for char in str(line))


def _translate_one(client_ollama: ollama.Client, summary: list[str], model: str) -> list[str]:
    response = client_ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": (
                "당신은 상품 리뷰 번역기입니다. 입력된 영어 문장을 반드시 자연스러운 한국어로 번역하세요. "
                "영어 문장을 그대로 복사하지 마세요. Positive:는 장점:, Caution:은 주의:로 번역하세요. "
                "사실, 수치, 장단점을 바꾸거나 새로운 내용을 추가하지 마세요."
            )},
            {"role": "user", "content": json.dumps(summary, ensure_ascii=False)},
        ],
        format=SingleTranslation.model_json_schema(),
        options={"temperature": 0, "num_predict": 500},
        think=False,
        keep_alive=KEEP_ALIVE,
    )
    message = response["message"] if isinstance(response, dict) else response.message
    raw = message["content"] if isinstance(message, dict) else message.content
    translated = SingleTranslation.model_validate_json(raw).translation
    if not _has_korean(translated):
        raise ValueError("Qwen returned no Korean text")
    return translated


def source_hash(summary: list[str]) -> str:
    canonical = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ensure_mapping(index: str) -> None:
    properties = client.indices.get_mapping(index=index)[index]["mappings"].get("properties", {})
    additions = {}
    if "review_summary_ko" not in properties:
        additions["review_summary_ko"] = {"type": "text", "index": False}
    if "review_translation_source_hash" not in properties:
        additions["review_translation_source_hash"] = {"type": "keyword"}
    if "review_translation_model" not in properties:
        additions["review_translation_model"] = {"type": "keyword"}
    if additions:
        client.indices.put_mapping(index=index, body={"properties": additions}, request_timeout=120)


def translate_batch(client_ollama: ollama.Client, rows: list[tuple[str, list[str], str]], model: str):
    payload = [summary for _, summary, _ in rows]
    response = client_ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": (
                "Translate Amazon Fashion review summaries into concise natural Korean. "
                "Preserve factual meaning, product details, numbers, and sentiment. "
                "Translate 'Positive:' as '장점:' and 'Caution:' as '주의:'. "
                "Do not add claims. Return exactly one string list per input product in the same order."
            )},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        format=TranslationBatch.model_json_schema(),
        options={"temperature": 0, "num_predict": min(1800, max(300, len(rows) * 180))},
        think=False,
        keep_alive=KEEP_ALIVE,
    )
    message = response["message"] if isinstance(response, dict) else response.message
    raw = message["content"] if isinstance(message, dict) else message.content
    translations = TranslationBatch.model_validate_json(raw).translations
    if len(translations) != len(rows):
        raise ValueError(f"Translation count mismatch: expected {len(rows)}, got {len(translations)}")
    # Small local models occasionally satisfy the JSON schema while copying
    # English verbatim. Retry only those rows with a stricter Korean prompt.
    for index, translated in enumerate(translations):
        if not _has_korean(translated):
            translations[index] = _translate_one(client_ollama, rows[index][1], model)
    return translations


def run(input_path: Path, index: str, checkpoint_path: Path, batch_size: int, model: str, limit: int | None):
    ensure_mapping(index)
    completed = 0
    translated = 0
    skipped = 0
    if checkpoint_path.exists():
        saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if saved.get("index") != index or saved.get("model") != model:
            raise ValueError("Checkpoint index or translation model does not match")
        completed = int(saved.get("completed_lines", 0))
        translated = int(saved.get("translated", 0))
        skipped = int(saved.get("skipped", 0))

    ollama_client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))
    pending: list[tuple[str, list[str], str]] = []
    last_line = completed

    def save_checkpoint(complete=False):
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(json.dumps({
            "input": str(input_path.resolve()), "index": index, "model": model,
            "completed_lines": last_line, "translated": translated,
            "skipped": skipped, "complete": complete,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def flush():
        nonlocal translated, pending
        if not pending:
            return
        translations = translate_batch(ollama_client, pending, model)
        actions = []
        for (product_id, _, digest), translated_lines in zip(pending, translations):
            clean = [" ".join(str(line).split())[:440] for line in translated_lines if str(line).strip()][:3]
            actions.append({
                "_op_type": "update", "_index": index, "_id": product_id,
                "doc": {
                    "review_summary_ko": clean,
                    "review_translation_source_hash": digest,
                    "review_translation_model": model,
                },
                "retry_on_conflict": 5,
            })
        succeeded, errors = bulk(client, actions, chunk_size=len(actions), raise_on_error=False, request_timeout=180)
        if errors:
            raise RuntimeError(f"Translation bulk update failed: {errors[0]}")
        translated += succeeded
        pending = []
        save_checkpoint()
        print(f"lines={last_line:,} translated={translated:,} skipped={skipped:,}", flush=True)

    with input_path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if line_number <= completed:
                continue
            if limit is not None and line_number > completed + limit:
                break
            last_line = line_number
            product = json.loads(line)
            summary = build_review_summary(product)
            if not summary:
                skipped += 1
                continue
            pending.append((product["product_id"], summary, source_hash(summary)))
            if len(pending) >= batch_size:
                flush()
        flush()
    save_checkpoint(complete=limit is None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/amazon_fashion/products.jsonl"))
    parser.add_argument("--index", default=os.getenv("OPENSEARCH_INDEX", "products-amazon-fashion-v2"))
    parser.add_argument("--checkpoint", type=Path, default=Path("data/amazon_fashion/review_translation_ko.checkpoint.json"))
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, help="Process only this many new input lines for a canary run")
    args = parser.parse_args()
    run(args.input, args.index, args.checkpoint, args.batch_size, args.model, args.limit)
