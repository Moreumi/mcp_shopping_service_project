import argparse
import json
from pathlib import Path

import ollama

MODEL_NAME = "nomic-embed-text"
EMBEDDING_DIMENSION = 768

CATEGORY_ALIASES = {
    "Shoes": "신발 구두 운동화 샌들 부츠 sneakers shoes",
    "Clothing": "옷 의류 셔츠 재킷 바지 원피스 clothing apparel",
    "Watches": "시계 손목시계 watches",
    "Jewelry": "주얼리 귀걸이 목걸이 팔찌 반지 jewelry",
    "Bags": "가방 핸드백 백팩 지갑 bags handbags",
    "Accessories": "액세서리 벨트 모자 스카프 장갑 선글라스 accessories",
}


def make_product_text(product):
    parts = []
    for field in (
        "title", "brand", "category", "product_type", "color", "material",
        "style", "description", "main_category", "review_summary",
    ):
        value = product.get(field)
        if value:
            parts.append(f"{field}: {value}")

    for field, label in (
        ("bullet_points", "features"),
        ("keywords", "keywords"),
        ("positive_review_evidence", "positive reviews"),
        ("negative_review_evidence", "negative reviews"),
    ):
        value = product.get(field)
        if value:
            if isinstance(value, list):
                text = " ".join(
                    str(item.get("text", "") if isinstance(item, dict) else item)
                    for item in value[:3]
                )
            else:
                text = str(value)
            parts.append(f"{label}: {text}")
    category = str(product.get("category") or "").rsplit(">", 1)[-1].strip()
    if CATEGORY_ALIASES.get(category):
        parts.append(f"multilingual category aliases: {CATEGORY_ALIASES[category]}")
    audience = product.get("audience")
    if audience == "Women":
        parts.append("audience aliases: 여성 여자 women women's")
    elif audience == "Men":
        parts.append("audience aliases: 남성 남자 men men's")
    elif audience == "Kids":
        parts.append("audience aliases: 아동 어린이 kids children")
    return "\n".join(parts)


def completed_lines(path):
    if not path.exists():
        return 0

    with path.open("r", encoding="utf-8") as source:
        return sum(1 for _ in source)


def embed_catalog(input_path, output_path, batch_size=128, limit=None):
    source_path = Path(input_path)
    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    completed = completed_lines(target_path)
    processed = 0
    batch = []

    def write_batch(target, products):
        texts = [make_product_text(product) for product in products]
        response = ollama.embed(model=MODEL_NAME, input=texts)
        embeddings = response["embeddings"]

        if len(embeddings) != len(products):
            raise ValueError("Embedding result count does not match input count.")

        for product, embedding in zip(products, embeddings):
            if len(embedding) != EMBEDDING_DIMENSION:
                raise ValueError(
                    f"Unexpected embedding dimension: {len(embedding)}"
                )
            product["embedding"] = embedding
            target.write(
                json.dumps(product, ensure_ascii=False, default=str) + "\n"
            )
        target.flush()

    with source_path.open("r", encoding="utf-8") as source, target_path.open(
        "a", encoding="utf-8", newline="\n"
    ) as target:
        for line_number, line in enumerate(source):
            if line_number < completed:
                continue
            if limit and processed >= limit:
                break

            batch.append(json.loads(line))
            if len(batch) < batch_size and not (
                limit and processed + len(batch) >= limit
            ):
                continue

            write_batch(target, batch)
            processed += len(batch)
            batch = []
            print(
                f"embedded locally: {completed + processed:,}",
                flush=True,
            )

        if batch:
            write_batch(target, batch)
            processed += len(batch)

    result = {
        "previously_completed": completed,
        "newly_completed": processed,
        "total_completed": completed + processed,
        "output": str(target_path),
    }
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/amazon_fashion/products.jsonl")
    parser.add_argument("--output", default="data/amazon_fashion/products_embedded.jsonl")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    embed_catalog(args.input, args.output, args.batch_size, args.limit)
