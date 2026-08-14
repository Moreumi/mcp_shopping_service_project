"""Precision-first second-stage reranking with a deterministic fallback."""

from __future__ import annotations

from functools import lru_cache
import math
import os
import re


MODEL_ID = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
ENABLED = os.getenv("RERANKER_ENABLED", "false").lower() == "true"
LOCAL_ONLY = os.getenv("RERANKER_LOCAL_FILES_ONLY", "true").lower() != "false"
MAX_CANDIDATES = int(os.getenv("RERANKER_MAX_CANDIDATES", "8"))


def _tokens(value: str) -> set[str]:
    return {
        token[:-1] if len(token) > 3 and token.endswith("s") else token
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) >= 3
    }


def _product_text(product: dict) -> str:
    return " ".join(
        str(product.get(field) or "")
        for field in ("title", "product_type", "category", "brand", "color", "material", "style", "bullet_points")
    )[:1800]


def lexical_relevance(query: str, product: dict, product_terms=(), product_phrases=()) -> float:
    """Return a calibrated 0..1 evidence score; title evidence is strongest."""
    title = str(product.get("title") or "").lower()
    text = _product_text(product).lower()
    query_tokens = _tokens(query)
    title_tokens = _tokens(title)
    text_tokens = _tokens(text)
    terms = _tokens(" ".join(str(term) for term in product_terms))
    phrases = [str(value).lower().strip() for value in product_phrases if str(value).strip()]

    phrase_match = max((len(_tokens(phrase)) for phrase in phrases if _tokens(phrase) <= title_tokens), default=0)
    term_coverage = len(terms & title_tokens) / len(terms) if terms else 0.0
    query_coverage = len(query_tokens & text_tokens) / len(query_tokens) if query_tokens else 0.0
    phrase_score = min(1.0, phrase_match / 2) if phrase_match else 0.0
    score = 0.55 * phrase_score + 0.30 * term_coverage + 0.15 * query_coverage
    return round(min(1.0, score), 4)


@lru_cache(maxsize=1)
def _runtime():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, local_files_only=LOCAL_ONLY)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_ID, local_files_only=LOCAL_ONLY
    ).to(device).eval()
    return torch, tokenizer, model, device


def warm_reranker() -> None:
    """Load the cross-encoder once at startup instead of on the first search."""
    if not ENABLED:
        return
    try:
        _model_scores("warmup", [{"title": "warmup product"}])
    except Exception:
        pass


def _model_scores(query: str, products: list[dict]) -> list[float]:
    torch, tokenizer, model, device = _runtime()
    pairs = [[query, _product_text(product)] for product in products]
    inputs = tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.inference_mode():
        logits = model(**inputs).logits.view(-1).float().cpu().tolist()
    return [1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, score)))) for score in logits]


def rerank_products(query: str, products: list[dict], *, product_terms=(), product_phrases=()) -> list[dict]:
    candidates = products[:MAX_CANDIDATES]
    lexical = [lexical_relevance(query, product, product_terms, product_phrases) for product in candidates]
    model_scores = None
    if ENABLED and candidates:
        try:
            model_scores = _model_scores(query, candidates)
        except Exception:
            # Missing model/GPU must never take down catalog search.
            model_scores = None

    ranked = []
    for index, product in enumerate(candidates):
        relevance = lexical[index]
        if model_scores is not None:
            relevance = 0.70 * model_scores[index] + 0.30 * relevance
        ranked.append({**product, "relevance_score": round(relevance, 4)})
    ranked.sort(
        key=lambda product: (product["relevance_score"], product.get("hybrid_score", 0)),
        reverse=True,
    )
    return ranked


def confidence_filter(products: list[dict], minimum: float = 0.10) -> list[dict]:
    """Prefer abstention over filling three slots with weakly related items."""
    if not products:
        return []
    accepted = [product for product in products if float(product.get("relevance_score") or 0) >= minimum]
    if not accepted:
        return []
    top = float(accepted[0].get("relevance_score") or 0)
    return [
        product for product in accepted
        if float(product.get("relevance_score") or 0) >= max(minimum, top - 0.45)
    ]
