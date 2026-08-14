"""Deterministic shopping policies enforced outside the language model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import math
import re


def normalize_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(normalize_text(item) for item in value)
    return str(value).lower().strip()


COLOR_TERMS = {
    "검은": "Black", "검정": "Black", "블랙": "Black", "black": "Black",
    "흰색": "White", "하얀": "White", "화이트": "White", "white": "White",
    "빨간": "Red", "레드": "Red", "red": "Red",
    "파란": "Blue", "블루": "Blue", "blue": "Blue",
    "갈색": "Brown", "브라운": "Brown", "brown": "Brown",
    "초록": "Green", "그린": "Green", "green": "Green",
    "분홍": "Pink", "핑크": "Pink", "pink": "Pink",
    # gray/grey map to one canonical spelling ("Gray", the catalog's dominant
    # form) - keeping them separate caused a same-color word to register as
    # a *conflicting* color in the hybrid_search hard-check whenever the
    # requested and catalog spellings didn't match (same bug class as the
    # 반지/반지갑 collision fixed above).
    "회색": "Gray", "그레이": "Gray", "gray": "Gray", "grey": "Gray",
    "베이지": "Beige", "beige": "Beige",
    "네이비": "Navy", "navy": "Navy",
    # These five were entirely missing despite thousands of matching catalog
    # products (Purple 2628, Yellow 2017, Orange 1168, Gold 6392, Silver
    # 9135) - a request for one of these colors silently lost its color
    # constraint on any query that also matches a PRODUCT_KIND_TERMS
    # deterministic bypass (e.g. "구두"/FormalShoes), since that path relies
    # only on this dict and never reaches the LLM's free-form translation.
    "보라": "Purple", "자주": "Purple", "퍼플": "Purple", "purple": "Purple",
    "노란": "Yellow", "노랑": "Yellow", "옐로우": "Yellow", "yellow": "Yellow",
    "주황": "Orange", "오렌지": "Orange", "orange": "Orange",
    "금색": "Gold", "골드": "Gold", "gold": "Gold",
    "은색": "Silver", "실버": "Silver", "silver": "Silver",
}

# Common Korean transliterations for major fashion brands, mapped to the
# lowercase substring that actually appears in the catalog's own `brand`
# field (checked directly against data/amazon_fashion/products.jsonl, e.g.
# adidas is stored lowercase, PUMA is all-caps, "The North Face" is stored
# as "THE NORTH FACE" - normalize_text lowercases both sides before the
# substring check, so only the substring itself needs to be right here).
# Kept deterministic (rather than left entirely to the translation LLM)
# because a silently-dropped brand name is worse than a mistranslated one:
# without a hard filter, the search still "succeeds" with unrelated
# products and nothing tells the user their brand request was ignored.
BRAND_TERMS = {
    "나이키": "nike", "nike": "nike",
    "아디다스": "adidas", "adidas": "adidas",
    "노스페이스": "the north face", "north face": "the north face",
    "뉴발란스": "new balance", "new balance": "new balance",
    "컨버스": "converse", "converse": "converse",
    "반스": "vans", "vans": "vans",
    "리복": "reebok", "reebok": "reebok",
    "언더아머": "under armour", "under armour": "under armour",
    "푸마": "puma", "puma": "puma",
    "카시오": "casio", "casio": "casio",
    "세이코": "seiko", "seiko": "seiko",
    "코치": "coach", "coach": "coach",
    "마이클코어스": "michael kors", "michael kors": "michael kors",
    "캘빈클라인": "calvin klein", "calvin klein": "calvin klein",
    "게스": "guess", "guess": "guess",
    "스케쳐스": "skechers", "스케처스": "skechers", "skechers": "skechers",
    "크록스": "crocs", "crocs": "crocs",
    "리바이스": "levi", "levi's": "levi", "levis": "levi",
    "랄프로렌": "ralph lauren", "폴로": "polo ralph lauren", "ralph lauren": "ralph lauren",
    "타미힐피거": "tommy hilfiger", "tommy hilfiger": "tommy hilfiger",
    "포시즌": "fossil", "fossil": "fossil",
    "팀버랜드": "timberland", "timberland": "timberland",
    "컬럼비아": "columbia", "columbia": "columbia",
    "칼하트": "carhartt", "carhartt": "carhartt",
    "디즈니": "disney", "disney": "disney",
}

CATEGORY_TERMS = {
    "Shoes": ("신발", "구두", "운동화", "샌들", "부츠", "로퍼", "스니커", "슬리퍼", "shoe", "sneaker", "sandal", "boot", "loafer", "slipper"),
    "Watches": ("시계", "손목시계", "스마트워치", "watch", "smartwatch"),
    "Jewelry": ("주얼리", "보석", "목걸이", "귀걸이", "팔찌", "반지", "necklace", "earring", "bracelet", "ring", "jewelry"),
    # "반지갑" (bifold wallet) is listed explicitly and longer than "반지"
    # (ring) in Jewelry above, so the longest-match rule in
    # detect_requested_category resolves the "반지"/"반지갑" collision correctly.
    "Bags": ("가방", "핸드백", "백팩", "반지갑", "지갑", "토트백", "handbag", "backpack", "purse", "wallet", "bifold", "tote", "bag"),
    "Clothing": ("옷", "의류", "셔츠", "드레스", "원피스", "재킷", "코트", "패딩", "바지", "청바지", "반바지", "치마", "shirt", "dress", "jacket", "coat", "pants", "jeans", "shorts", "skirt", "hoodie"),
    "Accessories": ("액세서리", "벨트", "모자", "스카프", "장갑", "선글라스", "넥타이", "belt", "hat", "scarf", "glove", "sunglass", "tie"),
}

QUERY_EXPANSIONS = {
    "운동화": "sneakers running shoes",
    "구두": "formal dress shoes",
    "출근": "office work formal",
    "가방": "bag handbag backpack",
    "지갑": "wallet billfold card holder",
    "백팩": "backpack rucksack",
    "시계": "watch wristwatch",
    "옷": "clothing apparel",
    "의류": "clothing apparel",
    "목걸이": "necklace jewelry",
    "귀걸이": "earrings jewelry",
    "팔찌": "bracelet bangle jewelry",
    "반지": "ring jewelry",
    "반지갑": "wallet bifold wallet",
    "청바지": "jeans denim pants",
    "반바지": "shorts short pants",
    "숏팬츠": "shorts short pants",
    "핫팬츠": "shorts hot pants",
    "슬리퍼": "slippers house shoes",
    "패딩": "puffer jacket padded jacket",
    "원피스": "dress",
    "후드": "hoodie hooded sweatshirt",
    "부츠": "boots",
    "로퍼": "loafers slip on shoes",
    "토트백": "tote bag",
    "벨트": "belt",
    "모자": "hat cap",
    "스카프": "scarf shawl wrap",
    "장갑": "gloves mittens",
    "치마": "skirt",
    "재킷": "jacket",
    "여성": "women women's",
    "여자": "women women's",
    "남성": "men men's",
    "남자": "men men's",
    "검정": "black",
    "검은": "black",
    "흰색": "white",
    "데일리": "daily casual everyday",
    "편한": "comfortable comfort",
    "편안": "comfortable comfort",
    "가벼운": "lightweight",
    "여름": "summer",
    "겨울": "winter warm",
    "선물": "gift",
}

PRODUCT_KIND_TERMS = {
    "Sneakers": ("운동화", "스니커즈", "sneaker", "sneakers", "running shoe", "running shoes", "walking shoe", "walking shoes", "trainer"),
    "Loafers": ("로퍼", "loafer", "loafers", "slip-on loafer", "slip on loafer"),
    "FormalShoes": ("구두", "정장화", "dress shoe", "dress shoes", "formal shoe", "formal shoes", "loafer", "loafers", "oxford", "oxfords"),
    "Sandals": ("샌들", "sandal", "sandals", "flip flop", "flip-flop", "slides"),
    "Coats": ("코트", "coat", "coats", "puffer jacket", "overcoat", "parka"),
    "Sunglasses": ("선글라스", "sunglass", "sunglasses", "sun glasses", "eyewear"),
    # "반바지" is easy for the translation LLM to mis-hear as "청바지"
    # (jeans) since both end in 바지 - handle it deterministically instead
    # of trusting the LLM's Korean->English translation for this term.
    "Shorts": ("반바지", "숏팬츠", "핫팬츠", "쇼츠", "shorts", "short pants", "bermuda shorts", "cargo shorts"),
}

CATEGORY_EXCLUSIONS = {
    # Catalog data-quality noise: accessories filed under a broad category
    # that aren't the product itself (e.g. a luggage tag under "Bags" whose
    # title mentions "backpack" and "sports bag" only to describe what it
    # attaches to).
    "Bags": ("luggage tag", "bag tag", "bag charm", "keychain", "key chain"),
}

PRODUCT_KIND_EXCLUSIONS = {
    "Sneakers": (
        "steel toe", "safety shoe", "work shoe", "work boot", "construction", "combat boot", "boot",
        "sock", "socks", "shoe care", "care kit", "care pack", "shoe accessory", "shoelace", "shoe lace",
        "crease protector", "shoe protector", "cleaning kit",
        "cleaner", "detergent", "eraser",
        "slipper", "slippers", "sandal", "sandals", "clog", "clogs", "wallet",
    ),
    "Loafers": ("shoelace", "shoe lace", "sneaker", "running shoe", "sandal", "boot", "sock", "slipper", "slippers", "wallet"),
    "FormalShoes": ("sneaker", "sneakers", "running shoe", "running shoes", "walking shoe", "walking shoes", "athletic shoe", "steel toe", "work boot", "sock", "socks", "slipper", "sandal", "clog", "shoe repair", "replacement", "half sole", "shoelace", "shoe lace", "wallet"),
    "Sandals": ("steel toe", "work shoe", "work boot", "construction", "sneaker", "running shoe", "sock", "socks", "wallet"),
    "Coats": ("legging", "leggings", "pants", "trouser", "shirt", "dress", "skirt", "tights"),
    "Sunglasses": ("face mask", "scarf", "hat", "visor", "cap", "goggle case"),
    "Shorts": ("jeans", "denim pants", "trouser", "trousers", "legging", "leggings", "jumpsuit", "overall", "skirt", "dress"),
}

# Sleeve length is a real attribute request ("반팔 티셔츠") that was being
# accepted into the semantic/vector query but never enforced as a hard
# filter, so a strong non-sleeve signal (color, "summer", brand) could still
# rank an explicitly wrong-length item ("Long Sleeve ...") into the top 3.
# Exclusion-only (no positive requirement) because most titles don't
# mention sleeve length at all, and those shouldn't be dropped just for
# staying silent on it.
SLEEVE_REQUEST_TERMS = {
    "반팔": "Short", "반소매": "Short", "half sleeve": "Short",
    "short sleeve": "Short", "short-sleeve": "Short",
    "긴팔": "Long", "긴소매": "Long",
    "long sleeve": "Long", "long-sleeve": "Long",
}

SLEEVE_EXCLUSION_TERMS = {
    "Short": ("long sleeve", "long-sleeve", "longsleeve"),
    "Long": ("short sleeve", "short-sleeve", "sleeveless", "tank top", "cap sleeve"),
}


def detect_requested_sleeve(message: str) -> str | None:
    text = normalize_text(message)
    matches = [(term, value) for term, value in SLEEVE_REQUEST_TERMS.items() if term in text]
    if not matches:
        return None
    return max(matches, key=lambda pair: len(pair[0]))[1]


# A handful of product types are overwhelmingly one gender in this catalog
# regardless of who's shopping - a profile's preferred_gender default (added
# so mixed-gender results don't leak into a neutral category like shoes or
# bags) actively backfires here: defaulting "원피스" (dress) to a Men's
# profile doesn't just fail to help, it makes product_matches_constraint
# exclude products explicitly labeled "Women's" while unlabeled unisex
# costume/cosplay items - which happen to satisfy a loose Men constraint -
# pass through instead. This signal should win over the profile default,
# though an explicit audience in the message (여성용/남성용) still wins over
# this, same as it already wins over the profile default.
INHERENT_AUDIENCE_TERMS = {
    "원피스": "Women", "드레스": "Women", "dress": "Women",
    "브라": "Women", "브래지어": "Women", "bra": "Women",
    "치마": "Women", "skirt": "Women",
}


def detect_inherent_audience(message: str) -> str | None:
    text = normalize_text(message)
    matches = [(term, value) for term, value in INHERENT_AUDIENCE_TERMS.items() if term in text]
    if not matches:
        return None
    return max(matches, key=lambda pair: len(pair[0]))[1]


# A contrastive follow-up ("이거 말고 다른 색으로", "다른 것도 보여줘") asks for
# results different from what's already on screen, but names no new
# attribute of its own for compile_search_intent to search on - without
# excluding the previously-shown product ids, the search plan comes out
# identical to the prior turn and the same top-ranked items come back,
# which reads as the assistant ignoring "not this one."
_ALTERNATIVE_TERMS = (
    "다른 색", "다른색", "다른 거", "다른거", "다른 것", "다른상품", "다른 상품",
    "이거 말고", "그거 말고", "말고 다른", "말고다른",
    "different color", "something else", "other one", "another one",
)


def wants_alternative(message: str) -> bool:
    text = normalize_text(message)
    return any(term in text for term in _ALTERNATIVE_TERMS)


# A bare attribute question ("가격은 얼마야?", "평점은 어때?") right after
# products were shown names no product of its own to search for - it can
# only sensibly be about what's already on screen. Treating it as a fresh
# search sends it through hybrid_search with an empty/meaningless query,
# which either returns unrelated junk or - since a real search plan needs
# *some* signal - 0 results with a "조건에 맞는 상품을 찾지 못했습니다" answer
# that's flatly wrong (nothing was searched for, so nothing to not-find).
_ATTRIBUTE_QUESTION_TERMS = ("가격", "얼마", "평점", "별점", "리뷰", "후기", "재고", "사이즈", "치수", "배송")


def asks_about_shown_products(message: str, has_products: bool) -> bool:
    if not has_products:
        return False
    text = normalize_text(message)
    has_attribute_question = any(term in text for term in _ATTRIBUTE_QUESTION_TERMS)
    if not has_attribute_question:
        return False
    has_own_product_signal = bool(
        detect_requested_category(message)
        or detect_requested_product_kind(message)
        or detect_requested_color(message)
        or detect_requested_brand(message)
    )
    return not has_own_product_signal


def detect_requested_sort(message: str) -> str | None:
    """A ranking request against an already-shown set ("그 중에서 제일 평점
    높은 거", "더 저렴한 순으로") - distinct from a fresh "find me something
    cheaper" search, which is handled by wants_alternative/a new query."""
    text = normalize_text(message)
    superlative = any(term in text for term in ("제일", "가장", "최고", "best", "most"))
    if any(term in text for term in ("평점", "별점", "rating")) and (superlative or "높은" in text):
        return "rating_desc"
    if any(term in text for term in ("리뷰", "후기", "review")) and (superlative or "많은" in text):
        return "reviews_desc"
    if any(term in text for term in ("저렴", "싼", "cheap", "낮은 가격")):
        return "price_asc"
    if any(term in text for term in ("비싼", "expensive", "높은 가격")):
        return "price_desc"
    return None


def wants_single_top_result(message: str) -> bool:
    text = normalize_text(message)
    return any(term in text for term in ("제일", "가장", "최고", "best"))


def sort_products(products: list[dict], sort_key: str | None) -> list[dict]:
    if sort_key == "rating_desc":
        return sorted(products, key=lambda p: float(p.get("average_rating") or 0), reverse=True)
    if sort_key == "reviews_desc":
        return sorted(products, key=lambda p: int(p.get("review_count") or 0), reverse=True)
    if sort_key in ("price_asc", "price_desc"):
        priced = [p for p in products if p.get("price") is not None]
        unpriced = [p for p in products if p.get("price") is None]
        priced.sort(key=lambda p: float(p["price"]), reverse=(sort_key == "price_desc"))
        return priced + unpriced
    return products


def expand_search_query(message: str) -> str:
    """Add a small deterministic English bridge for the English catalog."""
    text = normalize_text(message)
    additions = [english for term, english in QUERY_EXPANSIONS.items() if term in text]
    return " ".join(dict.fromkeys([message.strip(), *additions])).strip()


def detect_requested_color(message: str) -> str | None:
    text = normalize_text(message)
    return next((value for term, value in COLOR_TERMS.items() if term in text), None)


def detect_requested_audience(message: str) -> str | None:
    text = normalize_text(message)
    if any(term in text for term in ("아동", "어린이", "키즈", "남아", "여아", "kids", "kid", "toddler", "children")):
        return "Kids"
    if any(term in text for term in ("여성", "여자", "우먼", "women", "woman")):
        return "Women"
    if any(term in text for term in ("남성", "남자", "맨즈", "men", "man")):
        return "Men"
    return None


def detect_requested_brand(message: str) -> str | None:
    text = normalize_text(message)
    matches = [(term, brand) for term, brand in BRAND_TERMS.items() if term in text]
    if not matches:
        return None
    return max(matches, key=lambda pair: len(pair[0]))[1]


def detect_requested_brands(message: str) -> tuple[str, ...]:
    """All distinct brands named in the message, in the order first mentioned.

    Used only for an explicit "compare brand A vs brand B" request - unlike
    detect_requested_brand (which picks the single longest-matching alias,
    right for narrowing a normal search to one brand), a comparison request
    naming two brands needs both kept so neither gets silently dropped.
    """
    text = normalize_text(message)
    found = []
    for term, brand in BRAND_TERMS.items():
        if term in text and brand not in found:
            found.append(brand)
    return tuple(found)


_COMPARISON_TERMS = ("비교", "대비", "vs", "compare")


def wants_brand_comparison(message: str) -> bool:
    """A fresh request naming 2+ brands and asking to compare them.

    Distinct from classify_intent's "compare" bucket, which only fires when
    products are already on screen (referring back to shown items) - this
    fires on the very first message, e.g. "나이키랑 아디다스 운동화 비교해줘".
    """
    text = normalize_text(message)
    return any(term in text for term in _COMPARISON_TERMS)


def detect_requested_category(message: str) -> str | None:
    text = normalize_text(message)
    matches = [
        (term, category)
        for category, terms in CATEGORY_TERMS.items()
        for term in terms
        if term in text
    ]
    if not matches:
        return None
    # Prefer the longest/most specific matching term - a short term can be a
    # false-positive substring of a longer, unrelated compound word (e.g.
    # "반지" (ring) inside "반지갑" (wallet)); the longer term wins.
    return max(matches, key=lambda pair: len(pair[0]))[1]


def detect_requested_product_kind(message: str) -> str | None:
    text = normalize_text(message)
    matches = [
        (term, kind)
        for kind, terms in PRODUCT_KIND_TERMS.items()
        for term in terms
        if term in text
    ]
    if not matches:
        return None
    return max(matches, key=lambda pair: len(pair[0]))[1]


SHOPPING_SIGNAL_TERMS = (
    "추천", "찾아", "찾고", "보여", "골라", "알려줘", "알려 줘", "구매", "사고 싶", "사고싶",
    "구입", "얼마", "가격", "가성비", "리뷰", "후기", "재고", "사이즈", "치수", "브랜드",
    "인기", "베스트", "쇼핑", "상품", "제품", "선물",
    "recommend", "buy", "price", "shop", "product", "review", "best", "cheap",
)


def has_specific_shopping_signal(message: str) -> bool:
    """A concrete catalog signal: a recognized category, color, audience or kind.

    Unlike a generic request verb ("추천해줘"), this can't be about the wrong
    subject — matching one of these means the message names something we
    actually sell.
    """
    return bool(
        detect_requested_category(message)
        or detect_requested_color(message)
        or detect_requested_audience(message)
        or detect_requested_product_kind(message)
    )


def looks_like_shopping_request(message: str) -> bool:
    """A loose, deterministic signal that a message is about the catalog.

    Used only to route otherwise-unclassified messages between "search" and
    "chitchat" — it never gates or narrows an actual search. Messages that
    only match a generic verb here (no concrete category/color/audience/kind)
    are still ambiguous — see query_understanding.is_shopping_related for the
    flexible follow-up check on that residual bucket.
    """
    if has_specific_shopping_signal(message):
        return True
    text = normalize_text(message)
    return any(term in text for term in SHOPPING_SIGNAL_TERMS)


_MORE_RECOMMENDATIONS_TERMS = (
    "더 많은 상품", "더 추천해줘", "더 추천해 줘", "더 추천받", "more recommendations", "show me more",
)


def wants_more_recommendations(message: str) -> bool:
    """Detects the dedicated "show more" follow-up, not a generic new search.

    Used to exclude already-shown products from a repeat search so clicking
    the button surfaces a fresh set instead of the same top matches again.
    """
    text = normalize_text(message)
    return any(term in text for term in _MORE_RECOMMENDATIONS_TERMS)


_COMPARE_REFERENCE_TERMS = (
    "비교", "차이", "그중", "그 중", "이중", "이 중", "그것들 중", "이것들 중",
    "첫 번째", "두 번째", "이 상품", "추천 상품", "자세히", "compare",
    "리뷰", "후기", "review", "평가", "평점", "별점", "다른 상품", "다른상품",
)


def classify_intent(message: str, has_products: bool = False) -> str:
    """Cheap, deterministic router. Search is the safe shopping default."""
    text = normalize_text(message)
    if any(term in text for term in (
        "내 취향", "나의 취향", "쇼핑 취향", "내 선호", "나의 선호", "내 프로필",
        "my preference", "my shopping style", "what do i like",
    )):
        return "profile"
    if any(term in text for term in (
        "주문", "배송", "구매 내역", "주문 내역", "order", "delivery",
        "결제", "결재", "payment", "paid",
    )):
        return "orders"
    if has_products and (
        any(term in text for term in _COMPARE_REFERENCE_TERMS)
        or asks_about_shown_products(message, has_products)
    ):
        return "compare"
    if any(term == text or text.startswith(term + " ") for term in ("안녕", "안녕하세요", "hello", "hi")):
        return "greeting"
    if not looks_like_shopping_request(message):
        return "chitchat"
    return "search"


_ORDER_CONFIRMATION_TERMS = ("확인", "완료", "됐어", "됐나요", "됐어요", "confirm", "confirmed")
_PAYMENT_TERMS = ("결제", "결재", "payment", "paid")


def classify_order_subintent(message: str) -> str:
    """Within the "orders" intent, tell a status question from a plain listing.

    "payment_confirmation" wins over "order_confirmation" when both a payment
    word and a confirmation word appear (e.g. "결제 확인해줘"), since the
    payment word is the more specific signal of what the user wants checked.
    """
    text = normalize_text(message)
    if any(term in text for term in _PAYMENT_TERMS):
        return "payment_confirmation"
    if any(term in text for term in _ORDER_CONFIRMATION_TERMS):
        return "order_confirmation"
    return "list"


_MENTION_STOPWORDS = {
    "with", "for", "and", "the", "from", "size", "shoes", "shoe", "women", "womens",
    "men", "mens", "black", "white", "brown", "blue", "green", "purple", "casual",
}


def filter_mentioned_products(message: str, products: list[dict]) -> list[dict]:
    """Narrow a follow-up to the specific previously-shown products the user named.

    Falls back to the full list when no distinctive title word is mentioned, so a
    generic follow-up ("이 상품들 리뷰 알려줘") still works like "compare" always did.

    The catalog is English-only, but Korean shoppers name a product in Korean
    ("카시오 시계") — a plain English-word substring check never matches that.
    A message that names a recognized category ("시계") also counts as a match
    against any candidate whose own title falls in that category; this is
    coarser than a title-word hit, but it's the only bridge available without a
    transliteration table, and it still degrades safely — it can only narrow
    the field (to one match) or leave it ambiguous (multiple/no match), never
    silently pick the wrong product.
    """
    text = normalize_text(message)
    message_category = detect_requested_category(message)
    matched = []
    for product in products:
        title = product.get("title")
        words = re.findall(r"[a-z0-9]{4,}", normalize_text(title))
        distinctive = [word for word in words if word not in _MENTION_STOPWORDS]
        category_hit = bool(message_category) and message_category == detect_requested_category(title)
        if category_hit or any(word in text for word in distinctive):
            matched.append(product)
    return matched or list(products)


def has_comfort_evidence(product: dict) -> bool:
    evidence = " ".join((normalize_text(product.get("bullet_points")), normalize_text(product.get("description"))))
    return any(term in evidence for term in ("comfort", "comfortable", "cushion", "padded", "padding", "soft", "flexible", "flexibility"))


@dataclass(frozen=True)
class ProductConstraint:
    """One canonical set of hard constraints shared by retrieval and policy checks."""

    category: str | None = None
    audience: str | None = None
    color: str | None = None
    product_kind: str | None = None
    # A tuple of 2+ brands means "any of these" (an explicit brand-vs-brand
    # comparison request) rather than "exactly this one".
    brand: str | tuple[str, ...] | None = None
    sleeve: str | None = None
    exclude_kids: bool = True
    excluded_product_ids: frozenset[str] = frozenset()
    min_rating: float | None = None


def product_matches_constraint(product: dict, constraint: ProductConstraint) -> bool:
    product_id = product.get("product_id")
    if not product_id or product_id in constraint.excluded_product_ids:
        return False
    if constraint.min_rating is not None and float(product.get("average_rating") or 0) < constraint.min_rating:
        return False

    combined = " ".join(
        normalize_text(product.get(field))
        for field in ("title", "category", "product_type", "audience", "color")
    )
    # "gray"/"grey" are the same color under two spellings - normalize so a
    # "Grey" title/color value still matches a "Gray" constraint (and vice
    # versa) instead of registering as a non-match.
    combined = re.sub(r"\bgrey\b", "gray", combined)
    explicitly_women = any(term in combined for term in ("women's", " womens ", " women ", "/women/"))
    explicitly_men = any(term in combined for term in ("men's", " mens ", " men ", "/men/"))
    explicitly_kids = any(term in combined for term in (
        "kid's", " kids ", "toddler", "children", " boys", " girls",
        "/kids/", "youth", "years old", "baby", "infant",
    ))
    if constraint.exclude_kids and explicitly_kids:
        return False
    if constraint.audience == "Kids" and not explicitly_kids:
        return False
    if constraint.audience == "Women" and explicitly_men and not explicitly_women:
        return False
    if constraint.audience == "Men" and explicitly_women:
        return False
    if constraint.color and not product.get("visual_color_match") and normalize_text(constraint.color) not in combined:
        return False
    if constraint.brand:
        # The dedicated brand field is clean and reliable in this catalog;
        # also accept a title-only hit so a product whose brand field is
        # missing/blank but names the brand in its title isn't wrongly
        # dropped. constraint.brand may arrive capitalized (e.g. the LLM
        # writes "Nike"), so normalize it the same way as the product text
        # before comparing - otherwise the case mismatch alone fails every
        # product. A tuple means "any of these" (brand-vs-brand comparison).
        required_brands = (constraint.brand,) if isinstance(constraint.brand, str) else constraint.brand
        product_brand = normalize_text(product.get("brand"))
        if not any(normalize_text(value) in product_brand or normalize_text(value) in combined for value in required_brands):
            return False
    if constraint.sleeve:
        sleeve_text = " ".join(
            normalize_text(product.get(field))
            for field in ("title", "style")
        )
        if any(term in sleeve_text for term in SLEEVE_EXCLUSION_TERMS.get(constraint.sleeve, ())):
            return False
    category_terms = CATEGORY_TERMS.get(constraint.category, ())
    if category_terms and not any(term in combined for term in category_terms):
        return False
    category_excluded_terms = CATEGORY_EXCLUSIONS.get(constraint.category, ())
    if any(term in combined for term in category_excluded_terms):
        return False
    if constraint.product_kind:
        kind_text = " ".join(
            normalize_text(product.get(field))
            for field in ("title", "category", "product_type", "style")
        )
        kind_terms = PRODUCT_KIND_TERMS.get(constraint.product_kind, ())
        excluded_terms = PRODUCT_KIND_EXCLUSIONS.get(constraint.product_kind, ())
        if kind_terms and not any(term in kind_text for term in kind_terms):
            return False
        if any(term in kind_text for term in excluded_terms):
            return False
    return True


def filter_products(
    products: Iterable[dict],
    *,
    exclude_product_ids: Iterable[str] = (),
    audience: str | None = None,
    required_color: str | None = None,
    category: str | None = None,
    requested_kind: str | None = None,
    required_brand: str | tuple[str, ...] | None = None,
    required_sleeve: str | None = None,
    exclude_kids: bool = True,
    min_rating: float | None = None,
) -> list[dict]:
    constraint = ProductConstraint(
        category=category,
        audience=audience,
        color=required_color,
        product_kind=requested_kind,
        brand=required_brand,
        sleeve=required_sleeve,
        exclude_kids=exclude_kids,
        excluded_product_ids=frozenset(exclude_product_ids),
        min_rating=min_rating,
    )
    return [product for product in products if product_matches_constraint(product, constraint)]


def rank_products(products: list[dict], limit: int = 3, profile: dict | None = None) -> list[dict]:
    """Blend relevance with Bayesian review quality and promote brand diversity."""
    if not products:
        return []
    maximum_reviews = max(int(product.get("review_count") or 0) for product in products)
    profile_data = (profile or {}).get("user", profile or {})
    preferred_brands = {
        normalize_text(value) for value in profile_data.get("preferred_brands", []) if value
    }
    preferred_colors = {
        normalize_text(value) for value in profile_data.get("preferred_colors", []) if value
    }
    style_values = profile_data.get("preferred_styles", [])
    if isinstance(style_values, str):
        style_values = style_values.split(",")
    shopping_style = profile_data.get("shopping_style", "")
    if isinstance(shopping_style, str):
        style_values = [*style_values, *shopping_style.split(",")]
    preferred_styles = {normalize_text(value) for value in style_values if normalize_text(value)}
    preferred_categories = {
        normalize_text(value) for value in profile_data.get("preferred_categories", []) if value
    }
    scored = []
    total = len(products)
    for rank, product in enumerate(products):
        relevance = (total - rank) / total
        rating_value = float(product.get("average_rating") or 0)
        review_count = int(product.get("review_count") or 0)
        # A small prior prevents a handful of perfect reviews from dominating.
        bayesian_rating = ((review_count * rating_value) + (25 * 4.0)) / (review_count + 25)
        rating = bayesian_rating / 5
        popularity = math.log1p(review_count) / math.log1p(maximum_reviews) if maximum_reviews else 0
        personalization = 0.0
        if normalize_text(product.get("brand")) in preferred_brands:
            personalization += 0.08
        if normalize_text(product.get("color")) in preferred_colors:
            personalization += 0.04
        if normalize_text(product.get("category")) in preferred_categories:
            personalization += 0.03
        product_style = normalize_text(product.get("style"))
        if any(style in product_style for style in preferred_styles):
            personalization += 0.03
        semantic_relevance = float(product.get("relevance_score") or relevance)
        scored.append((0.52 * semantic_relevance + 0.20 * relevance + 0.16 * rating + 0.07 * popularity + personalization, product))
    scored.sort(key=lambda item: item[0], reverse=True)

    unique = []
    seen = set()
    for _, product in scored:
        signature = (normalize_text(product.get("brand")), normalize_text(product.get("title")))
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(product)

    # First pass picks different brands; second pass fills gaps when the catalog
    # only contains one suitable brand.
    output = []
    seen_brands = set()
    for product in unique:
        brand = normalize_text(product.get("brand"))
        if brand and brand in seen_brands:
            continue
        output.append(product)
        if brand:
            seen_brands.add(brand)
        if len(output) >= limit:
            return output
    for product in unique:
        if product not in output:
            output.append(product)
        if len(output) >= limit:
            break
    return output


def safe_product(product: dict) -> dict:
    """Fields allowed to reach the UI; never synthesize absent commerce data."""
    allowed = (
        "product_id", "title", "brand", "category", "product_type", "audience", "color",
        "material", "style", "bullet_points", "description", "price",
        "average_rating", "review_count", "main_image_id", "image_url", "amazon_url", "visual_color_match",
        "review_summary_ko",
    )
    result = {key: product[key] for key in allowed if product.get(key) not in (None, "", [])}
    product_id = str(product.get("product_id") or "").strip().upper()
    if "amazon_url" not in result and re.fullmatch(r"[A-Z0-9]{10}", product_id):
        result["amazon_url"] = f"https://www.amazon.com/dp/{product_id}"
    return result
