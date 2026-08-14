"""Live Amazon preference recommendations for the "Detail Search" feature.

The RapidAPI credential is read only from the environment (.env RAPIDAPI_KEY).
No scraped value or secret is returned to the browser. This module is
independent from New Thread's search pipeline (backend/agent_graph.py etc.)
and from the customer-service module.
"""

from __future__ import annotations

import math
import os
import re
from urllib.parse import urlparse

import requests


API_URL = "https://real-time-amazon-data.p.rapidapi.com/search"
API_HOST = "real-time-amazon-data.p.rapidapi.com"
EXCHANGE_RATE = 1350

GENDER_OPTIONS = {"남자": "Men's", "여자": "Women's"}

TOPS_OPTIONS = {
    "color": {
        "블랙 / 차콜 / 다크톤": {"query": "black", "target": ("black", "charcoal", "dark grey", "dark gray"), "conflict": ("white", "ivory", "cream", "light grey", "beige")},
        "화이트 / 아이보리 / 멜란지": {"query": "white", "target": ("white", "ivory", "cream", "heather", "grey", "gray"), "conflict": ("black", "dark navy")},
        "베이지 / 카키 / 어스톤": {"query": "khaki beige", "target": ("beige", "khaki", "brown", "tan", "olive"), "conflict": ("black", "white")},
        "포인트 / 브라이트톤 (블루, 레드, 그린 등)": {"query": "bright color", "target": ("blue", "red", "green", "yellow", "pink", "purple", "orange"), "conflict": ()},
    },
    "fit": {
        "오버핏 / 세미오버핏": {"query": "oversized fit", "target": ("oversized", "oversize", "loose", "relaxed")},
        "레귤러핏 / 스탠다드핏": {"query": "regular fit", "target": ("regular", "standard", "classic")},
        "슬림핏 / 머슬핏": {"query": "slim fit", "target": ("slim", "muscle", "fitted", "tight")},
        "크롭핏": {"query": "cropped", "target": ("crop", "cropped")},
    },
    "material": {
        "면": {"query": "cotton", "target": ("cotton", "pique")},
        "폴리에스터": {"query": "polyester", "target": ("polyester", "nylon", "dry", "spandex")},
        "기모": {"query": "fleece", "target": ("fleece", "warm", "fleece-lined", "thermal")},
        "린넨": {"query": "linen", "target": ("linen", "flax")},
        "청": {"query": "denim", "target": ("denim", "jean")},
    },
    "type": {
        "티셔츠": {"query": "t-shirt", "target": ("t-shirt", "tee", "tshirt")},
        "셔츠 / 블라우스": {"query": "shirt blouse", "target": ("shirt", "blouse", "button down")},
        "맨투맨(스웨트셔츠) / 후드티": {"query": "hoodie sweatshirt", "target": ("sweatshirt", "hoodie", "pullover")},
        "니트 / 가디건": {"query": "sweater cardigan", "target": ("knit", "cardigan", "sweater")},
    },
    "neckline": {
        "라운드넥 (크루넥)": {"query": "crewneck", "target": ("crewneck", "crew neck", "round neck")},
        "V넥 / U넥": {"query": "v-neck", "target": ("v-neck", "v neck", "u-neck")},
        "카라 / 오픈카라 / 헨리넥": {"query": "polo collar", "target": ("polo", "collar", "henley")},
        "모크넥 / 터틀넥": {"query": "turtleneck", "target": ("mock neck", "turtleneck", "turtle neck", "high neck")},
    },
    "budget": {
        "3만 원 미만": ((0, 22), 20000),
        "3만 원 ~ 5만 원": ((20, 38), 40000),
        "5만 원 ~ 10만 원": ((35, 76), 75000),
        "10만 원 이상": ((70, 999), 120000),
    },
    "season": {
        "봄/가을용 (기본)": {"target": ("spring", "autumn", "stretch", "standard")},
        "여름용 (경량/통기성)": {"target": ("summer", "lightweight", "breathable", "cool")},
        "겨울용 (기모/두꺼움)": {"target": ("winter", "fleece", "thermal", "warm", "heavyweight")},
        "사계절용": {"target": ("all season", "classic", "standard")},
    },
}

