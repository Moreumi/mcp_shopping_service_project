from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import os
import re
import threading
import time

import ollama

from backend.policies import ProductConstraint, SLEEVE_EXCLUSION_TERMS, product_matches_constraint
from tools.search_products import INDEX_NAME, client
from tools.siglip_vision import COLOR_LABELS, embed_visual_query, evaluate_candidate


EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_KEEP_ALIVE = os.getenv("OLLAMA_EMBED_KEEP_ALIVE", "2h")
EMBEDDING_CACHE_SIZE = int(os.getenv("EMBEDDING_CACHE_SIZE", "256"))
ONLINE_VISION_VERIFY = os.getenv("ONLINE_VISION_VERIFY", "false").lower() == "true"
_PREVIEW_CALLBACK: ContextVar = ContextVar("retrieval_preview_callback", default=None)
PRODUCT_KIND_SEARCH = {
    "Sneakers": {
        "include": ("sneaker", "sneakers", "running shoe", "running shoes", "walking shoe", "walking shoes", "athletic shoe", "trainer"),
        "exclude": ("steel toe", "safety shoe", "work shoe", "work boot", "construction", "boot", "sock", "slipper", "sandal", "clog"),
    },
    "Loafers": {
        "include": ("loafer", "loafers", "slip-on loafer", "slip on loafer"),
        "exclude": ("shoelace", "shoe lace", "sneaker", "sandal", "boot", "slipper", "slippers"),
    },
    "FormalShoes": {
        "include": ("dress shoe", "dress shoes", "formal shoe", "formal shoes", "loafer", "loafers", "oxford", "oxfords", "business shoe"),
        "exclude": ("sneaker", "running shoe", "walking shoe", "athletic shoe", "steel toe", "work boot", "sock", "slipper", "sandal", "clog"),
    },
    "Sandals": {
        "include": ("sandal", "sandals", "flip flop", "flip-flop", "slides"),
        "exclude": ("steel toe", "work shoe", "work boot", "construction", "sneaker", "running shoe", "sock"),
    },
    "Coats": {
        "include": ("coat", "coats", "puffer jacket", "overcoat", "parka"),
        "exclude": ("legging", "pants", "trouser", "shirt", "dress", "skirt", "tights"),
    },
    "Sunglasses": {
        "include": ("sunglass", "sunglasses", "sun glasses", "eyewear"),
        "exclude": ("face mask", "scarf", "hat", "visor", "cap"),
    },
    "Shorts": {
        "include": ("shorts", "short pants", "bermuda shorts", "cargo shorts"),
        "exclude": ("jeans", "denim pants", "trouser", "trousers", "legging", "leggings", "jumpsuit", "overall", "skirt", "dress"),
    },
}


@contextmanager
def retrieval_preview(callback):
    token = _PREVIEW_CALLBACK.set(callback)
    try:
        yield
    finally:
        _PREVIEW_CALLBACK.reset(token)


def _emit_keyword_preview(response: dict, constraint: ProductConstraint, terms, phrases) -> None:
    callback = _PREVIEW_CALLBACK.get()
    if not callback:
        return
    preview = []
    for hit in response.get("hits", {}).get("hits", []):
        product = {**hit.get("_source", {}), "product_id": hit.get("_id")}
        if (terms or phrases) and not _semantic_evidence(product, terms, phrases):
            continue
        if product_matches_constraint(product, constraint):
            preview.append(product)
        if len(preview) == 3:
            break
    if preview:
        callback(preview)
_embedding_status = {
    "ready": False,
    "warming": False,
    "error": None,
    "last_latency_ms": None,
}
_embedding_status_lock = threading.Lock()

# Large review bodies are fetched only after reranking the final three items.
RETRIEVAL_SOURCE_EXCLUDES = [
    "embedding",
    "image_embedding",
    "review_embedding",
    "description",
    "positive_review_evidence",
    "negative_review_evidence",
]


@lru_cache(maxsize=EMBEDDING_CACHE_SIZE)
def _embed_query(query: str) -> tuple[float, ...]:
    started = time.perf_counter()
    response = ollama.embed(
        model=EMBEDDING_MODEL,
        input=query,
        keep_alive=EMBEDDING_KEEP_ALIVE,
    )
    vector = tuple(response["embeddings"][0])
    with _embedding_status_lock:
        _embedding_status.update({
            "ready": True,
            "warming": False,
            "error": None,
            "last_latency_ms": round((time.perf_counter() - started) * 1000),
        })
    return vector


