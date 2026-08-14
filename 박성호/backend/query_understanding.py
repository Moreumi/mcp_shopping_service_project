"""Compile free-form shopping language into a small validated search plan."""

from __future__ import annotations

from functools import lru_cache
import os
import re
from typing import Literal

from dotenv import load_dotenv
import ollama
from pydantic import BaseModel, Field

from backend.policies import (
    PRODUCT_KIND_TERMS,
    detect_requested_audience,
    detect_requested_brand,
    detect_requested_category,
    detect_requested_color,
    detect_requested_product_kind,
    expand_search_query,
)


load_dotenv()
MODEL = os.getenv("OLLAMA_QUERY_MODEL", "qwen3:4b")
KEEP_ALIVE = os.getenv("OLLAMA_QUERY_KEEP_ALIVE", "2h")
_client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))


def _structured_chat(schema: type[BaseModel], system: str, content: str):
    """Run local Qwen and reject output that does not match the schema."""
    response = _client.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        format=schema.model_json_schema(),
        options={"temperature": 0, "num_predict": 300},
        think=False,
        keep_alive=KEEP_ALIVE,
    )
    message = response["message"] if isinstance(response, dict) else response.message
    raw = message["content"] if isinstance(message, dict) else message.content
    return schema.model_validate_json(raw)


def warm_query_model() -> None:
    """Load Qwen into Ollama before the first free-form user request."""
    try:
        _structured_chat(
            TopicCheck,
            TOPIC_SYSTEM_PROMPT,
            "running shoes",
        )
    except Exception:
        # Query parsing already has deterministic fallbacks; startup must not fail.
        pass


class SearchIntent(BaseModel):
    semantic_query: str = Field(min_length=2, max_length=180)
    visual_query: str = Field(min_length=2, max_length=220)
    product_terms: list[str] = Field(default_factory=list, max_length=8)
    product_phrases: list[str] = Field(default_factory=list, max_length=8)
    category: Literal["Shoes", "Watches", "Jewelry", "Bags", "Clothing", "Accessories"] | None = None
    audience: Literal["Men", "Women", "Kids", "Unisex"] | None = None
    color: str | None = Field(default=None, max_length=40)
    brand: str | None = Field(default=None, max_length=60)
    exclude_kids: bool = True


class TopicCheck(BaseModel):
    is_shopping_related: bool = Field(
        description="True only if the message asks about a purchasable fashion "
        "product, or about reviewing/ordering/comparing one."
    )


TOPIC_SYSTEM_PROMPT = """[R]
You judge topic relevance for an Amazon Fashion shopping assistant, not a general chatbot.

[C]
The store only sells fashion products: shoes, watches, jewelry, bags, clothing, accessories.

[I]
- Return is_shopping_related=true only if the message is clearly asking to find, buy,
  compare or review a fashion product sold by this store.
- A generic request verb (recommend, find, show me) is not enough by itself — the
  subject matters. "영화 추천해줘" (recommend a movie) is false; "신발 추천해줘"
  (recommend shoes) is true.
- A message may be a short follow-up to the customer's own [이전 요청] (previous request),
  such as asking for a lighter, cheaper, or different-colored version of what was just
  discussed. If so, judge it as shopping-related the same way a human agent would.
- Return false for anything unrelated to this store's products: movies, food, weather,
  general knowledge, personal questions about the assistant, other shopping sites, etc.
- When genuinely unsure, prefer true — a real search returning few results is safer
  than wrongly refusing a real request.

[F]
Return only JSON matching the provided schema."""


def _fallback_topic_check(_message: str) -> bool:
    # Unknown-model or network failure: don't block a possibly-real search.
    return True


@lru_cache(maxsize=256)
def is_shopping_related(message: str, prior_message: str = "") -> bool:
    """Flexible follow-up check for the ambiguous bucket: a message that matched
    only a generic request verb, with no recognized category/color/audience/kind.

    prior_message is the customer's own previous turn, if any — it lets a short
    reply like "가벼운 것도 있어?" be judged in context instead of in isolation.
    """
    clean = " ".join(message.split())[:300]
    content = clean if not prior_message else f"[이전 요청] {prior_message}\n[이번 메시지] {clean}"
    try:
        return _structured_chat(TopicCheck, TOPIC_SYSTEM_PROMPT, content).is_shopping_related
    except Exception:
        return _fallback_topic_check(clean)


class OrderMatch(BaseModel):
    matched_index: int | None = Field(
        default=None,
        description="0-based index of the single order the message clearly refers "
        "to, or null if the message could match more than one order or matches none.",
    )


ORDER_MATCH_SYSTEM_PROMPT = """[R]
You match a customer's message to one specific order from their own order history,
for an Amazon shopping assistant order/payment status check.

[C]
The candidate list is the customer's own past orders — never orders belonging to
someone else. The customer may name the product in Korean or English, by brand
(possibly a Korean transliteration, e.g. 카시오 = Casio, 나이키 = Nike), product
type, or color — not necessarily the exact catalog title.

[I]
- Return the 0-based index of the one order the message clearly refers to.
- Return null if the message could plausibly match more than one candidate, or
  matches none of them. Do not guess — telling the customer to clarify is better
  than checking the wrong order's status.

[F]
Return only JSON matching the provided schema."""


