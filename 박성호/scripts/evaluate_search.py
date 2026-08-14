"""Labeled precision-oriented evaluation for the Amazon Fashion demo."""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.policies import (  # noqa: E402
    detect_requested_audience, detect_requested_category, detect_requested_color,
    detect_requested_product_kind, filter_products, rank_products,
)
from backend.query_understanding import compile_search_intent  # noqa: E402
from backend.reranker import confidence_filter, rerank_products  # noqa: E402
from tools.hybrid_search import hybrid_search  # noqa: E402


CASES_PATH = ROOT / "tests" / "fixtures" / "search_quality_cases.json"


def _relevant(title: str, case: dict) -> bool:
    text = (title or "").lower()
    def forbidden_contains(term: str) -> bool:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text))

    def normalized(value: str) -> str:
        tokens = re.findall(r"[a-z0-9]+", value.lower())
        return " ".join(token[:-1] if len(token) > 3 and token.endswith("s") else token for token in tokens)

    normalized_title = normalized(text)
    required = any(normalized(term) in normalized_title for term in case.get("title_any", []))
    forbidden = any(forbidden_contains(term) for term in case.get("title_none", []))
    return required and not forbidden


def _ndcg(relevances: list[bool]) -> float:
    if not relevances:
        return 0.0
    dcg = sum((1.0 if relevant else 0.0) / math.log2(rank + 2) for rank, relevant in enumerate(relevances))
    ideal_count = sum(relevances)
    if not ideal_count:
        return 0.0
    ideal = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_count))
    return round(dcg / ideal, 3)


def evaluate_case(case: dict) -> dict:
    query = case["query"]
    intent = compile_search_intent(query)
    category = intent.category or detect_requested_category(query)
    audience = intent.audience or detect_requested_audience(query)
    color = intent.color or detect_requested_color(query)
    requested_kind = detect_requested_product_kind(query)
    started = time.perf_counter()
    candidates = hybrid_search(
        intent.semantic_query, size=60, category=category, audience=audience,
        required_color=color, product_kind=requested_kind,
        visual_query_text=intent.visual_query, product_terms=intent.product_terms,
        product_phrases=intent.product_phrases, exclude_kids=intent.exclude_kids,
    )
    products = filter_products(
        candidates, category=category, audience=audience, required_color=color,
        requested_kind=requested_kind, exclude_kids=intent.exclude_kids,
    )
    products = confidence_filter(rerank_products(
        intent.semantic_query, products,
        product_terms=intent.product_terms,
        product_phrases=intent.product_phrases,
    ))
    products = rank_products(products, limit=3)
    titles = [product.get("title") or "" for product in products]
    relevance = [_relevant(title, case) for title in titles]
    normalized_titles = [" ".join(title.lower().split()) for title in titles]
    duplicates = len(normalized_titles) - len(set(normalized_titles))
    minimum = int(case.get("min_results", 1))
    precision = round(sum(relevance) / len(relevance), 3) if relevance else (1.0 if minimum == 0 else 0.0)
    passed = len(products) >= minimum and all(relevance) and duplicates == 0
    return {
        "query": query,
        "result_count": len(products),
        "relevant_count": sum(relevance),
        "precision_at_3": precision,
        "ndcg_at_3": _ndcg(relevance),
        "duplicate_count": duplicates,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "titles": titles,
        "passed": passed,
    }


def run(path: Path = CASES_PATH) -> dict:
    cases = json.loads(path.read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in cases]
    summary = {
        "cases": len(results),
        "passed": sum(result["passed"] for result in results),
        "pass_rate": round(sum(result["passed"] for result in results) / len(results), 3),
        "mean_precision_at_3": round(sum(result["precision_at_3"] for result in results) / len(results), 3),
        "mean_ndcg_at_3": round(sum(result["ndcg_at_3"] for result in results) / len(results), 3),
        "duplicate_queries": sum(result["duplicate_count"] > 0 for result in results),
        "average_latency_ms": round(sum(result["latency_ms"] for result in results) / len(results)),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    run()