BOTTOMS_OPTIONS = {
    "color": {
        "블랙 / 차콜 / 다크톤": {"query": "black", "target": ("black", "charcoal", "dark grey", "dark gray"), "conflict": ("white", "ivory", "cream", "light grey", "beige")},
        "화이트 / 아이보리 / 멜란지": {"query": "white", "target": ("white", "ivory", "cream", "heather", "grey", "gray"), "conflict": ("black", "dark navy")},
        "베이지 / 카키 / 어스톤": {"query": "khaki beige", "target": ("beige", "khaki", "brown", "tan", "olive"), "conflict": ("black", "white")},
        "데님 블루 / 인디고": {"query": "blue denim", "target": ("blue", "indigo", "wash", "denim"), "conflict": ("white", "black")},
    },
    "fit": {
        "스트레이트 (일자)": {"query": "straight fit", "target": ("straight",)},
        "슬림 / 테이퍼드": {"query": "slim tapered", "target": ("slim", "tapered", "skinny")},
        "와이드 / 와이드레그": {"query": "wide leg", "target": ("wide", "baggy")},
        "세미와이드 / 릴랙스": {"query": "relaxed fit", "target": ("relaxed", "loose")},
    },
    "material": {
        "면": {"query": "cotton pants", "target": ("cotton", "twill", "chino")},
        "폴리에스터": {"query": "polyester pants", "target": ("polyester", "nylon", "spandex")},
        "기모": {"query": "fleece pants", "target": ("fleece", "warm", "fleece-lined", "thermal")},
        "린넨": {"query": "linen pants", "target": ("linen", "flax")},
        "청": {"query": "jeans", "target": ("denim", "jean")},
    },
    "mood": {
        "캐주얼 / 데일리 (편안하고 편하게 매일 입기 좋은 스타일)": {"target": ("casual", "daily", "basic")},
        "스트릿 / 고프코어 (힙하고 개성 있는 야외/스트릿 감성)": {"target": ("street", "cargo", "utility", "baggy")},
        "미니멀 / 세미포멀 (깔끔하고 단정한 슬랙스/격식 스타일)": {"target": ("minimal", "clean", "trouser", "tailored")},
        "스포티 / 워크아웃 (활동성이 뛰어난 운동 및 애슬레저 룩)": {"target": ("sport", "workout", "active", "track")},
    },
    "use": {
        "일상 / 마실용": {"target": ("casual", "everyday", "daily")},
        "출근 / 출장용": {"target": ("work", "office", "chino", "trouser", "dress")},
        "야외활동 / 캠핑": {"target": ("outdoor", "cargo", "hiking", "utility")},
        "운동 / 홈웨어": {"target": ("gym", "workout", "sweat", "running", "lounge")},
    },
    "budget": {
        "3만 원 미만": ((0, 22), 20000),
        "3만 원 ~ 5만 원": ((20, 38), 40000),
        "5만 원 ~ 10만 원": ((35, 76), 75000),
        "10만 원 이상": ((70, 999), 120000),
    },
    "season": {
        "봄/가을용 (기본)": {"target": ("spring", "autumn", "stretch", "standard")},
        "여름용 (경량/통기성)": {"target": ("summer", "lightweight", "breathable", "cool")},
        "겨울용 (기모/두꺼움)": {"target": ("winter", "fleece", "thermal", "warm", "heavyweight")},
        "사계절용": {"target": ("all season", "classic", "standard")},
    },
}

CATEGORY_OPTIONS = {"tops": TOPS_OPTIONS, "bottoms": BOTTOMS_OPTIONS}
TOPS_FIELDS = ("color", "fit", "material", "type", "neckline", "budget", "season")
BOTTOMS_FIELDS = ("color", "fit", "material", "mood", "use", "budget", "season")
CATEGORY_FIELDS = {"tops": TOPS_FIELDS, "bottoms": BOTTOMS_FIELDS}

# Interest-click bonus. Process-wide, not per-user - same simplification the
# rest of this demo already uses for short-lived state (e.g. backend/api.py's
# CS_STATES), fine for a single-process demo deployment.
CLICK_DATA: dict[str, int] = {}


def _price(value) -> float | None:
    match = re.search(r"\d+\.\d+|\d+", str(value or "").replace(",", ""))
    return float(match.group()) if match else None


def _validate_inputs(category: str, answers: dict, priorities: list[str]) -> None:
    if category not in CATEGORY_OPTIONS:
        raise ValueError(f"invalid category: {category}")
    if answers.get("gender") not in GENDER_OPTIONS:
        raise ValueError("invalid answer: gender")
    options = CATEGORY_OPTIONS[category]
    for key in CATEGORY_FIELDS[category]:
        if answers.get(key) not in options[key]:
            raise ValueError(f"invalid answer: {key}")
    valid_priority_keys = {"gender", *CATEGORY_FIELDS[category]}
    if len(priorities) > 3 or any(key not in valid_priority_keys for key in priorities):
        raise ValueError("priorities must contain at most three valid fields")


