"""Deterministic, evidence-only response formatting.

The New Thread response path deliberately has no LLM call. Query understanding
may use an LLM, but the final answer is rendered directly from verified catalog
fields and offline review summaries.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar

from backend.query_understanding import compile_search_intent
from tools.search_products import image_embedding_count, total_product_count


# Kept as a public capability flag for /health and older integrations.
LLM_WRITER_ENABLED = False
SYSTEM_PROMPT = "Deterministic evidence-only writer; no LLM invocation."
_TOKEN_CALLBACK: ContextVar = ContextVar("writer_token_callback", default=None)


def _clean(value, limit: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit].rstrip(" ,;:-")


def _review_excerpt(product: dict, field: str, limit: int = 150) -> str:
    values = product.get(field) or []
    excerpts: list[str] = []
    for value in values[:2]:
        if isinstance(value, dict):
            value = value.get("text")
        text = _clean(value, limit)
        if text:
            excerpts.append(re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0])
    return _clean(" / ".join(excerpts), limit)


def compact_products(products: list[dict]) -> list[dict]:
    """Compatibility helper containing only fields safe to expose."""
    fields = (
        "title", "brand", "color", "material", "style", "price",
        "average_rating", "review_count", "review_summary",
    )
    return [
        {field: product[field] for field in fields if product.get(field) not in (None, "")}
        for product in products[:3]
    ]


def _review_lines(product: dict) -> list[str]:
    summary = product.get("review_summary_ko") or product.get("review_summary")
    if isinstance(summary, list):
        lines = [_clean(item, 180) for item in summary[:3] if _clean(item, 180)]
    elif summary:
        lines = [_clean(item, 180) for item in str(summary).split("\n")[:3] if _clean(item, 180)]
    else:
        positive = _review_excerpt(product, "positive_review_evidence")
        negative = _review_excerpt(product, "negative_review_evidence")
        lines = []
        if positive:
            lines.append(f"Positive: {positive}")
        if negative:
            lines.append(f"Caution: {negative}")
    return lines[:3]


def _product_block_lines(products: list[dict], intent: str = "search") -> list[str]:
    lines = ["비교 상품" if intent == "compare" else "추천 상품"]
    for product in products[:3]:
        title = _clean(product.get("title"), 140) or "Unnamed product"
        lines.append(f"- {title}")
        if product.get("average_rating") is not None:
            lines.append(f"  - 평점: {float(product['average_rating']):.1f}/5")
        if product.get("review_count") is not None:
            lines.append(f"  - 리뷰: {int(product['review_count']):,}개")
        if product.get("price") is not None:
            lines.append(f"  - 가격: ${float(product['price']):,.2f}")
        review_lines = _review_lines(product)
        if review_lines:
            lines.append("  - 리뷰 요약:")
            lines.extend(f"    - {line}" for line in review_lines)
    return lines


def _image_coverage_note(message: str) -> str:
    try:
        if not compile_search_intent(message).color:
            return ""
        completed, total = image_embedding_count(), total_product_count()
        if completed and completed < total:
            return f"\n- Visual-search coverage: {completed:,}/{total:,} products"
    except Exception:
        pass
    return ""


def deterministic_answer(products: list[dict], intent: str = "search", message: str = "") -> str:
    if not products:
        return "조건에 맞는 상품을 찾지 못했습니다." + _image_coverage_note(message)
    lines = [f"요청 조건: {_clean(message, 180)}", ""]
    lines.extend(_product_block_lines(products, intent))
    return "\n".join(lines)


@contextmanager
def answer_stream(callback):
    token = _TOKEN_CALLBACK.set(callback)
    try:
        yield
    finally:
        _TOKEN_CALLBACK.reset(token)


def _emit(text: str) -> None:
    callback = _TOKEN_CALLBACK.get()
    if not callback:
        return
    # Line-sized chunks render useful structure sooner than waiting for the
    # whole answer, without artificial sleeps or fake token generation.
    for line in text.splitlines(keepends=True):
        callback(line)


def write_product_answer(
    message: str, products: list[dict], intent: str = "search", history: list[dict] | None = None
) -> str:
    del history
    answer = deterministic_answer(products, intent, message)
    _emit(answer)
    return answer