def warm_embedding_model():
    """Load the local embedding model before the first demo search."""
    with _embedding_status_lock:
        if _embedding_status["ready"] or _embedding_status["warming"]:
            return dict(_embedding_status)
        _embedding_status["warming"] = True
        _embedding_status["error"] = None
    try:
        _embed_query("shopping assistant warmup")
    except Exception as error:
        with _embedding_status_lock:
            _embedding_status.update({
                "ready": False,
                "warming": False,
                "error": type(error).__name__,
            })
    return embedding_model_status()


def embedding_model_status():
    with _embedding_status_lock:
        return {
            "model": EMBEDDING_MODEL,
            "keep_alive": EMBEDDING_KEEP_ALIVE,
            **_embedding_status,
            "cached_queries": _embed_query.cache_info().currsize,
        }


def _catalog_filters(category=None, audience=None, required_color=None, product_kind=None, required_brand=None):
    filters = []
    if category:
        filters.append({"match": {"category": category}})
    if audience == "Kids":
        # Kids stays a strict inclusion filter (must have positive evidence)
        # - unlike Men/Women below, wrongly including an adult item here is
        # the worse failure mode, so this one keeps requiring proof.
        filters.append({
            "bool": {
                "should": [
                    {"term": {"audience": "Kids"}},
                    {"term": {"audience": "Unisex"}},
                    {"match": {"title": "kids"}},
                    {"match": {"category": "kids"}},
                ],
                "minimum_should_match": 1,
            }
        })
    # Men/Women audience is enforced as a must_not (exclude the explicit
    # opposite gender) in hybrid_search's keyword_must_not instead of an
    # inclusion filter here - see the comment there for why.
    if required_color:
        filters.append({
            "bool": {
                "should": [
                    {"match": {"color": required_color}},
                    {"match": {"title": required_color}},
                ],
                "minimum_should_match": 1,
            }
        })
    if product_kind in PRODUCT_KIND_SEARCH:
        rule = PRODUCT_KIND_SEARCH[product_kind]
        fields = ["title^4", "product_type^3", "style^2", "category"]
        filters.append({
            "bool": {
                "should": [
                    {"multi_match": {"query": term, "fields": fields, "type": "phrase"}}
                    for term in rule["include"]
                ],
                "minimum_should_match": 1,
            }
        })
    if required_brand:
        # A named brand is a hard constraint, not just a ranking signal -
        # without this, "나이키 운동화" silently returned unrelated brands
        # ranked purely by title/embedding relevance even though the
        # catalog has genuine Nike products, which reads as the assistant
        # ignoring the request while claiming to have fulfilled it. A tuple
        # of 2+ brands (an explicit "compare brand A vs brand B" request)
        # matches either one instead of requiring both on the same product.
        brand_values = (required_brand,) if isinstance(required_brand, str) else required_brand
        should = []
        for value in brand_values:
            should.append({"match": {"brand": value}})
            should.append({"match": {"title": value}})
        filters.append({"bool": {"should": should, "minimum_should_match": 1}})
    return filters


def _visual_query(category=None, audience=None, required_color=None, product_kind=None):
    parts = ["a product photo of"]
    if required_color:
        parts.append(required_color.lower())
    if audience:
        parts.append("men's" if audience == "Men" else "women's")
    if product_kind == "Sneakers":
        parts.append("sneakers or athletic shoes")
    elif product_kind == "FormalShoes":
        parts.append("formal dress shoes or loafers")
    elif product_kind == "Sandals":
        parts.append("sandals or flip flops")
    elif product_kind == "Coats":
        parts.append("coat or puffer jacket")
    elif product_kind == "Sunglasses":
        parts.append("sunglasses or eyewear")
    elif category:
        parts.append(category.lower())
    else:
        parts.append("fashion product")
    return " ".join(parts)


def _semantic_evidence(product: dict, product_terms, product_phrases=None) -> bool:
    terms = [str(term).lower().strip() for term in (product_terms or []) if len(str(term).strip()) >= 3]
    text = " ".join(
        str(product.get(field) or "").lower()
        for field in ("title", "product_type", "category", "style", "bullet_points", "description")
    )
    phrases = [str(phrase).lower().strip() for phrase in (product_phrases or []) if len(str(phrase).strip()) >= 3]
    if phrases:
        # Normalize basic English plurals so generic phrase evidence accepts
        # shoe/shoes and sneaker/sneakers without a per-product rule table.
        def normalized_tokens(value):
            tokens = re.findall(r"[a-z0-9]+", value.lower())
            return {token[:-1] if len(token) > 3 and token.endswith("s") else token for token in tokens}

        # A phrase counts as evidence once every one of its words appears
        # somewhere in the product text, regardless of order/adjacency.
        # Catalog titles often put an attribute like color at the end
        # ("... Pants Yellow") rather than as an adjacent phrase like the
        # compiled "yellow pants" - requiring an exact substring match was
        # silently rejecting genuinely matching products.
        text_tokens = normalized_tokens(text)
        if any(normalized_tokens(phrase) <= text_tokens for phrase in phrases):
            return True
        # The LLM can pick a phrase using a synonym the catalog rarely uses
        # (e.g. "yellow trousers" when titles almost always say "pants") even
        # though the plain terms would have matched - fall back to a term
        # check instead of rejecting an otherwise-good candidate outright.
        if terms:
            return any(term in text for term in terms)
        return False
    if not terms:
        return True
    return any(term in text for term in terms)