def build_search_keyword(category: str, answers: dict) -> str:
    options = CATEGORY_OPTIONS[category]
    gender = GENDER_OPTIONS[answers["gender"]]
    color = options["color"][answers["color"]]["query"]
    fit = options["fit"][answers["fit"]]["query"]
    if category == "tops":
        neck = options["neckline"][answers["neckline"]]["query"]
        type_kw = options["type"][answers["type"]]["query"]
        return f"{gender} {color} {fit} {neck} {type_kw}".strip()
    material = options["material"][answers["material"]]["query"]
    return f"{gender} {color} {fit} {material}".strip()


def _evaluate(category: str, product: dict, answers: dict, priorities: list[str]) -> tuple[float, float, list[str]]:
    """C1~C8 weighted match scoring. Returns (match_ratio 0..1, penalty, reasons)."""
    options = CATEGORY_OPTIONS[category]
    title = str(product.get("title") or "").lower()
    reasons: list[str] = []
    matched = 0.0
    total = 0.0
    penalty = 0.0

    def weight(key: str) -> float:
        return 2.5 if key in priorities else 1.0

    # C1 gender
    w = weight("gender")
    total += w
    female_terms = ("women", "woman", "female", "ladies")
    male_terms = ("men", "man", "male", "gents")
    if answers["gender"] == "여자":
        if any(t in title for t in female_terms):
            matched += w
            reasons.append("성별: 여성용 라인 일치")
        elif any(t in title for t in male_terms):
            penalty += 40.0
            reasons.append("성별: 남성용 키워드 감지 (불일치)")
        else:
            matched += 0.5 * w
            reasons.append("성별: 남녀 공용/유니섹스")
    else:
        if any(t in title for t in male_terms) and "women" not in title:
            matched += w
            reasons.append("성별: 남성용 라인 일치")
        elif "women" in title or "girl" in title:
            penalty += 40.0
            reasons.append("성별: 여성용 키워드 감지 (불일치)")
        else:
            matched += 0.5 * w
            reasons.append("성별: 남녀 공용/유니섹스")

    # C2 color
    w = weight("color")
    total += w
    color_info = options["color"][answers["color"]]
    has_target = any(c in title for c in color_info["target"])
    has_conflict = any(c in title for c in color_info.get("conflict", ()))
    if has_target:
        matched += w
        tag = " [우선조건]" if "color" in priorities else ""
        reasons.append(f"색상: 희망 색상 계열 일치{tag}")
    elif has_conflict:
        penalty += 50.0 if "color" in priorities else 15.0
        reasons.append("색상: 다른 색상 키워드 감지")
    else:
        matched += 0.2 * w
        reasons.append("색상: 기본 옵션/멀티 컬러")

    # C3 fit
    w = weight("fit")
    total += w
    fit_targets = options["fit"][answers["fit"]]["target"]
    if any(f in title for f in fit_targets):
        matched += w
        tag = " [우선조건]" if "fit" in priorities else ""
        reasons.append(f"핏: '{answers['fit']}' 실루엣 확인{tag}")
    else:
        matched += 0.3 * w
        reasons.append("핏: 표준 레귤러/스탠다드 핏")

    # C4 material
    w = weight("material")
    total += w
    mat_targets = options["material"][answers["material"]]["target"]
    if any(m in title for m in mat_targets):
        matched += w
        tag = " [우선조건]" if "material" in priorities else ""
        reasons.append(f"소재: '{answers['material']}' 원단 충족{tag}")
    else:
        penalty += 15.0 if "material" in priorities else 5.0
        reasons.append("소재: 원단 미명시 또는 타 소재 혼방")

    if category == "tops":
        # C5 type
        w = weight("type")
        total += w
        type_targets = options["type"][answers["type"]]["target"]
        if any(t in title for t in type_targets):
            matched += w
            tag = " [우선조건]" if "type" in priorities else ""
            reasons.append(f"종류: '{answers['type']}' 스타일 일치{tag}")
        else:
            matched += 0.3 * w
            reasons.append("종류: 기타 상의 아이템")

        # C6 neckline
        w = weight("neckline")
        total += w
        neck_targets = options["neckline"][answers["neckline"]]["target"]
        if any(n in title for n in neck_targets):
            matched += w
            tag = " [우선조건]" if "neckline" in priorities else ""
            reasons.append(f"넥라인: '{answers['neckline']}' 사양 확인{tag}")
        else:
            matched += 0.4 * w
            reasons.append("넥라인: 기본 라운드/스탠다드 넥라인")
    else:
        # C5 mood
        w = weight("mood")
        total += w
        mood_targets = options["mood"][answers["mood"]]["target"]
        if any(m in title for m in mood_targets):
            matched += w
            tag = " [우선조건]" if "mood" in priorities else ""
            reasons.append(f"무드: '{answers['mood']}' 디테일 부합{tag}")
        else:
            matched += 0.4 * w
            reasons.append("무드: 범용 기본 디자인")

        # C6 use
        w = weight("use")
        total += w
        use_targets = options["use"][answers["use"]]["target"]
        if any(u in title for u in use_targets):
            matched += w
            tag = " [우선조건]" if "use" in priorities else ""
            reasons.append(f"용도: '{answers['use']}' 목적 최적화{tag}")
        else:
            matched += 0.4 * w
            reasons.append("용도: 다양하게 착용 가능한 베이직 라인")

    # C7 budget
    w = weight("budget")
    total += w
    price_range, target_krw = options["budget"][answers["budget"]]
    price = _price(product.get("raw_price_usd"))
    if price is not None:
        krw = int(price * EXCHANGE_RATE)
        if price_range[0] <= price <= price_range[1]:
            matched += w
            tag = " [우선조건]" if "budget" in priorities else ""
            reasons.append(f"가격대: 목표 예산 부합 (약 {krw:,}원){tag}")
        else:
            matched += 0.3 * w
            reasons.append(f"가격대: 예산 구간 벗어남 (약 {krw:,}원)")
    else:
        matched += 0.5 * w
        reasons.append("가격대: 가격 미기재/변동 가능")

    # C8 season
    w = weight("season")
    total += w
    season_targets = options["season"][answers["season"]]["target"]
    if any(s in title for s in season_targets):
        matched += w
        tag = " [우선조건]" if "season" in priorities else ""
        reasons.append(f"계절감: '{answers['season']}' 사양 확인{tag}")
    else:
        matched += 0.4 * w
        reasons.append("계절감: 표준 사계절용 두께")

    match_ratio = matched / total if total else 0.0
    return match_ratio, penalty, reasons


