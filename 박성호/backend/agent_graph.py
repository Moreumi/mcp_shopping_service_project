"""Low-token shopping workflow inspired by the AWS Rufus demo.

No LLM tool calling is used. Routing, customer context, retrieval, filtering,
cards, orders and follow-up suggestions are deterministic. The LLM is invoked
at most once to phrase a grounded product response.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import time
from typing import TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.policies import (
    classify_intent,
    classify_order_subintent,
    detect_inherent_audience,
    detect_requested_audience,
    detect_requested_brand,
    detect_requested_brands,
    detect_requested_category,
    detect_requested_color,
    detect_requested_product_kind,
    detect_requested_sleeve,
    detect_requested_sort,
    filter_mentioned_products,
    filter_products,
    has_specific_shopping_signal,
    rank_products,
    safe_product,
    sort_products,
    wants_alternative,
    wants_brand_comparison,
    wants_more_recommendations,
    wants_single_top_result,
)
from backend.order_policies import (
    judge_order_completion,
    judge_order_payment_consistency,
    judge_payment_completion,
)
from backend.response_writer import answer_stream, write_product_answer
from backend.reranker import confidence_filter, rerank_products
from backend.conversation_store import load_conversation, save_conversation
from backend.demo_persona import DEMO_ORDERS, DEMO_PERSONA
from backend.query_understanding import compile_search_intent, is_shopping_related, match_mentioned_order
from backend.ttl_cache import TTLCache
from tools.customer_context import get_orders, get_user_profile
from tools.hybrid_search import hybrid_search, hydrate_products, retrieval_preview
from tools.search_products import search_products


logger = logging.getLogger("shopping-assistant.workflow")
PERSONALIZED_USER_IDS = {
    value.strip() for value in os.getenv("DEMO_USER_IDS", "user_001").split(",")
    if value.strip() and value.strip() != "*"
}
CONTEXT_CACHE = TTLCache(int(os.getenv("CONTEXT_CACHE_TTL_SECONDS", "300")), 128)
SEARCH_CACHE = TTLCache(int(os.getenv("SEARCH_CACHE_TTL_SECONDS", "180")), 256)

_VISUAL_TERMS = (
    "색", "색상", "외형", "디자인", "무늬", "패턴", "모양", "look", "appearance",
    "design", "pattern", "striped", "floral", "plaid",
)


def _retrieval_mode(message: str, color: str | None, brand) -> str:
    """Choose the cheapest retrieval branch that can satisfy the request."""
    lowered = message.lower()
    if color or any(term in lowered for term in _VISUAL_TERMS):
        return "visual"
    if brand:
        return "keyword"
    return "semantic"


class ShoppingState(TypedDict, total=False):
    message: str
    user_id: str
    thread_id: str
    intent: str
    profile: dict
    orders_result: dict
    purchased_ids: list[str]
    previous_products: list[dict]
    products: list[dict]
    search_available: bool
    answer: str
    suggestions: list[str]
    history: list[dict]
    retrieval_attempt: int
    requested_kind: str | None
    more_requested: bool


def _last_user_turn(history: list[dict]) -> str:
    for entry in reversed(history or []):
        if entry.get("role") == "user":
            return entry.get("content", "")
    return ""


def _topic_context_turns(history: list[dict], cap: int = 6) -> tuple[str, ...]:
    """Oldest-first turns since (and including) the most recent one that
    established its own category/product-kind, up to `cap` turns back.

    A fixed 2-turn window loses the topic entirely once a conversation runs
    a few attribute-only follow-ups deep - e.g. "운동화 추천해줘" -> "검은색으로"
    -> "더 가벼운 거 있어?" -> "나이키 제품으로 보여줘": by the 4th turn, a
    2-turn window only contains "검은색으로"/"더 가벼운 거 있어?", neither of
    which says "shoes", so the brand-only follow-up loses the product type
    entirely and returns Nike apparel instead of Nike sneakers. Anchoring to
    the last category/kind-bearing turn keeps the topic in scope for as long
    as the conversation keeps refining it, not just for 2 turns.
    """
    turns = [entry.get("content", "") for entry in (history or []) if entry.get("role") == "user"]
    turns = turns[-cap:]
    anchor = 0
    for index in range(len(turns) - 1, -1, -1):
        if detect_requested_category(turns[index]) or detect_requested_product_kind(turns[index]):
            anchor = index
            break
    return tuple(turns[anchor:])


def classify_node(state: ShoppingState):
    message = state["message"]
    intent = classify_intent(message, bool(state.get("previous_products")))
    prior_turn = _last_user_turn(state.get("history", []))
    # A generic verb alone ("추천해줘") is ambiguous about subject ("영화
    # 추천해줘"); a message with no shopping signal at all defaults to
    # chitchat. Both get the flexible LLM check when a prior shopping-context
    # turn exists — a short follow-up ("가벼운 것도 있어?") carries no signal
    # of its own but is clearly shopping-related given what was just asked.
    needs_topic_check = (
        (intent == "search" and not has_specific_shopping_signal(message))
        or (intent == "chitchat" and bool(prior_turn))
    )
    if needs_topic_check:
        try:
            intent = "search" if is_shopping_related(message, prior_turn) else "chitchat"
        except Exception:
            logger.warning("topic_check_failed; defaulting to search", exc_info=True)
            intent = "search"
    return {"intent": intent}


def load_context_node(state: ShoppingState):
    intent = state["intent"]
    profile = {}
    orders_result = {"orders": []}

    cache_key = (state["user_id"], intent)
    cached = CONTEXT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        personalized = state["user_id"] in PERSONALIZED_USER_IDS
        with ThreadPoolExecutor(max_workers=2) as pool:
            profile_future = (
                pool.submit(get_user_profile, state["user_id"])
                if intent in {"search", "profile"} and personalized else None
            )
            orders_future = (
                pool.submit(get_orders, state["user_id"])
                if intent in {"search", "orders"} and personalized else None
            )
            if profile_future:
                profile = profile_future.result()
            if orders_future:
                orders_result = orders_future.result()
    except Exception:
        # The catalog demo remains usable when optional customer data is unavailable.
        if intent in {"search", "profile"} and state["user_id"] in PERSONALIZED_USER_IDS:
            profile = {"found": True, "user": {"user_id": state["user_id"], **DEMO_PERSONA}}

    if (
        intent in {"search", "profile"}
        and state["user_id"] in PERSONALIZED_USER_IDS
        and not profile.get("found")
    ):
        profile = {"found": True, "user": {"user_id": state["user_id"], **DEMO_PERSONA}}

    if (
        intent in {"search", "orders"}
        and state["user_id"] in PERSONALIZED_USER_IDS
        and not orders_result.get("orders")
    ):
        orders_result = {
            "user_id": state["user_id"],
            "count": len(DEMO_ORDERS),
            "orders": [dict(order, user_id=state["user_id"]) for order in DEMO_ORDERS],
        }

    purchased_ids = [
        order.get("product_id")
        for order in orders_result.get("orders", [])
        if order.get("product_id")
    ]
    result = {"profile": profile, "orders_result": orders_result, "purchased_ids": purchased_ids}
    CONTEXT_CACHE.set(cache_key, result)
    return result


def retrieve_node(state: ShoppingState):
    if state["intent"] == "compare":
        previous = state.get("previous_products", [])
        mentioned = filter_mentioned_products(state["message"], previous)
        # filter_mentioned_products falls back to the *entire* previous list
        # when nothing in the message matches a shown product's title or
        # category - correct for a generic "비교해줘", but wrong when the
        # message names its own product/brand that simply isn't among
        # what's currently shown (e.g. "나이키 아디다스 운동화 비교" typed
        # right after an unrelated shirt search): every previously-shown
        # item is a shirt, nothing matches, and the fallback silently
        # re-serves the shirts as if they answered the new request. Treat
        # that specific case as a fresh search instead of re-serving
        # unrelated leftovers; a real "compare what's shown" request either
        # narrows the list or names no product signal of its own.
        own_signal = bool(
            detect_requested_category(state["message"])
            or detect_requested_product_kind(state["message"])
            or detect_requested_brand(state["message"])
        )
        if mentioned != previous or not own_signal:
            # A ranking request against the shown set ("그 중에서 제일 평점
            # 높은 거", "더 저렴한 순으로") - sort before slicing rather than
            # just re-listing whatever was already shown. "제일"/"가장" asks
            # for the single best match, not another 3-card list.
            sort_key = detect_requested_sort(state["message"])
            ordered = sort_products(mentioned, sort_key) if sort_key else mentioned
            limit = 1 if sort_key and wants_single_top_result(state["message"]) else 3
            return {"products": ordered[:limit], "search_available": True}
    elif state["intent"] != "search":
        return {"products": [], "search_available": True}

    message = state["message"]
    more_requested = wants_more_recommendations(message)
    alternative_requested = wants_alternative(message)
    prior_turn = _last_user_turn(state.get("history", []))
    exclude_ids = list(state.get("purchased_ids", []))
    follow_up_context: tuple[str, ...] = ()
    if more_requested:
        # "더 추천받기" carries no product subject of its own — reuse the prior
        # turn's request so the repeat search stays on the same topic, and
        # exclude what was already shown so it surfaces a fresh set.
        if prior_turn:
            message = prior_turn
        exclude_ids += [
            product.get("product_id")
            for product in state.get("previous_products", [])
            if product.get("product_id")
        ]
    elif prior_turn and not (
        (detect_requested_category(message) or detect_requested_product_kind(message))
        and detect_requested_color(message)
        and detect_requested_audience(message)
    ):
        # A follow-up with no product type/category of its own needs the
        # prior turn(s) to know WHAT is being refined — this includes a bare
        # color or audience mention ("빨간색으로"), which has_specific_shopping_signal
        # would (wrongly, for this purpose) already call "specific enough":
        # color alone doesn't say whether it's a red t-shirt or red boots.
        # A message that DOES name its own category/kind still needs context
        # if it's missing color/audience — e.g. "검은색 바지" then "반바지"
        # should still mean black shorts, not drop the established color
        # just because the new message is self-sufficient on product type.
        # But when the current message names its own category/kind and it
        # differs from the established topic, that's a genuine topic
        # switch, not a refinement — attaching the old topic as context let
        # compile_search_intent keep the old semantic query (sneakers) even
        # after the category filter correctly switched, producing a
        # filter/query mismatch that matched nothing. The comparison must
        # be against the *anchor* turn the context actually carries (the
        # last turn that established a category/kind), not just the
        # immediately-previous turn — a chain of attribute-only follow-ups
        # ("검은색으로" → "더 가벼운 거 있어?" → "가격은 얼마야?") has no
        # category of its own in between, so comparing against only the
        # last turn would miss a switch several turns after the anchor.
        candidate_context = _topic_context_turns(state.get("history", []))
        current_signal = detect_requested_category(message) or detect_requested_product_kind(message)
        anchor_signal = (
            (detect_requested_category(candidate_context[0]) or detect_requested_product_kind(candidate_context[0]))
            if candidate_context else None
        )
        if not (current_signal and anchor_signal and current_signal != anchor_signal):
            follow_up_context = candidate_context
    if alternative_requested:
        # "이거 말고 다른 색으로" names no new attribute of its own, so without
        # excluding what's already on screen the search plan comes out
        # identical to the prior turn and the same top-ranked items come
        # back — which reads as the assistant ignoring "not this one."
        exclude_ids += [
            product.get("product_id")
            for product in state.get("previous_products", [])
            if product.get("product_id")
        ]

    # The deterministic keyword fallbacks below can't use LLM-merged context,
    # so they get a plain concatenation as a safety net; compile_search_intent
    # gets the turns as structured, explicitly-labeled context instead, so it
    # can actually merge established attributes with the new refinement.
    search_text = f"{' '.join(follow_up_context)} {message}".strip() if follow_up_context else message

    search_intent = compile_search_intent(message, follow_up_context)
    category = search_intent.category or detect_requested_category(search_text)
    audience = search_intent.audience or detect_requested_audience(search_text)
    if not audience:
        # Nothing in this message names a gender - default to the customer's
        # own profile instead of leaving the search ungated, which otherwise
        # mixes men's and women's items into the same 3-slot result and reads
        # as inconsistent. An explicit "여성용"/"men's" in the message still
        # always wins (handled above, before this default is even reached).
        # A handful of product types (dresses, bras, skirts, ...) are
        # overwhelmingly one gender regardless of who's shopping - for those,
        # this inherent signal wins over the profile default, which would
        # otherwise wrongly exclude the real matches (e.g. defaulting
        # "원피스" to a Men's profile excludes items explicitly labeled
        # "Women's" while unrelated unisex costume items slip through).
        inherent_audience = detect_inherent_audience(search_text)
        if inherent_audience:
            audience = inherent_audience
        else:
            profile_gender = ((state.get("profile") or {}).get("user") or {}).get("preferred_gender")
            if profile_gender in ("Men", "Women"):
                audience = profile_gender
    color = search_intent.color or detect_requested_color(search_text)
    brands_mentioned = detect_requested_brands(search_text)
    if len(brands_mentioned) >= 2 and wants_brand_comparison(search_text):
        # An explicit "brand A vs brand B" request - keep both so the
        # comparison doesn't collapse to a single brand's products.
        brand = brands_mentioned
    else:
        brand = search_intent.brand or detect_requested_brand(search_text)
    sleeve = detect_requested_sleeve(search_text)
    requested_kind = detect_requested_product_kind(search_text)
    retrieval_mode = _retrieval_mode(search_text, color, brand)
    attempt = int(state.get("retrieval_attempt", 0)) + 1

    # Keep the retrieval query focused. Profile preferences are used after
    # relevance, never mixed into the product identity query.
    query = search_intent.semantic_query
    if attempt > 1 and search_intent.product_phrases:
        query = " ".join(search_intent.product_phrases)

    search_available = True
    retrieval_size = 30 if requested_kind else 12
    if attempt > 1 or more_requested or alternative_requested:
        # A "more"/"different" follow-up excludes what's already shown, so
        # it needs a wider net than a first search to still surface enough
        # qualifying items.
        retrieval_size = max(retrieval_size * 3, 60)
    search_cache_key = (
        query, category, audience, color, requested_kind, brand, sleeve,
        tuple(sorted(exclude_ids)),
        tuple(search_intent.product_terms), tuple(search_intent.product_phrases),
        search_intent.exclude_kids, retrieval_size, retrieval_mode,
    )
    candidates = SEARCH_CACHE.get(search_cache_key)
    try:
        if candidates is None:
            candidates = hybrid_search(
                query=query,
                size=retrieval_size,
                category=category,
                audience=audience,
                required_color=color,
                product_kind=requested_kind,
                required_brand=brand,
                required_sleeve=sleeve,
                exclude_product_ids=exclude_ids,
                visual_query_text=search_intent.visual_query,
                product_terms=search_intent.product_terms,
                product_phrases=search_intent.product_phrases,
                exclude_kids=search_intent.exclude_kids,
                min_rating=4.0,
                retrieval_mode=retrieval_mode,
            )
            SEARCH_CACHE.set(search_cache_key, candidates)
    except Exception:
        logger.warning("hybrid_search_failed; using keyword fallback", exc_info=True)
        try:
            candidates = search_products(
                query=query,
                size=20,
                category=category,
                audience=audience,
                required_color=color,
                exclude_product_ids=exclude_ids,
                exclude_kids=search_intent.exclude_kids,
            )
        except Exception:
            logger.error("keyword_search_failed; returning safe empty result", exc_info=True)
            candidates = []
            search_available = False

    products = filter_products(
        [*state.get("products", []), *candidates] if attempt > 1 else candidates,
        exclude_product_ids=exclude_ids,
        audience=audience,
        required_color=color,
        category=category,
        requested_kind=requested_kind,
        required_brand=brand,
        required_sleeve=sleeve,
        exclude_kids=search_intent.exclude_kids,
        min_rating=4.0,
    )
    products = rerank_products(
        query,
        products,
        product_terms=search_intent.product_terms,
        product_phrases=search_intent.product_phrases,
    )
    products = confidence_filter(products)
    products = rank_products(products, limit=3, profile=state.get("profile"))
    return {
        "products": products,
        "search_available": search_available,
        "retrieval_attempt": attempt,
        "requested_kind": requested_kind,
        "more_requested": more_requested,
    }


def quality_node(state: ShoppingState):
    """A deterministic quality gate; hard constraints are never relaxed."""
    return {}


def route_after_quality(state: ShoppingState) -> str:
    if state.get("intent") != "search":
        return "respond"
    if not state.get("search_available", True):
        return "respond"
    if len(state.get("products", [])) >= 3:
        return "respond"
    # Product-kind searches already retrieve up to 240 candidates on the
    # first pass; retrying at the 250 cap adds latency with negligible recall.
    if state.get("requested_kind"):
        return "respond"
    return "retry" if int(state.get("retrieval_attempt", 0)) < 2 else "respond"


def retry_node(state: ShoppingState):
    return retrieve_node(state)


def _profile_answer(profile: dict, personalized: bool) -> str:
    if not personalized:
        return "이 데모 세션에는 저장된 개인 취향이 없습니다. 취향 설문을 완료하면 맞춤 추천에 반영할 수 있어요."

    user = profile.get("user", {}) if profile.get("found") else {}
    if not user:
        return "아직 저장된 취향 정보가 없습니다. 취향 설문을 완료하면 맞춤 추천에 반영할게요."

    fields = (
        ("선호 스타일", "preferred_styles"),
        ("선호 카테고리", "preferred_categories"),
        ("선호 색상", "preferred_colors"),
        ("선호 브랜드", "preferred_brands"),
        ("주요 사용 목적", "preferred_use_cases"),
        ("선호 착용감", "preferred_fit"),
        ("예산", "budget_range"),
        ("피하고 싶은 요소", "avoid_features"),
    )
    lines = ["현재 저장된 쇼핑 취향은 다음과 같아요."]
    for label, key in fields:
        value = user.get(key)
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value if item)
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines) if len(lines) > 1 else "아직 저장된 취향 정보가 없습니다."


def _order_answer(orders: list[dict]) -> str:
    if not orders:
        return "확인 가능한 주문 내역이 없습니다."
    status_labels = {
        "delivered": "배송 완료",
        "shipped": "배송 중",
        "processing": "주문 처리 중",
        "cancelled": "취소됨",
        "canceled": "취소됨",
    }
    lines = ["최근 주문 내역입니다."]
    for order in orders[:5]:
        label = order.get("title") or order.get("product_name") or order.get("product_id") or "상품"
        date = order.get("purchase_date") or order.get("order_date")
        raw_status = order.get("status") or order.get("delivery_status")
        status = status_labels.get(str(raw_status).lower(), raw_status) if raw_status else None
        price = order.get("price")
        price_label = f"${float(price):.2f}" if price is not None else None
        details = " · ".join(str(value) for value in (date, label, price_label, status) if value)
        lines.append(f"- {details}")
    return "\n".join(lines)


def _order_label(order: dict) -> str:
    return order.get("title") or order.get("product_id") or "상품"


def _order_confirmation_answer(order: dict) -> str:
    name = _order_label(order)
    judgment = judge_order_completion(order.get("order_status"))
    amount = order.get("payment_amount") or order.get("total_price")
    amount_label = f" (${float(amount):,.2f})" if amount is not None else ""
    if judgment == "completed":
        return f"'{name}' 주문{amount_label}은 정상적으로 완료된 상태입니다."
    if judgment == "canceled":
        return f"'{name}' 주문은 취소된 상태입니다."
    if judgment == "failed":
        return f"'{name}' 주문은 정상적으로 완료되지 않았습니다."
    return f"'{name}' 주문 상태를 확인할 수 있는 정보가 아직 없어 추가 확인이 필요합니다."


def _payment_confirmation_answer(order: dict) -> str:
    name = _order_label(order)
    judgment = judge_payment_completion(order.get("payment_status"))
    consistency = judge_order_payment_consistency(order.get("order_status"), order.get("payment_status"))
    amount = order.get("payment_amount")
    amount_label = f"${float(amount):,.2f}" if amount is not None else None
    details = " · ".join(str(value) for value in (order.get("payment_method"), amount_label, order.get("payment_date")) if value)
    suffix = f" ({details})" if details else ""
    if judgment == "completed":
        answer = f"'{name}'의 결제는 정상적으로 완료되었습니다{suffix}."
    elif judgment == "failed":
        answer = f"'{name}'의 결제가 완료되지 않았습니다. 결제 시도 중 실패한 것으로 확인됩니다."
    elif judgment == "canceled":
        answer = f"'{name}'의 결제는 취소된 상태입니다."
    else:
        answer = f"'{name}'의 결제 상태를 확인할 수 있는 정보가 아직 없어 추가 확인이 필요합니다."
    if consistency == "needs_review":
        answer += " 주문 상태와 결제 상태가 서로 일치하지 않아 고객센터를 통한 추가 확인이 필요할 수 있습니다."
    return answer


def _order_clarify_answer(candidates: list[dict], subintent: str) -> str:
    label = "결제" if subintent == "payment_confirmation" else "주문"
    names = "\n".join(f"- {_order_label(order)}" for order in candidates[:5])
    return f"{label} 확인이 필요한 상품명을 함께 말씀해 주세요. 확인 가능한 주문은 다음과 같습니다.\n{names}"


def _order_status_answer(message: str, orders: list[dict], subintent: str) -> str:
    if not orders:
        return "확인 가능한 주문 내역이 없습니다."
    matched = filter_mentioned_products(message, orders)
    # filter_mentioned_products falls back to the full list when nothing is
    # named. That fallback is right for "compare", but here we must not
    # silently guess an order, so treat "matched everything" as "named nothing".
    pool = matched if len(matched) < len(orders) else orders

    if len(pool) == 1:
        order = pool[0]
    else:
        # Deterministic title/category matching left more than one candidate
        # (or none). Only this small, per-user candidate set — never the full
        # catalog — goes to the LLM, so the round trip stays cheap and this
        # generalizes to any brand/language without a hardcoded alias table.
        index = match_mentioned_order(message, tuple(_order_label(o) for o in pool))
        order = pool[index] if index is not None else None

    if order is None:
        return _order_clarify_answer(pool, subintent)
    if subintent == "payment_confirmation":
        return _payment_confirmation_answer(order)
    return _order_confirmation_answer(order)


def respond_node(state: ShoppingState):
    intent = state["intent"]
    products = hydrate_products(state.get("products", []))
    if intent == "greeting":
        answer = "안녕하세요! 찾는 상품이나 확인하고 싶은 주문 내역을 말씀해 주세요."
    elif intent == "profile":
        answer = _profile_answer(
            state.get("profile", {}),
            state.get("user_id") in PERSONALIZED_USER_IDS,
        )
    elif intent == "orders":
        orders = state.get("orders_result", {}).get("orders", [])
        subintent = classify_order_subintent(state["message"])
        if subintent == "list":
            answer = _order_answer(orders)
        else:
            answer = _order_status_answer(state["message"], orders, subintent)
    elif intent == "chitchat":
        answer = (
            "저는 Amazon 쇼핑을 도와드리는 데 특화된 AI라, "
            "상품 추천이나 주문·배송 문의에 가장 잘 답해드릴 수 있어요. "
            "찾으시는 상품이나 확인하고 싶은 주문이 있으면 언제든 말씀해 주세요."
        )
    elif intent == "search" and not state.get("search_available", True):
        answer = "현재 상품 검색 서비스가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해 주세요."
    elif intent == "search" and not products and state.get("more_requested"):
        answer = "지금 조건에 맞는 상품은 이미 모두 보여드렸어요. 다른 조건으로 찾아볼까요?"
    else:
        answer = write_product_answer(state["message"], products, intent, state.get("history"))

    suggestions = []
    if products:
        suggestions = ["추천 상품들의 차이점을 비교해줘", "비슷한 상품을 더 보여줘"]
        if products[0].get("brand"):
            suggestions.append(f"{products[0]['brand']}의 다른 상품도 보여줘")
    elif intent in ("greeting", "chitchat"):
        suggestions = ["내 취향에 맞는 상품 추천해줘", "최근 주문 내역 보여줘"]
    elif intent == "profile":
        suggestions = ["내 취향에 맞는 상품 추천해줘", "검은색 운동화 추천해줘"]
    elif intent == "orders":
        suggestions = ["내 취향이 뭐야?", "구매한 상품을 제외하고 추천해줘"]

    history = (state.get("history", []) + [
        {"role": "user", "content": state["message"][:300]},
        {"role": "assistant", "content": answer[:500]},
    ])[-20:]
    return {
        "answer": answer,
        "products": products,
        "suggestions": suggestions[:4],
        "history": history,
    }


def build_shopping_graph(checkpointer=None):
    graph = StateGraph(ShoppingState)
    graph.add_node("classify", classify_node)
    graph.add_node("context", load_context_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("quality", quality_node)
    graph.add_node("retry", retry_node)
    graph.add_node("respond", respond_node)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "context")
    graph.add_edge("context", "retrieve")
    graph.add_edge("retrieve", "quality")
    graph.add_conditional_edges(
        "quality",
        route_after_quality,
        {"retry": "retry", "respond": "respond"},
    )
    graph.add_edge("retry", "quality")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)


SHOPPING_GRAPH = build_shopping_graph(checkpointer=InMemorySaver())


def _initial_state(message: str, user_id: str, thread_id: str, config: dict) -> ShoppingState:
    snapshot = SHOPPING_GRAPH.get_state(config)
    previous = snapshot.values if snapshot.values else load_conversation(user_id, thread_id)
    return {
        "message": message,
        "user_id": user_id,
        "thread_id": thread_id,
        "previous_products": previous.get("products", []),
        "history": previous.get("history", []),
        "products": [],
        "answer": "",
        "suggestions": [],
        "search_available": True,
        "retrieval_attempt": 0,
    }


def _result_payload(result: ShoppingState) -> dict:
    return {
        "answer": result["answer"],
        "products": [safe_product(product) for product in result.get("products", [])[:3]],
        "orders": result.get("orders_result", {}).get("orders", [])[:5] if result.get("intent") == "orders" else [],
        "suggestions": result.get("suggestions", []),
        "service_status": "ok" if result.get("search_available", True) else "search_unavailable",
        "response_mode": result.get("intent", "search"),
        "timings": result.get("timings", {}),
    }


def invoke_shopping_graph_result(
    message: str,
    user_id: str = "user_001",
    thread_id: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
    event_callback: Callable[[str, dict], None] | None = None,
    answer_callback: Callable[[str], None] | None = None,
):
    thread_id = thread_id or str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = dict(_initial_state(message, user_id, thread_id, config))
    timings = {}
    node_started = time.perf_counter()
    products_emitted = False
    def emit_preview(products):
        if event_callback:
            event_callback("products", {
                "products": [safe_product(product) for product in products[:3]],
                "response_mode": "search",
                "phase": "preview",
            })

    with answer_stream(answer_callback), retrieval_preview(emit_preview):
        for update in SHOPPING_GRAPH.stream(result, config=config, stream_mode="updates"):
            for node, values in update.items():
                timings[f"{node}_ms"] = round((time.perf_counter() - node_started) * 1000)
                node_started = time.perf_counter()
                result.update(values or {})
                if progress_callback:
                    progress_callback(node)
                if (
                    event_callback and node == "retrieve"
                    and len(result.get("products") or []) >= 3
                ):
                    # Retrieval cards can render while quality checks and the
                    # deterministic response formatter finish.
                    preview = [safe_product(product) for product in result["products"][:3]]
                    event_callback("products", {
                        "products": preview,
                        "response_mode": result.get("intent", "search"),
                        "phase": "final",
                    })
                    products_emitted = True
                elif (
                    event_callback and node == "respond" and not products_emitted
                    and result.get("products")
                ):
                    preview = [safe_product(product) for product in result["products"][:3]]
                    event_callback("products", {
                        "products": preview,
                        "response_mode": result.get("intent", "search"),
                        "phase": "final",
                    })
                    products_emitted = True
    result["timings"] = timings
    save_conversation(user_id, thread_id, result)
    return _result_payload(result)