@lru_cache(maxsize=256)
def match_mentioned_order(message: str, candidate_titles: tuple[str, ...]) -> int | None:
    if not candidate_titles:
        return None
    clean = " ".join(message.split())[:300]
    numbered = "\n".join(f"{index}: {title}" for index, title in enumerate(candidate_titles))
    try:
        parsed = _structured_chat(
            OrderMatch,
            ORDER_MATCH_SYSTEM_PROMPT,
            f"[orders]\n{numbered}\n\n[customer message]\n{clean}",
        )
        index = parsed.matched_index
        return index if index is not None and 0 <= index < len(candidate_titles) else None
    except Exception:
        return None


SYSTEM_PROMPT = """[R]
You are a multilingual shopping-query compiler, not a product recommender.

[C]
The catalog is English Amazon Fashion. Broad categories are exactly Shoes, Watches, Jewelry, Bags, Clothing, Accessories.

[I]
- Translate the requested product and attributes into concise English.
- semantic_query must preserve the specific product type and useful attributes.
- visual_query must describe only what the requested product should look like in a product photo.
- product_terms contains 2-6 distinctive lowercase English nouns or adjectives from the requested product, without words such as recommend, show, find, product, photo.
- product_phrases contains 2-6 precise English names or aliases for the requested product. Avoid overly broad standalone words. Korean 축구 means association soccer, not American football.
- Use Clothing for jerseys, uniforms, shirts, dresses, jackets and coats.
- Use audience=null when unspecified. Set exclude_kids=true unless the user explicitly requests children or toddler products.
- Normalize a requested color to a short English color name. Use null when absent.
- If the user names a specific brand (in Korean, a Korean transliteration, or English),
  set brand to that brand's standard English name (e.g. 나이키 -> "Nike", 노스페이스 ->
  "The North Face"). Use null when no brand is named. Never invent a brand the user
  did not name.
- Never add an attribute the user did not request.
- If one or more [이전 요청] lines are given before [이번 메시지], the message is a
  follow-up in an ongoing conversation, not a standalone request. Carry forward the
  product type/category/audience/color already established in [이전 요청] unless
  [이번 메시지] explicitly changes it, and merge in whatever new condition [이번
  메시지] adds (lighter, cheaper, a different color, a different material, etc.)
  into one single, complete search plan. Ignore [이전 요청] content that the
  follow-up has nothing to do with.

[F]
Return only JSON matching the provided schema.

Examples:
축구 유니폼 추천 -> {"semantic_query":"soccer jersey uniform football club kit","visual_query":"a soccer team jersey uniform shirt","product_terms":["soccer","jersey","uniform","kit"],"product_phrases":["soccer jersey","soccer uniform","football club jersey","football kit","soccer shirt"],"category":"Clothing","audience":null,"color":null,"brand":null,"exclude_kids":true}
노란색 운동화 추천 -> {"semantic_query":"yellow sneakers athletic shoes","visual_query":"yellow sneakers athletic shoes","product_terms":["yellow","sneakers","athletic"],"product_phrases":["sneakers","athletic shoes","running shoes"],"category":"Shoes","audience":null,"color":"Yellow","brand":null,"exclude_kids":true}
여아 분홍 샌들 -> {"semantic_query":"pink sandals for girls","visual_query":"pink sandals for girls","product_terms":["pink","sandals"],"product_phrases":["sandals","flip flops"],"category":"Shoes","audience":"Kids","color":"Pink","brand":null,"exclude_kids":false}
나이키 운동화 추천해줘 -> {"semantic_query":"Nike sneakers athletic shoes","visual_query":"Nike sneakers athletic shoes","product_terms":["nike","sneakers","athletic"],"product_phrases":["nike sneakers","nike athletic shoes"],"category":"Shoes","audience":null,"color":null,"brand":"Nike","exclude_kids":true}
[이전 요청 1] 여름에 입을 반팔 티셔츠 추천해줘
[이번 메시지] 가벼운 것도 있어?
-> {"semantic_query":"lightweight breathable short sleeve summer t-shirt","visual_query":"a lightweight short sleeve summer t-shirt","product_terms":["lightweight","breathable","short sleeve","summer"],"product_phrases":["short sleeve t-shirt","summer t-shirt","lightweight t-shirt"],"category":"Clothing","audience":null,"color":null,"brand":null,"exclude_kids":true}
[이전 요청 1] 겨울에 신을 부츠 추천해줘
[이전 요청 2] 가벼운 것도 있어?
[이번 메시지] 파란색으로
-> {"semantic_query":"lightweight blue winter boots","visual_query":"lightweight blue winter boots","product_terms":["lightweight","blue","winter","boots"],"product_phrases":["winter boots","blue boots"],"category":"Shoes","audience":null,"color":"Blue","brand":null,"exclude_kids":true}
"""