def hybrid_search(
    query: str,
    size: int = 5,
    category: str = None,
    audience: str = None,
    required_color: str = None,
    product_kind: str = None,
    required_brand: str = None,
    required_sleeve: str = None,
    exclude_product_ids=None,
    visual_query_text: str = None,
    product_terms=None,
    product_phrases=None,
    exclude_kids: bool = True,
    min_rating: float = None,
    retrieval_mode: str = "auto",
):
    if exclude_product_ids is None:
        exclude_product_ids = []

    # =====================================
    # 1. 검색어 → Embedding
    # =====================================

    if retrieval_mode == "auto":
        retrieval_mode = "visual" if required_color else ("keyword" if required_brand else "semantic")
    if retrieval_mode not in {"keyword", "semantic", "visual"}:
        raise ValueError(f"Unsupported retrieval mode: {retrieval_mode}")

    # 후보군은 최종 결과보다 넓게 가져옴
    # The demo domain is a single small node. A bounded candidate pool keeps
    # three parallel retrieval branches below its heap circuit breaker.
    candidate_size = min(max(size * 8, 50), 150)

    # =====================================
    # 2. Keyword Search
    # =====================================

    keyword_filter = _catalog_filters(category, audience, required_color, product_kind, required_brand)
    keyword_must_not = []

    if exclude_product_ids:
        keyword_must_not.append({
            "ids": {
                "values": exclude_product_ids
            }
        })

    if exclude_kids:
        for term in ("toddler", "little kid", "kids", "kid's", "boys", "girls", "youth", "years old", "baby", "infant"):
            keyword_must_not.append({"match_phrase": {"title": term}})

    for term in SLEEVE_EXCLUSION_TERMS.get(required_sleeve, ()):
        keyword_must_not.append({"match_phrase": {"title": term}})

    if audience in ("Men", "Women"):
        # Excluding the explicit opposite gender (must_not) instead of
        # requiring positive evidence of the target one (must) matches
        # product_matches_constraint's own, looser semantics - most
        # products here have no `audience` field and no gender word in the
        # title at all (unisex-applicable in practice), and requiring one
        # was silently dropping those from the retrieval candidate pool
        # before the softer post-filter ever got a chance to keep them.
        opposite = "Women" if audience == "Men" else "Men"
        keyword_must_not.append({"term": {"audience": opposite}})
        opposite_word = "women" if opposite == "Women" else "men"
        for term in (f"{opposite_word}'s", opposite_word):
            keyword_must_not.append({"match_phrase": {"title": term}})

    keyword_body = {
        "size": candidate_size,

        "_source": {"excludes": RETRIEVAL_SOURCE_EXCLUDES},

        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,

                            "fields": [
                                "title^10",
                                "style^7",
                                "category^6",
                                "product_type^5",
                                "bullet_points^3",
                                "description^2",
                                "brand^2"
                            ]
                        }
                    }
                ],

                "filter": keyword_filter,

                "must_not": keyword_must_not
            }
        }
    }

    # =====================================
    # 3. Vector Search
    # =====================================

    vector_search_active = retrieval_mode in {"semantic", "visual"}

    def semantic_search():
        # Embedding generation runs concurrently with BM25 and visual embedding.
        query_vector = list(_embed_query(query))
        vector_filter = {"bool": {"filter": keyword_filter, "must_not": keyword_must_not}}
        return client.search(index=INDEX_NAME, body={
            "size": candidate_size,
            "_source": {"excludes": RETRIEVAL_SOURCE_EXCLUDES},
            "query": {"knn": {"embedding": {
                "vector": query_vector,
                "k": candidate_size,
                "filter": vector_filter,
            }}},
        })

    def visual_search():
        image_vector = embed_visual_query(
            visual_query_text or _visual_query(category, audience, required_color, product_kind)
        )
        image_filter = _catalog_filters(category, audience, None, product_kind, required_brand)
        return client.search(index=INDEX_NAME, body={
            "size": candidate_size,
            "_source": {"excludes": RETRIEVAL_SOURCE_EXCLUDES},
            "query": {"knn": {"image_embedding": {
                "vector": image_vector,
                "k": candidate_size,
                "filter": {"bool": {"filter": image_filter, "must_not": keyword_must_not}},
            }}},
        })

    image_response = {"hits": {"hits": []}}
    # Product-kind constraints are already enforced by deterministic text
    # filters. Starting SigLIP for every shoe/coat query added a large cold
    # start with little precision benefit, so visual ANN is reserved for
    # genuinely visual constraints such as colour.
    image_search_active = retrieval_mode == "visual"
    constraint = ProductConstraint(
        category=category,
        audience=audience,
        color=required_color,
        product_kind=product_kind,
        brand=required_brand,
        sleeve=required_sleeve,
        exclude_kids=exclude_kids,
        excluded_product_ids=frozenset(exclude_product_ids),
        min_rating=min_rating,
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        keyword_future = pool.submit(client.search, index=INDEX_NAME, body=keyword_body)
        vector_future = pool.submit(semantic_search) if vector_search_active else None
        image_future = pool.submit(visual_search) if image_search_active else None

        keyword_response = keyword_future.result()
        _emit_keyword_preview(keyword_response, constraint, product_terms, product_phrases)
        try:
            vector_response = vector_future.result() if vector_future is not None else {"hits": {"hits": []}}
        except Exception:
            # BM25 remains usable when local embedding or vector ANN is unavailable.
            vector_response = {"hits": {"hits": []}}
        if image_future is not None:
            try:
                image_response = image_future.result()
            except Exception:
                # Text retrieval remains available while visual rollout is partial.
                image_search_active = False

    # =====================================
    # 4. RRF
    # Reciprocal Rank Fusion
    # =====================================

    scores = {}
    products = {}

    RRF_K = 60

    # Keyword 순위
    for rank, hit in enumerate(
        keyword_response["hits"]["hits"],
        start=1
    ):
        product_id = hit["_id"]

        scores[product_id] = (
            scores.get(product_id, 0)
            + 1.00 / (RRF_K + rank)
        )

        products[product_id] = hit["_source"]

    # Vector 순위
    for rank, hit in enumerate(
        vector_response["hits"]["hits"],
        start=1
    ):
        product_id = hit["_id"]

        scores[product_id] = (
            scores.get(product_id, 0)
            + 0.78 / (RRF_K + rank)
        )

        if product_id not in products:
            products[product_id] = hit["_source"]

    # Retrieve broadly, then let the stricter per-image classifier decide.
    # This preserves precision without returning only one item for rare colors.
    visual_match_limit = min(max(size * 2, 12), 60)
    visual_match_ids = set()
    visual_core_ids = set()
    for rank, hit in enumerate(image_response["hits"]["hits"], start=1):
        product_id = hit["_id"]
        scores[product_id] = scores.get(product_id, 0) + 0.44 / (RRF_K + rank)
        if product_id not in products:
            products[product_id] = hit["_source"]
        if rank <= visual_match_limit:
            visual_match_ids.add(product_id)
        if rank <= max(min(size, 10), 5):
            visual_core_ids.add(product_id)

    # =====================================
    # 5. 최종 조건 재검사
    # =====================================

    ranked_ids = sorted(
        scores,
        key=scores.get,
        reverse=True
    )

    results = []
    for product_id in ranked_ids:

        product = products[product_id]
        vision_evaluation = None

        color_value = (
            product.get("color") or ""
        )

        title_value = (
            product.get("title") or ""
        )

        if (product_phrases or product_terms) and not _semantic_evidence(product, product_terms, product_phrases):
            continue

        # color hard check
        if required_color:

            # The structured color field is authoritative when present. A
            # color word appearing incidentally in the title (e.g. a black
            # "Red Bull" tee) must never be allowed to confirm/override it -
            # only fall back to scanning the title when there is no
            # structured color to go on at all, and even then strip the
            # brand name first so a brand like "Red Bull" can't masquerade
            # as a color match on its own.
            color_field_text = color_value.lower()
            brand_value = (product.get("brand") or "").lower()
            title_fallback_text = title_value.lower()
            if brand_value:
                title_fallback_text = title_fallback_text.replace(brand_value, " ")
            search_text = color_field_text or title_fallback_text
            # "gray"/"grey" are the same color under two spellings - the
            # catalog's own color field is unified to "Gray" (see
            # backend/policies.py's COLOR_TERMS), but a title-fallback string
            # can still say "Grey", which would otherwise register as a
            # *different*, conflicting named color from a "gray" request.
            search_text = re.sub(r"\bgrey\b", "gray", search_text)

            # Catalog color text is stronger evidence than a close visual
            # embedding score. Reject an explicitly different named color;
            # SigLIP remains useful when metadata is absent or ambiguous.
            requested_color = "gray" if required_color.lower() == "grey" else required_color.lower()
            named_colors = {name.lower() for name in COLOR_LABELS}
            conflicting_colors = {
                name for name in named_colors
                if name != requested_color and re.search(rf"\b{re.escape(name)}\b", search_text)
            }
            requested_is_named = re.search(rf"\b{re.escape(requested_color)}\b", search_text)
            if conflicting_colors and not requested_is_named and "multicolor" not in search_text:
                continue

            if requested_is_named:
                # Catalog text already confirms the requested colour; trust
                # it directly rather than also requiring a visual ANN hit,
                # which would wrongly drop items SigLIP hasn't embedded yet.
                pass
            elif image_search_active:
                # No colour text to go on: fall back to visual similarity,
                # but only accept a strong (core) match for this weaker signal.
                if product_id not in visual_core_ids:
                    continue
            elif required_color.lower() not in search_text:
                continue

        if image_search_active and ONLINE_VISION_VERIFY:
            try:
                vision_evaluation = evaluate_candidate(product, product_kind, required_color)
            except Exception:
                continue
            if not vision_evaluation.get("accepted"):
                continue

        policy_product = dict(product)
        policy_product["product_id"] = product.get("product_id", product_id)
        policy_product["visual_color_match"] = bool(
            required_color
            and product_id in (visual_match_ids if requested_is_named else visual_core_ids)
            and (
                not ONLINE_VISION_VERIFY
                or (vision_evaluation and vision_evaluation.get("accepted"))
            )
        )
        if not product_matches_constraint(policy_product, constraint):
            continue

        results.append({
            "product_id": product.get(
                "product_id",
                product_id
            ),

            "title": product.get("title"),
            "brand": product.get("brand"),
            "category": product.get("category"),
            "audience": product.get("audience"),
            "color": product.get("color"),
            "material": product.get("material"),
            "style": product.get("style"),
            "bullet_points": product.get(
                "bullet_points"
            ),
            "description": product.get(
                "description"
            ),
            "price": product.get("price"),
            "average_rating": product.get("average_rating"),
            "review_count": product.get("review_count"),
            "verified_review_count": product.get("verified_review_count"),
            "image_url": product.get("image_url"),
            "amazon_url": product.get("amazon_url"),
            "visual_color_match": policy_product["visual_color_match"],
            "positive_review_evidence": product.get("positive_review_evidence"),
            "negative_review_evidence": product.get("negative_review_evidence"),
            "review_summary": product.get("review_summary"),
            "review_summary_ko": product.get("review_summary_ko"),
            "_needs_hydration": True,

            "hybrid_score": scores[
                product_id
            ]
        })

        if len(results) >= size:
            break

    return results


def hydrate_products(products: list[dict]) -> list[dict]:
    """Fetch heavy response-only fields once for the final reranked products."""
    pending = [product for product in products if product.get("_needs_hydration")]
    if not pending:
        return products
    try:
        response = client.mget(
            index=INDEX_NAME,
            body={"ids": [product["product_id"] for product in pending]},
            _source_includes=[
                "description", "positive_review_evidence", "negative_review_evidence",
                "review_summary", "review_summary_ko"
            ],
            request_timeout=10,
        )
        details = {
            document["_id"]: document.get("_source", {})
            for document in response.get("docs", []) if document.get("found")
        }
    except Exception:
        details = {}
    return [
        {**product, **details.get(product.get("product_id"), {}), "_needs_hydration": False}
        for product in products
    ]


# =====================================
# 직접 테스트
# =====================================

if __name__ == "__main__":

    query = input(
        "Hybrid 검색어: "
    )

    results = hybrid_search(
        query=query,
        size=5,
        category="Shoes",
        audience="Women",
        required_color="Black"
    )

    print("\n==============================")
    print("Hybrid 검색 결과")
    print("==============================")

    for index, product in enumerate(
        results,
        start=1
    ):
        print(
            f"\n{index}. "
            f"{product['title']}"
        )

        print(
            "category:",
            product["category"]
        )

        print(
            "color:",
            product["color"]
        )

        print(
            "style:",
            product["style"]
        )

        print(
            "hybrid_score:",
            product["hybrid_score"]
        )