def _calculate_score(product: dict, target_krw: float, asin: str, match_ratio: float, penalty: float) -> tuple[float, dict]:
    match_part = match_ratio * 70.0

    try:
        rating = float(product.get("rating") or 4.0)
    except (ValueError, TypeError):
        rating = 4.0
    try:
        reviews = int(product.get("reviews") or 0)
    except (ValueError, TypeError):
        reviews = 0

    bayesian = (reviews * rating + 50 * 4.3) / (reviews + 50)
    rating_part = (bayesian / 5.0) * 12.0
    review_part = min((math.log10(reviews + 1) / 4.0) * 8.0, 8.0)

    price = _price(product.get("raw_price_usd"))
    if price is not None:
        diff = abs(price * EXCHANGE_RATE - target_krw)
        price_part = max(0.0, 10.0 - diff / 5000)
    else:
        price_part = 5.0

    clicks = CLICK_DATA.get(asin, 0)
    click_bonus = min(clicks * 1.5, 5.0)

    final = match_part + rating_part + review_part + price_part + click_bonus - penalty
    score = round(max(0.0, min(final, 100.0)), 1)
    breakdown = {
        "매칭 적합도": round(match_part, 1),
        "베이지안 평점": round(rating_part, 1),
        "리뷰 수 가중치": round(review_part, 1),
        "목표 가격 적합도": round(price_part, 1),
        "관심 클릭 보너스": round(click_bonus, 1),
        "조건 불일치 감점": round(-penalty, 1) if penalty > 0 else 0.0,
    }
    return score, breakdown


def _safe_amazon_url(value: str, asin: str) -> str:
    url = str(value or "")
    parsed = urlparse(url)
    if parsed.scheme == "https" and (parsed.hostname or "").lower().endswith("amazon.com"):
        return url
    return f"https://www.amazon.com/dp/{asin}"


def _fetch_raw_products(query: str, limit: int | None = None) -> list[dict]:
    api_key = os.getenv("RAPIDAPI_KEY", "").strip()
    if not api_key:
        raise RuntimeError("RAPIDAPI_KEY is not configured")
    response = requests.get(
        API_URL,
        headers={"x-rapidapi-key": api_key, "x-rapidapi-host": API_HOST},
        params={"query": query, "page": "1", "country": "US", "sort_by": "RELEVANCE"},
        timeout=15,
    )
    response.raise_for_status()
    products = response.json().get("data", {}).get("products", [])
    return products[:limit] if limit else products