def _fallback(message: str) -> SearchIntent:
    expanded = expand_search_query(message)
    english_terms = [term.lower() for term in re.findall(r"[A-Za-z][A-Za-z-]{2,}", expanded)]
    audience = detect_requested_audience(message)
    # A recognized product kind already has curated English aliases; reuse them
    # as product_phrases so the reranker's phrase-match signal isn't always 0
    # for these queries (product_phrases is otherwise LLM-only).
    kind = detect_requested_product_kind(message)
    kind_phrases = [
        term for term in PRODUCT_KIND_TERMS.get(kind, ())
        if re.fullmatch(r"[a-z][a-z -]*", term)
    ][:8]
    return SearchIntent(
        semantic_query=expanded[:180],
        visual_query=expanded[:220],
        product_terms=list(dict.fromkeys(english_terms))[:8],
        product_phrases=kind_phrases,
        category=detect_requested_category(message),
        audience=audience,
        color=detect_requested_color(message),
        brand=detect_requested_brand(message),
        exclude_kids=audience != "Kids",
    )


def _fallback_with_context(message: str, context: tuple[str, ...]) -> SearchIntent:
    """_fallback(), but still able to inherit color/audience from recent
    context when the message itself is silent on them.

    The PRODUCT_KIND_TERMS deterministic bypass exists to dodge LLM
    mistranslation risk (반바지/청바지 etc.), not to ignore the conversation -
    a category-shifting follow-up like "반바지" typed right after "검은색
    바지" should still mean black shorts, not silently drop the color just
    because "반바지" is self-sufficient on product type. The message's own
    color/audience always wins when present; context only fills a gap.
    """
    intent = _fallback(message)
    if not context or (intent.color and intent.audience):
        return intent
    context_text = " ".join(context)
    if not intent.color:
        inherited_color = detect_requested_color(context_text)
        if inherited_color:
            intent.color = inherited_color
    if not intent.audience:
        inherited_audience = detect_requested_audience(context_text)
        if inherited_audience:
            intent.audience = inherited_audience
            intent.exclude_kids = inherited_audience != "Kids"
    return intent


@lru_cache(maxsize=256)
def compile_search_intent(message: str, context: tuple[str, ...] = ()) -> SearchIntent:
    """context is up to a few of the customer's own prior turns, oldest first,
    for a short follow-up ("가벼운 것도 있어?") that carries no product signal
    of its own. Structuring them as separate [이전 요청 N] / [이번 메시지] lines
    (rather than blindly string-concatenating them) lets the model merge
    established attributes with the new refinement instead of guessing at a
    run-on sentence."""
    clean = " ".join(message.split())[:500]
    context = tuple(" ".join(turn.split())[:300] for turn in context if turn and turn.strip())
    # Common product kinds already have deterministic multilingual aliases and
    # hard policy filters. Avoiding an LLM round trip here is both faster and
    # more consistent — a small local model could still mis-translate one of
    # these (e.g. 반바지 -> 청바지); local Qwen remains available for
    # genuinely free-form items where no such alias list exists.
    if detect_requested_product_kind(clean):
        return _fallback_with_context(clean, context)
    if context:
        context_lines = "\n".join(f"[이전 요청 {index}] {turn}" for index, turn in enumerate(context, start=1))
        content = f"{context_lines}\n[이번 메시지] {clean}"
    else:
        content = clean
    try:
        intent = _structured_chat(SearchIntent, SYSTEM_PROMPT, content)
        intent.semantic_query = " ".join(intent.semantic_query.split())
        intent.visual_query = " ".join(intent.visual_query.split())
        intent.product_terms = list(dict.fromkeys(
            term.lower().strip() for term in intent.product_terms if term.strip()
        ))[:8]
        intent.product_phrases = list(dict.fromkeys(
            phrase.lower().strip() for phrase in intent.product_phrases if phrase.strip()
        ))[:8]
        placeholders = {"string", "none", "null", "unknown", "product"}
        if (
            intent.semantic_query.lower() in placeholders
            or intent.visual_query.lower() in placeholders
            or any(value in placeholders for value in intent.product_terms + intent.product_phrases)
        ):
            return _fallback(f"{' '.join(context)} {clean}".strip() if context else clean)

        # Explicit terms in the original request are stronger than an LLM
        # inference. This prevents schema-valid but contradictory plans.
        explicit_category = detect_requested_category(clean)
        explicit_audience = detect_requested_audience(clean)
        explicit_color = detect_requested_color(clean)
        explicit_brand = detect_requested_brand(clean)
        if explicit_category:
            intent.category = explicit_category
        if explicit_audience:
            intent.audience = explicit_audience
            intent.exclude_kids = explicit_audience != "Kids"
        if explicit_color:
            intent.color = explicit_color
        if explicit_brand:
            intent.brand = explicit_brand
        if intent.audience == "Kids":
            intent.exclude_kids = False
        return intent
    except Exception:
        return _fallback(f"{' '.join(context)} {clean}".strip() if context else clean)