def register_click(asin: str) -> int:
    asin = str(asin or "").strip()
    if not asin:
        raise ValueError("asin is required")
    CLICK_DATA[asin] = CLICK_DATA.get(asin, 0) + 1
    return CLICK_DATA[asin]


def recommend(category: str, answers: dict, priorities: list[str], limit: int = 10) -> dict:
    _validate_inputs(category, answers, priorities)
    query = build_search_keyword(category, answers)
    options = CATEGORY_OPTIONS[category]
    _, target_krw = options["budget"][answers["budget"]]

    raw_products = _fetch_raw_products(query)
    ranked = []
    for raw in raw_products:
        asin = str(raw.get("asin") or "").strip()
        title = str(raw.get("product_title") or "").strip()
        if not asin or not title:
            continue
        price_usd_val = _price(raw.get("product_price"))
        price_krw = f"약 {int(price_usd_val * EXCHANGE_RATE):,}원" if price_usd_val else "가격 정보 확인 필요"
        product = {
            "asin": asin,
            "title": title,
            "raw_price_usd": raw.get("product_price"),
            "price_krw": price_krw,
            "rating": raw.get("product_star_rating"),
            "reviews": raw.get("product_num_ratings"),
            "image_url": raw.get("product_photo"),
            "amazon_url": _safe_amazon_url(raw.get("product_url"), asin),
        }
        match_ratio, penalty, reasons = _evaluate(category, product, answers, priorities)
        score, breakdown = _calculate_score(product, target_krw, asin, match_ratio, penalty)
        product.update({
            "score": score,
            "match_percent": round(match_ratio * 100),
            "reasons": reasons[:5],
            "breakdown": breakdown,
            "clicks": CLICK_DATA.get(asin, 0),
        })
        ranked.append(product)
    ranked.sort(key=lambda product: product["score"], reverse=True)
    return {"query": query, "priorities": priorities, "products": ranked[:limit]}


# ==========================================
# Free-text style chat (rule-based, no LLM call - deterministic like the
# rest of this codebase's policy layer)
# ==========================================

_CHAT_KEYWORD_MAP = {
    "여름": "summer lightweight",
    "겨울": "winter warm thermal",
    "봄": "spring casual",
    "가을": "autumn jacket sweater",
    "하객": "formal dress shirt blazer",
    "결혼식": "semi formal elegante",
    "린넨": "linen",
    "면": "cotton",
    "청바지": "denim jeans",
    "슬랙스": "slacks dress trousers",
    "셔츠": "shirt",
    "오버핏": "oversized fit",
    "카고": "cargo pants",
    "운동": "sport gym activewear",
    "후드": "hoodie",
    "가디건": "cardigan sweater",
    "여성": "women's",
    "남성": "men's",
    "남자": "men's",
    "여자": "women's",
    "원피스": "women dress",
}


def chat_style_advice(message: str) -> dict:
    extracted = [en for ko, en in _CHAT_KEYWORD_MAP.items() if ko in message]
    query = " ".join(dict.fromkeys(extracted)) if extracted else "casual stylish clothing"

    advice = f"요청하신 '{message[:80]}' 스타일링에 맞춰 아마존 실시간 상품을 탐색했습니다.\n\n"
    if "하객" in message or "결혼식" in message:
        advice += "단정하면서도 과하지 않은 톤다운 컬러의 슬랙스나 린넨 블레이저/셔츠 조합을 추천합니다."
    elif "여름" in message or "린넨" in message:
        advice += "통기성이 좋고 흡습성이 뛰어난 린넨 혼방 원단이나 경량 소재를 추천합니다."
    elif "오버핏" in message or "카고" in message:
        advice += "스트릿한 감성의 실루엣을 살릴 수 있는 릴랙스 핏과 카고 포켓 디테일을 추천합니다."
    else:
        advice += "요청하신 소재, 계절감, 실루엣에 맞는 상위 평가 상품을 선별했습니다."

    raw_products = _fetch_raw_products(query, limit=3)
    products = []
    for raw in raw_products:
        asin = str(raw.get("asin") or "").strip()
        title = str(raw.get("product_title") or "").strip()
        if not asin or not title:
            continue
        price_usd_val = _price(raw.get("product_price"))
        price_krw = f"약 {int(price_usd_val * EXCHANGE_RATE):,}원" if price_usd_val else "가격 변동"
        products.append({
            "asin": asin,
            "title": title,
            "price_krw": price_krw,
            "rating": raw.get("product_star_rating") or "4.2",
            "image_url": raw.get("product_photo"),
            "amazon_url": _safe_amazon_url(raw.get("product_url"), asin),
        })
    return {"advice": advice, "query": query, "products": products}
