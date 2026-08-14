from collections import Counter
from io import BytesIO
import math
import os
import re
from dotenv import load_dotenv
import numpy as np
import pandas as pd
from PIL import Image
import requests
import streamlit as st

# 1. 환경변수 로드 및 페이지 기본 설정
load_dotenv()

st.set_page_config(
    page_title="아마존 AI 실시간 맞춤 의류 추천 & 챗봇 시스템",
    page_icon="👔",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. 커스텀 CSS & 웹 자동 번역 오류(React DOM removeChild) 차단
st.markdown(
    """
    <head>
        <meta name="google" content="notranslate" />
        <meta name="chrome" content="nocrtrans" />
    </head>
    <style>
        html, body, [data-testid="stAppViewContainer"], .main, div, span, p {
            translate: no !important;
        }
        .product-card {
            background-color: #ffffff;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 15px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.06);
            border: 1px solid #e2e8f0;
        }
        .badge-rank {
            background-color: #FF9900;
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 14px;
        }
        .badge-score {
            background-color: #146EB4;
            color: white;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: bold;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# 3. 세션 상태 초기화
if "click_data" not in st.session_state:
    st.session_state.click_data = {}

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "안녕하세요! 👔 **AI 패션 스타일리스트**입니다.\n\n원하시는 옷의 세부적인 느낌이나 TPO(시간·장소·상황), 구체적인 요구사항을 자유롭게 말씀해주세요!\n*(예: '여름 하객룩으로 입기 좋은 시원한 린넨 셔츠 추천해줘', '20대 남성 오버핏 카고 팬츠 찾고 있어')*",
        }
    ]

EXCHANGE_RATE = 1350

# RapidAPI 키 설정 (새로 발급받은 키 반영)
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
if not RAPIDAPI_KEY:
    try:
        if "RAPIDAPI_KEY" in st.secrets:
            RAPIDAPI_KEY = st.secrets["RAPIDAPI_KEY"]
    except Exception:
        pass

if not RAPIDAPI_KEY:
    RAPIDAPI_KEY = "933b8371famsh353d8611f88cb48p10c9cbjsnef93cf7d3f32"

HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com",
}

# 4. 🖼️ 네이버 CDN 가이드 이미지 매핑
GUIDE_IMAGES = {
    "tops_fit": {
        "오버핏": "https://search.pstatic.net/common/?src=http%3A%2F%2Fshopping.phinf.naver.net%2Fmain_3894276%2F38942763279.20230326123955.jpg&type=sc960_832",
        "레귤러핏": "https://search.pstatic.net/common/?src=http%3A%2F%2Fshop1.phinf.naver.net%2F20260415_229%2F1776241885302XMcF8_JPEG%2F39233345435276364_37012547.jpg&type=a340",
        "슬림핏": "https://search.pstatic.net/common/?src=https%3A%2F%2Fshop-phinf.pstatic.net%2F20260613_131%2F1781311072686Ksc9V_JPEG%2F27753390614117711_114414901.jpg&type=a340",
        "크롭핏": "https://search.pstatic.net/common/?src=https%3A%2F%2Fshop-phinf.pstatic.net%2F20220424_8%2F165079580093787JIR_JPEG%2F58260497043079903_730212950.jpg&type=a340",
    },
    "tops_neck": {
        "라운드넥": "https://search.pstatic.net/sunny/?src=http%3A%2F%2Luxboy.interhosting.kr%2F_wizfasta%2Fprada%2Fshort_sleeved_shirts%2Flj73d_bm1_f01ay_42830.jpg&type=a340",
        "V넥": "https://search.pstatic.net/common/?src=http%3A%2F%2Fshop1.phinf.naver.net%2F20250722_54%2F1753150794011P9VBM_JPEG%2F87283654123233168_1467617044.jpg&type=a340",
        "카라/오픈카라/헨리넥": "https://search.pstatic.net/common/?src=https%3A%2F%2Fshop-phinf.pstatic.net%2F20240928_3%2F1727497629319dolri_JPEG%2F4135043568336507_1582816217.jpg&type=a340",
        "모크넥/터틀넥": "https://search.pstatic.net/sunny/?src=https%3A%2F%2Fimage.msscdn.net%2Fthumbnails%2Fimages%2Fgoods_img%2F20211105%2F2219075%2F2219075_1_big.jpg%3Fw%3D780&type=a340",
    },
    "bottoms_fit": {
        "스트레이트": "https://search.pstatic.net/common/?src=https%3A%2F%2Fshop-phinf.pstatic.net%2F20251124_219%2F17639213612416tdqc_PNG%2F89552995241945655_1508996527.png&type=sc960_832",
        "슬림핏": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyMDA5MDJfMTA3%2FMDAxNTk5MDE0MDQ5OTU1.DMbAOyuHkh0TLEnlbZglcYgdhEEZMbZwX1qEAHMo9Vcg.uuGRS9GOqlHlN8W_fqaa2ReS_BU0jFi-Y-rHlDcwR6Ig.JPEG.whqudgus2%2FKakaoTalk_20200827_001937589_10.jpg&type=sc960_832",
        "와이드": "https://search.pstatic.net/common/?src=http%3A%2F%2Fshopping.phinf.naver.net%2Fmain_5891877%2F58918777061.20260214011350.jpg&type=sc960_832",
        "세미와이드": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyNjA1MDFfMTEx%2FMDAxNzc3NjA4NjM1Mzg3.8Z2e_WkQvmwkQwxzEKv4pcbt9O3sYGipXN8CqhaQwxkg.gweLDJlXnZy0lHgeYcB7lrNb2s6_H5Z8n2kmdmZEYCAg.JPEG%2F3a631497a877.jpg&type=sc960_832",
    },
    "materials": {
        "면": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyNTEwMDNfMTcw%2FMDAxNzU5NDYxMzE2OTMz.j2wBixJECpn5KkVcc-Ox4KyaI4DRtwn4dzy4dsOBAHkg.6IK-hKSTAOMPNgbF1kA_kmfmuIEHDfuRg7poKM7aZn8g.PNG%2FImage_fx.png&type=a340",
        "폴리에스터": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyNDEyMjNfMzAg%2FMDAxNzM0OTI4MjkzNzk2.ANN4XpK1dcPREF3qae1lkgjpCgYsO0zttsy0dH50Jg8g.3y2vN4HIqv6em2hfvSOMZdQjSnIo73rNCpwTIR3hfnAg.PNG%2Fimage.png&type=a340",
        "기모": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyNTAxMjNfNSAg%2FMDAxNzM3NjA4NxA2Nzc5.Q98pe-JQ2zMVlpYQc0DKLUKdjoMoaW06qBbNsuLJdXwg.FYECdmBiHlmfQM3pmgzEi07Vto5cB8QiooTYTbGY_cYg.PNG%2Fimage.png&type=a340",
        "린넨": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyM10xMTfMjUw%2FMDAxNjMzOTU3NjA4MDIz.8IC1FrHSGYauFdTZtAWt7hXuHv3wfspT-LapVvU16Psg.nMHTq-yDManCwSTynKkC-kPf44hP3o5mIFurXIPpsmMg.JPEG.ranswor%2FKakaoTalk_20211011_182437781_01.jpg&type=a340",
        "청": "https://search.pstatic.net/common/?src=http%3A%2F%2Fblogfiles.naver.net%2FMjAyMjAzMDhfMjY2%2FMDAxNxO3NzI0MjU1Mzc4.A8MrvsTG7K2oZSLOk4Lljur9Mj7x1e-v6hHS8dEnXigg.958L7ceSSZcaBZXWYztiw0LQZRqVruv0MbowDavRxZwg.JPEG.nh-motors%2F28.jpg&type=a340",
    },
}


# 5. 유틸리티 및 이미지 로더
@st.cache_data(show_spinner=False)
def load_safe_image(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return Image.open(BytesIO(res.content))
        return url
    except Exception:
        return url


def display_guide_images(category_dict):
    cols = st.columns(len(category_dict))
    for idx, (label, url) in enumerate(category_dict.items()):
        img = load_safe_image(url)
        with cols[idx]:
            st.image(img, caption=f"{idx+1}. {label}", use_container_width=True)


def parse_price_to_float(price_str):
    if not price_str or not isinstance(price_str, str):
        return None
    match = re.search(r"\d+\.\d+|\d+", price_str.replace(",", ""))
    if match:
        try:
            return float(match.group())
        except (ValueError, TypeError):
            return None
    return None


def get_price_info(c7_value):
    price_map = {
        "3만 원 미만": {"range": (0, 22), "target_krw": 20000},
        "3만 원 ~ 5만 원": {"range": (20, 38), "target_krw": 40000},
        "5만 원 ~ 10만 원": {"range": (35, 76), "target_krw": 75000},
        "10만 원 이상": {"range": (70, 999), "target_krw": 120000},
    }
    return price_map.get(c7_value, {"range": (0, 999), "target_krw": 40000})


# 6. 영문 검색 키워드 자동 생성 (설문용)
def build_search_keyword(category, user_inputs, priorities):
    gender = "Women's" if user_inputs["c1"] == "여자" else "Men's"

    color_search_map = {
        "블랙 / 차콜 / 다크톤": "black",
        "화이트 / 아이보리 / 멜란지": "white",
        "베이지 / 카키 / 어스톤": "khaki beige",
        "포인트 / 브라이트톤 (블루, 레드, 그린 등)": "bright color",
        "데님 블루 / 인디고": "blue denim",
    }
    color_kw = color_search_map.get(user_inputs["c2"], "")

    if category == "상의 (Tops)":
        fit_map = {
            "오버핏 / 세미오버핏": "oversized fit",
            "레귤러핏 / 스탠다드핏": "regular fit",
            "슬림핏 / 머슬핏": "slim fit",
            "크롭핏": "cropped",
        }
        type_map = {
            "티셔츠": "t-shirt",
            "셔츠 / 블라우스": "shirt blouse",
            "맨투맨(스웨트셔츠) / 후드티": "hoodie sweatshirt",
            "니트 / 가디건": "sweater cardigan",
        }
        neck_map = {
            "라운드넥 (크루넥)": "crewneck",
            "V넥 / U넥": "v-neck",
            "카라 / 오픈카라 / 헨리넥": "polo collar",
            "모크넥 / 터틀넥": "turtleneck",
        }
        fit_kw = fit_map.get(user_inputs["c3"], "")
        type_kw = type_map.get(user_inputs["c5"], "top")
        neck_kw = neck_map.get(user_inputs["c6"], "")
        return f"{gender} {color_kw} {fit_kw} {neck_kw} {type_kw}".strip()
    else:  # 하의 (Bottoms)
        fit_map = {
            "스트레이트 (일자)": "straight fit",
            "슬림 / 테이퍼드": "slim tapered",
            "와이드 / 와이드레그": "wide leg",
            "세미와이드 / 릴랙스": "relaxed fit",
        }
        mat_map = {
            "면": "cotton pants",
            "폴리에스터": "polyester pants",
            "기모": "fleece pants",
            "린넨": "linen pants",
            "청": "jeans",
        }
        fit_kw = fit_map.get(user_inputs["c3"], "pants")
        mat_kw = mat_map.get(user_inputs["c4"], "pants")
        return f"{gender} {color_kw} {fit_kw} {mat_kw}".strip()


# 7. C1 ~ C8 속성 평가 함수
def evaluate_product_with_priorities(product, category, user_inputs, priorities):
    title = str(product.get("title", "")).lower()
    price_val = parse_price_to_float(product.get("raw_price_usd"))

    reasons = []
    base_match_score = 0.0
    max_possible_score = 0.0
    penalty = 0.0

    def get_weight(key_name):
        return 2.5 if key_name in priorities else 1.0

    # C1. 성별
    w1 = get_weight("C1. 성별")
    max_possible_score += 1.0 * w1
    is_female = user_inputs["c1"] == "여자"
    if is_female:
        if any(k in title for k in ["women", "woman", "female", "ladies"]):
            base_match_score += 1.0 * w1
            reasons.append("✅ **C1 (성별)**: 여성용 라인 완벽 일치")
        elif "men" in title or "boy" in title:
            penalty += 40.0
            reasons.append("❌ **C1 (성별)**: 남성용 키워드 감지 (성별 불일치)")
        else:
            base_match_score += 0.5 * w1
            reasons.append("⚠️ **C1 (성별)**: 남녀 공용 / 유니섹스")
    else:
        if (
            any(k in title for k in ["men", "man", "male", "gents"])
            and "women" not in title
        ):
            base_match_score += 1.0 * w1
            reasons.append("✅ **C1 (성별)**: 남성용 라인 완벽 일치")
        elif "women" in title or "girl" in title:
            penalty += 40.0
            reasons.append("❌ **C1 (성별)**: 여성용 키워드 감지 (성별 불일치)")
        else:
            base_match_score += 0.5 * w1
            reasons.append("⚠️ **C1 (성별)**: 남녀 공용 / 유니섹스")

    # C2. 색상
    w2 = get_weight("C2. 색상")
    max_possible_score += 1.0 * w2
    color_map = {
        "블랙 / 차콜 / 다크톤": {
            "target": ["black", "charcoal", "dark grey", "dark gray"],
            "conflict": ["white", "ivory", "cream", "light grey", "beige"],
        },
        "화이트 / 아이보리 / 멜란지": {
            "target": ["white", "ivory", "cream", "heather", "grey", "gray"],
            "conflict": ["black", "dark navy"],
        },
        "베이지 / 카키 / 어스톤": {
            "target": ["beige", "khaki", "brown", "tan", "olive"],
            "conflict": ["black", "white"],
        },
        "포인트 / 브라이트톤 (블루, 레드, 그린 등)": {
            "target": [
                "blue",
                "red",
                "green",
                "yellow",
                "pink",
                "purple",
                "orange",
            ],
            "conflict": [],
        },
        "데님 블루 / 인디고": {
            "target": ["blue", "indigo", "wash", "denim"],
            "conflict": ["white", "black"],
        },
    }
    c2_info = color_map.get(user_inputs["c2"], {"target": [], "conflict": []})
    has_target_color = any(c in title for c in c2_info["target"])
    has_conflict_color = any(c in title for c in c2_info["conflict"])

    if has_target_color:
        base_match_score += 1.0 * w2
        priority_tag = " ⭐[고객 우선 조건]" if "C2. 색상" in priorities else ""
        reasons.append(f"✅ **C2 (색상)**: 희망 색상 계열 일치{priority_tag}")
    elif has_conflict_color:
        if "C2. 색상" in priorities:
            penalty += 50.0
            reasons.append(
                "❌ **C2 (색상)**: 최우선 희망 색상 불일치 (타 색상 제품)"
            )
        else:
            penalty += 15.0
            reasons.append("❌ **C2 (색상)**: 다른 색상 키워드 감지")
    else:
        base_match_score += 0.2 * w2
        reasons.append("⚠️ **C2 (색상)**: 기본 옵션 / 멀티 컬러 선택 가능")

    # C3. 핏
    w3 = get_weight("C3. 핏")
    max_possible_score += 1.0 * w3
    if category == "상의 (Tops)":
        fit_map = {
            "오버핏 / 세미오버핏": ["oversized", "oversize", "loose", "relaxed"],
            "레귤러핏 / 스탠다드핏": ["regular", "standard", "classic"],
            "슬림핏 / 머슬핏": ["slim", "muscle", "fitted", "tight"],
            "크롭핏": ["crop", "cropped"],
        }
    else:
        fit_map = {
            "스트레이트 (일자)": ["straight"],
            "슬림 / 테이퍼드": ["slim", "tapered", "skinny"],
            "와이드 / 와이드레그": ["wide", "baggy"],
            "세미와이드 / 릴랙스": ["relaxed", "loose"],
        }
    target_fits = fit_map.get(user_inputs["c3"], [])
    if any(f in title for f in target_fits):
        base_match_score += 1.0 * w3
        priority_tag = " ⭐[고객 우선 조건]" if "C3. 핏" in priorities else ""
        reasons.append(
            f"✅ **C3 (핏)**: **'{user_inputs['c3']}'** 실루엣 확인{priority_tag}"
        )
    else:
        base_match_score += 0.3 * w3
        reasons.append("⚠️ **C3 (핏)**: 표준 레귤러/스탠다드 핏")

    # C4. 소재
    w4 = get_weight("C4. 소재")
    max_possible_score += 1.0 * w4
    if category == "상의 (Tops)":
        mat_map = {
            "면": ["cotton", "pique"],
            "폴리에스터": ["polyester", "nylon", "dry", "spandex"],
            "기모": ["fleece", "warm", "fleece-lined", "thermal"],
            "린넨": ["linen", "flax"],
            "청": ["denim", "jean"],
        }
    else:
        mat_map = {
            "면": ["cotton", "twill", "chino"],
            "폴리에스터": ["polyester", "nylon", "spandex"],
            "기모": ["fleece", "warm", "fleece-lined", "thermal"],
            "린넨": ["linen", "flax"],
            "청": ["denim", "jean"],
        }
    target_mats = mat_map.get(user_inputs["c4"], [])
    if any(m in title for m in target_mats):
        base_match_score += 1.0 * w4
        priority_tag = " ⭐[고객 우선 조건]" if "C4. 소재" in priorities else ""
        reasons.append(
            f"✅ **C4 (소재)**: **'{user_inputs['c4']}'** 원단 충족{priority_tag}"
        )
    else:
        penalty += 15.0 if "C4. 소재" in priorities else 5.0
        reasons.append("❌ **C4 (소재)**: 원단 미명시 또는 타 소재 혼방")

    # C5. 상의: 옷 종류 / 하의: 무드
    if category == "상의 (Tops)":
        w5 = get_weight("C5. 옷 종류")
        max_possible_score += 1.0 * w5
        type_map = {
            "티셔츠": ["t-shirt", "tee", "tshirt"],
            "셔츠 / 블라우스": ["shirt", "blouse", "button down"],
            "맨투맨(스웨트셔츠) / 후드티": ["sweatshirt", "hoodie", "pullover"],
            "니트 / 가디건": ["knit", "cardigan", "sweater"],
        }
        target_types = type_map.get(user_inputs["c5"], [])
        if any(t in title for t in target_types):
            base_match_score += 1.0 * w5
            priority_tag = (
                " ⭐[고객 우선 조건]" if "C5. 옷 종류" in priorities else ""
            )
            reasons.append(
                f"✅ **C5 (옷 종류)**: **'{user_inputs['c5']}'** 스타일 일치{priority_tag}"
            )
        else:
            base_match_score += 0.3 * w5
            reasons.append("⚠️ **C5 (옷 종류)**: 기타 상의 아이템")
    else:
        w5 = get_weight("C5. 무드")
        max_possible_score += 1.0 * w5
        mood_map = {
            "캐주얼 / 데일리 (편안하고 편하게 매일 입기 좋은 스타일)": ["casual", "daily", "basic"],
            "스트릿 / 고프코어 (힙하고 개성 있는 야외/스트릿 감성)": ["street", "cargo", "utility", "baggy"],
            "미니멀 / 세미포멀 (깔끔하고 단정한 슬랙스/격식 스타일)": ["minimal", "clean", "trouser", "tailored"],
            "스포티 / 워크아웃 (활동성이 뛰어난 운동 및 애슬레저 룩)": ["sport", "workout", "active", "track"],
        }
        target_moods = mood_map.get(user_inputs["c5"], [])
        if any(m in title for m in target_moods):
            base_match_score += 1.0 * w5
            priority_tag = " ⭐[고객 우선 조건]" if "C5. 무드" in priorities else ""
            reasons.append(
                f"✅ **C5 (무드)**: **'{user_inputs['c5']}'** 디테일 부합{priority_tag}"
            )
        else:
            base_match_score += 0.4 * w5
            reasons.append("⚠️ **C5 (무드)**: 범용 기본 디자인")

    # C6. 상의: 넥라인 / 하의: 용도
    if category == "상의 (Tops)":
        w6 = get_weight("C6. 넥라인")
        max_possible_score += 1.0 * w6
        neck_map = {
            "라운드넥 (크루넥)": ["crewneck", "crew neck", "round neck"],
            "V넥 / U넥": ["v-neck", "v neck", "u-neck"],
            "카라 / 오픈카라 / 헨리넥": ["polo", "collar", "henley"],
            "모크넥 / 터틀넥": [
                "mock neck",
                "turtleneck",
                "turtle neck",
                "high neck",
            ],
        }
        target_necks = neck_map.get(user_inputs["c6"], [])
        if any(n in title for n in target_necks):
            base_match_score += 1.0 * w6
            priority_tag = (
                " ⭐[고객 우선 조건]" if "C6. 넥라인" in priorities else ""
            )
            reasons.append(
                f"✅ **C6 (넥라인)**: **'{user_inputs['c6']}'** 사양 확인{priority_tag}"
            )
        else:
            base_match_score += 0.4 * w6
            reasons.append("⚠️ **C6 (넥라인)**: 기본 라운드/스탠다드 넥라인")
    else:
        w6 = get_weight("C6. 용도")
        max_possible_score += 1.0 * w6
        use_map = {
            "일상 / 마실용": ["casual", "everyday", "daily"],
            "출근 / 출장용": ["work", "office", "chino", "trouser", "dress"],
            "야외활동 / 캠핑": ["outdoor", "cargo", "hiking", "utility"],
            "운동 / 홈웨어": ["gym", "workout", "sweat", "running", "lounge"],
        }
        target_uses = use_map.get(user_inputs["c6"], [])
        if any(u in title for u in target_uses):
            base_match_score += 1.0 * w6
            priority_tag = " ⭐[고객 우선 조건]" if "C6. 용도" in priorities else ""
            reasons.append(
                f"✅ **C6 (용도)**: **'{user_inputs['c6']}'** 목적 최적화{priority_tag}"
            )
        else:
            base_match_score += 0.4 * w6
            reasons.append("⚠️ **C6 (용도)**: 다양하게 착용 가능한 베이직 라인")

    # C7. 가격대
    w7 = get_weight("C7. 가격대")
    max_possible_score += 1.0 * w7
    p_info = get_price_info(user_inputs["c7"])
    min_usd, max_usd = p_info["range"]
    if price_val is not None:
        krw = int(price_val * EXCHANGE_RATE)
        if min_usd <= price_val <= max_usd:
            base_match_score += 1.0 * w7
            priority_tag = (
                " ⭐[고객 우선 조건]" if "C7. 가격대" in priorities else ""
            )
            reasons.append(
                f"✅ **C7 (가격대)**: Target 예산 부합 (약 {krw:,}원){priority_tag}"
            )
        else:
            base_match_score += 0.3 * w7
            reasons.append(f"⚠️ **C7 (가격대)**: 예산 구간 벗어남 (약 {krw:,}원)")
    else:
        base_match_score += 0.5 * w7
        reasons.append("⚠️ **C7 (가격대)**: 가격 미기재 / 변동 가능")

    # C8. 계절감
    w8 = get_weight("C8. 계절감")
    max_possible_score += 1.0 * w8
    thick_map = {
        "봄/가을용 (기본)": ["spring", "autumn", "stretch", "standard"],
        "여름용 (경량/통기성)": ["summer", "lightweight", "breathable", "cool"],
        "겨울용 (기모/두꺼움)": [
            "winter",
            "fleece",
            "thermal",
            "warm",
            "heavyweight",
        ],
        "사계절용": ["all season", "classic", "standard"],
    }
    target_thicks = thick_map.get(user_inputs["c8"], [])
    if any(t in title for t in target_thicks):
        base_match_score += 1.0 * w8
        priority_tag = " ⭐[고객 우선 조건]" if "C8. 계절감" in priorities else ""
        reasons.append(
            f"✅ **C8 (계절감)**: **'{user_inputs['c8']}'** 사양 확인{priority_tag}"
        )
    else:
        base_match_score += 0.4 * w8
        reasons.append("⚠️ **C8 (계절감)**: 표준 사계절용 두께")

    match_ratio = (
        base_match_score / max_possible_score if max_possible_score > 0 else 0.0
    )
    return match_ratio, penalty, reasons


# 8. 스코어링 엔진
def calculate_custom_score(
    product, target_krw, asin, match_ratio, penalty, priorities
):
    match_part = match_ratio * 70.0

    try:
        raw_rating = product.get("rating")
        rating = float(raw_rating) if raw_rating is not None else 4.0
    except (ValueError, TypeError):
        rating = 4.0

    try:
        raw_reviews = product.get("reviews")
        reviews = int(raw_reviews) if raw_reviews is not None else 0
    except (ValueError, TypeError):
        reviews = 0

    bayesian_rating = (reviews * rating + 50 * 4.3) / (reviews + 50)
    rating_part = (bayesian_rating / 5.0) * 12.0
    review_part = min((math.log10(reviews + 1) / 4.0) * 8.0, 8.0)

    price_val = parse_price_to_float(product.get("raw_price_usd"))
    if price_val is not None:
        krw_price = price_val * EXCHANGE_RATE
        diff = abs(krw_price - target_krw)
        price_part = max(0, 10.0 - (diff / 5000))
    else:
        price_part = 5.0

    clicks = st.session_state.click_data.get(asin, 0)
    click_bonus = min(clicks * 1.5, 5.0)

    final_score = (
        match_part + rating_part + review_part + price_part + click_bonus - penalty
    )
    clamped_score = round(max(0.0, min(final_score, 100.0)), 1)

    breakdown = {
        "C1~C8 매칭 적합도": round(match_part, 1),
        "베이지안 평점": round(rating_part, 1),
        "리뷰 수 가중치": round(review_part, 1),
        "목표 가격 적합도": round(price_part, 1),
        "관심 클릭 보너스": round(click_bonus, 1),
        "조건 불일치 감점": round(-penalty, 1) if penalty > 0 else 0.0,
    }

    return clamped_score, breakdown


# 9. RapidAPI 아마존 상품 수집 (캐싱 적용으로 호출 한도 보호)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_amazon_products_raw(query_keyword, limit=5):
    url = "https://real-time-amazon-data.p.rapidapi.com/search"
    querystring = {
        "query": query_keyword,
        "page": "1",
        "country": "US",
        "sort_by": "RELEVANCE",
    }
    try:
        res = requests.get(url, headers=HEADERS, params=querystring, timeout=10)
        if res.status_code == 200:
            raw_list = res.json().get("data", {}).get("products", [])
            parsed = []
            for p in raw_list[:limit]:
                price_usd_val = parse_price_to_float(p.get("product_price"))
                price_krw = (
                    f"약 {int(price_usd_val * EXCHANGE_RATE):,}원"
                    if price_usd_val
                    else "가격 변동"
                )
                parsed.append(
                    {
                        "title": p.get("product_title", "추천 의류"),
                        "price": price_krw,
                        "usd": p.get("product_price", "$29.99"),
                        "rating": p.get("product_star_rating", "4.2"),
                        "url": p.get(
                            "product_url", "https://www.amazon.com"
                        ),
                        "img": p.get("product_photo", ""),
                    }
                )
            return parsed
        elif res.status_code in [429, 403]:
            st.toast("⚠️ RapidAPI 호출 한도 초과 또는 인증 실패", icon="🚨")
    except Exception:
        pass
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_and_rank_amazon_products(
    category, query_keyword, user_inputs, priorities
):
    url = "https://real-time-amazon-data.p.rapidapi.com/search"
    p_info = get_price_info(user_inputs["c7"])
    querystring = {
        "query": query_keyword,
        "page": "1",
        "country": "US",
        "sort_by": "RELEVANCE",
    }

    try:
        response = requests.get(
            url, headers=HEADERS, params=querystring, timeout=12
        )
        products = (
            response.json().get("data", {}).get("products", [])
            if response.status_code == 200
            else []
        )

        parsed = []
        for p in products:
            asin = p.get("asin")
            if not asin:
                continue

            raw_rating = p.get("product_star_rating")
            raw_reviews = p.get("product_num_ratings")
            raw_price = p.get("product_price")
            raw_title = p.get("product_title")

            price_usd_val = parse_price_to_float(raw_price)
            if price_usd_val:
                display_price_krw = f"약 {int(price_usd_val * EXCHANGE_RATE):,}원"
            else:
                display_price_krw = "가격 정보 확인 필요"

            product_dict = {
                "asin": asin,
                "title": raw_title if raw_title else "추천 의류 상품",
                "raw_price_usd": raw_price if raw_price else "$29.99",
                "price_krw": display_price_krw,
                "rating": raw_rating if raw_rating is not None else 4.0,
                "reviews": raw_reviews if raw_reviews is not None else 0,
                "url": p.get("product_url", "https://www.amazon.com"),
                "img": p.get("product_photo", ""),
            }

            match_ratio, penalty, reasons = evaluate_product_with_priorities(
                product_dict, category, user_inputs, priorities
            )
            product_dict["match_ratio"] = match_ratio
            product_dict["reasons"] = reasons

            score, breakdown = calculate_custom_score(
                product_dict,
                p_info["target_krw"],
                asin,
                match_ratio,
                penalty,
                priorities,
            )
            product_dict["score"] = score
            product_dict["breakdown"] = breakdown

            parsed.append(product_dict)

        ranked = sorted(parsed, key=lambda x: x["score"], reverse=True)
        return ranked[:10]

    except Exception as e:
        st.error(f"데이터 수집 중 오류 발생: {e}")
        return []


def record_click(asin):
    st.session_state.click_data[asin] = (
        st.session_state.click_data.get(asin, 0) + 1
    )


# 10. AI 챗봇 키워드 파서 & 응답 생성기
def generate_chatbot_response(user_text):
    # 한국어 자연어 검색 키워드 자동 변환 매핑
    dict_map = {
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

    extracted_keywords = []
    for ko, en in dict_map.items():
        if ko in user_text:
            extracted_keywords.append(en)

    if not extracted_keywords:
        search_query = "casual stylish clothing"
    else:
        search_query = " ".join(extracted_keywords)

    # 답변 생성
    advice = f"💡 **스타일리스트 팁**: 요청하신 **'{user_text}'** 스타일링에 맞춰 아마존 실시간 모듈에서 최적의 상품을 탐색했습니다.\n\n"
    if "하객" in user_text or "결혼식" in user_text:
        advice += "- **스타일 제안**: 단정하면서도 과하지 않은 톤다운 컬러의 슬랙스나 린넨 블레이저/셔츠 조합을 추천합니다.\n"
    elif "여름" in user_text or "린넨" in user_text:
        advice += "- **스타일 제안**: 통기성이 좋고 흡습성이 뛰어난 린넨 혼방 원단이나 통기성 경량 탑을 추천합니다.\n"
    elif "오버핏" in user_text or "카고" in user_text:
        advice += "- **스타일 제안**: 스트릿한 감성의 실루엣을 강조할 수 있는 릴랙스 핏과 트렌디한 카고 포켓 디테일을 추천합니다.\n"
    else:
        advice += "- **스타일 제안**: 고객님의 요청 사항의 소재, 계절감, 실루엣에 맞는 상위 평가 상품들을 정밀 선별했습니다.\n"

    items = fetch_amazon_products_raw(search_query, limit=3)

    return advice, items, search_query


# 11. 사이드바 UI
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg",
        width=140,
    )
    st.title("⚙️ 시스템 대시보드")
    st.markdown("---")
    st.metric("적용 환율 (USD/KRW)", f"{EXCHANGE_RATE:,} 원")
    st.metric(
        "누적 관심 클릭 피드백", f"{sum(st.session_state.click_data.values())} 회"
    )
    st.success("🌐 RapidAPI 아마존 실시간 데이터 연동 중")

# 12. 메인 화면 UI (탭 구조 도입)
st.title("👔/👖 아마존 AI 실시간 맞춤 의류 솔루션")
st.caption(
    "설문 기반 AI 정밀 TOP 10 추천과 1:1 대화형 AI 패션 스타일리스트 챗봇을 제공합니다."
)

tab1, tab2 = st.tabs(
    ["🎯 AI 맞춤 추천 (C1~C8 설문)", "💬 1:1 AI 패션 스타일리스트 챗봇"]
)

# ==========================================
# TAB 1: 기존 C1~C8 설문 조사 기반 추천 시스템
# ==========================================
with tab1:
    category = st.radio(
        "📌 **추천받고 싶으신 카테고리를 선택하세요:**",
        ["상의 (Tops)", "하의 (Bottoms)"],
        horizontal=True,
    )

    st.divider()

    with st.form("custom_survey_form"):
        st.subheader(f"💡 1. 세부 체크리스트 ({category})")

        col1, col2 = st.columns(2)

        if category == "상의 (Tops)":
            with col1:
                c1 = st.radio("C1. 성별이 어떻게 되나요?", ["남자", "여자"], index=0)
                c2 = st.radio(
                    "C2. 선호하시는 색상 계열은 무엇인가요?",
                    [
                        "블랙 / 차콜 / 다크톤",
                        "화이트 / 아이보리 / 멜란지",
                        "베이지 / 카키 / 어스톤",
                        "포인트 / 브라이트톤 (블루, 레드, 그린 등)",
                    ],
                    index=0,
                )
                c3 = st.radio(
                    "C3. 선호하는 핏은 무엇인가요?",
                    [
                        "오버핏 / 세미오버핏",
                        "레귤러핏 / 스탠다드핏",
                        "슬림핏 / 머슬핏",
                        "크롭핏",
                    ],
                    index=0,
                )

                with st.expander("📖 [상의 핏 예시 가이드 보기]", expanded=False):
                    display_guide_images(GUIDE_IMAGES["tops_fit"])

                c4 = st.radio(
                    "C4. 선호하는 재질이 무엇일까요?",
                    ["면", "폴리에스터", "기모", "린넨", "청"],
                    index=0,
                )

                with st.expander("📖 [소재/재질 예시 가이드 보기]", expanded=False):
                    display_guide_images(GUIDE_IMAGES["materials"])

            with col2:
                c5 = st.radio(
                    "C5. 선호하는 옷 종류는 무엇인가요?",
                    [
                        "티셔츠",
                        "셔츠 / 블라우스",
                        "맨투맨(스웨트셔츠) / 후드티",
                        "니트 / 가디건",
                    ],
                    index=0,
                )
                c6 = st.radio(
                    "C6. 어떤 넥라인을 선호하시나요?",
                    [
                        "라운드넥 (크루넥)",
                        "V넥 / U넥",
                        "카라 / 오픈카라 / 헨리넥",
                        "모크넥 / 터틀넥",
                    ],
                    index=0,
                )

                with st.expander("📖 [넥라인 예시 가이드 보기]", expanded=False):
                    display_guide_images(GUIDE_IMAGES["tops_neck"])

                c7 = st.radio(
                    "C7. 선호하시거나 고려 중인 가격대는 어느 정도인가요?",
                    [
                        "3만 원 미만",
                        "3만 원 ~ 5만 원",
                        "5만 원 ~ 10만 원",
                        "10만 원 이상",
                    ],
                    index=1,
                )
                c8 = st.radio(
                    "C8. 원하시는 계절감 / 두께는 무엇인가요?",
                    [
                        "봄/가을용 (기본)",
                        "여름용 (경량/통기성)",
                        "겨울용 (기모/두꺼움)",
                        "사계절용",
                    ],
                    index=0,
                )

            priority_options = [
                "C1. 성별",
                "C2. 색상",
                "C3. 핏",
                "C4. 소재",
                "C5. 옷 종류",
                "C6. 넥라인",
                "C7. 가격대",
                "C8. 계절감",
            ]
            default_priorities = ["C2. 색상", "C3. 핏", "C5. 옷 종류"]

        else:  # 하의 (Bottoms)
            with col1:
                c1 = st.radio("C1. 성별이 어떻게 되나요?", ["남자", "여자"], index=0)
                c2 = st.radio(
                    "C2. 선호하시는 색상 계열은 무엇인가요?",
                    [
                        "블랙 / 차콜 / 다크톤",
                        "화이트 / 아이보리 / 멜란지",
                        "베이지 / 카키 / 어스톤",
                        "데님 블루 / 인디고",
                    ],
                    index=0,
                )
                c3 = st.radio(
                    "C3. 선호하는 핏은 무엇인가요?",
                    [
                        "스트레이트 (일자)",
                        "슬림 / 테이퍼드",
                        "와이드 / 와이드레그",
                        "세미와이드 / 릴랙스",
                    ],
                    index=3,
                )

                with st.expander("📖 [하의 핏 예시 가이드 보기]", expanded=False):
                    display_guide_images(GUIDE_IMAGES["bottoms_fit"])

                c4 = st.radio(
                    "C4. 선호하는 재질이 무엇일까요?",
                    ["면", "폴리에스터", "기모", "린넨", "청"],
                    index=0,
                )

                with st.expander("📖 [소재/재질 예시 가이드 보기]", expanded=False):
                    display_guide_images(GUIDE_IMAGES["materials"])

            with col2:
                c5 = st.radio(
                    "C5. 주로 어떤 스타일 또는 무드를 선호하시나요?",
                    [
                        "캐주얼 / 데일리 (편안하고 편하게 매일 입기 좋은 스타일)",
                        "스트릿 / 고프코어 (힙하고 개성 있는 야외/스트릿 감성)",
                        "미니멀 / 세미포멀 (깔끔하고 단정한 슬랙스/격식 스타일)",
                        "스포티 / 워크아웃 (활동성이 뛰어난 운동 및 애슬레저 룩)",
                    ],
                    index=0,
                )
                c6 = st.radio(
                    "C6. 주로 어떤 용도에 입을 옷을 찾으시나요?",
                    [
                        "일상 / 마실용",
                        "출근 / 출장용",
                        "야외활동 / 캠핑",
                        "운동 / 홈웨어",
                    ],
                    index=0,
                )
                c7 = st.radio(
                    "C7. 선호하시거나 고려 중인 가격대는 어느 정도인가요?",
                    [
                        "3만 원 미만",
                        "3만 원 ~ 5만 원",
                        "5만 원 ~ 10만 원",
                        "10만 원 이상",
                    ],
                    index=1,
                )
                c8 = st.radio(
                    "C8. 원하시는 계절감 / 두께는 무엇인가요?",
                    [
                        "봄/가을용 (기본)",
                        "여름용 (경량/통기성)",
                        "겨울용 (기모/두꺼움)",
                        "사계절용",
                    ],
                    index=0,
                )

            priority_options = [
                "C1. 성별",
                "C2. 색상",
                "C3. 핏",
                "C4. 소재",
                "C5. 무드",
                "C6. 용도",
                "C7. 가격대",
                "C8. 계절감",
            ]
            default_priorities = ["C2. 색상", "C3. 핏", "C7. 가격대"]

        st.divider()
        st.subheader("🔥 2. 고객 최우선 고려 조건 선택 (Top 3)")
        st.caption(
            "선택하신 3가지 항목은 추천 알고리즘에서 **2.5배 가중치**가 적용됩니다."
        )

        selected_priorities = st.multiselect(
            "가장 중요하게 생각하는 조건을 최대 3개 선택하세요:",
            options=priority_options,
            default=default_priorities,
            max_selections=3,
        )

        submit = st.form_submit_button("🚀 맞춤 가중치 반영 TOP 10 실시간 추천받기")

    if submit:
        user_inputs = {
            "c1": c1,
            "c2": c2,
            "c3": c3,
            "c4": c4,
            "c5": c5,
            "c6": c6,
            "c7": c7,
            "c8": c8,
        }
        st.session_state.current_category = category
        st.session_state.current_user_inputs = user_inputs
        st.session_state.current_priorities = selected_priorities

    if "current_user_inputs" in st.session_state:
        cur_category = st.session_state.current_category
        user_inputs = st.session_state.current_user_inputs
        priorities = st.session_state.current_priorities

        keyword = build_search_keyword(cur_category, user_inputs, priorities)

        st.info(
            f"🎯 카테고리: **{cur_category}** | 🔍 실시간 API 검색어: **'{keyword}'** | 🔥 2.5배 가중치 조건: **{', '.join(priorities) if priorities else '없음'}**"
        )

        with st.spinner("아마존 실시간 데이터 수집 및 AI 맞춤 순위 계산 중..."):
            products = fetch_and_rank_amazon_products(
                cur_category, keyword, user_inputs, priorities
            )

        st.divider()

        if not products:
            st.warning("아마존 추천 상품을 불러오지 못했습니다.")
        else:
            st.subheader(
                f"🎯 [{cur_category}] 고객 가중치 만족도 순 BEST 추천 TOP {len(products)}"
            )

            for idx, item in enumerate(products):
                st.markdown(
                    f"""
                <div class="product-card">
                    <span class="badge-rank">TOP {idx+1}</span> &nbsp; 
                    <span class="badge-score">AI Score: {item['score']}점</span>
                </div>
                """,
                    unsafe_allow_html=True,
                )

                col_img, col_info, col_btn = st.columns([2.0, 3.8, 1.8])

                with col_img:
                    if item["img"]:
                        st.image(item["img"], use_container_width=True)

                with col_info:
                    st.markdown(f"### {item['title']}")
                    st.write(
                        f"**실판매가:** `{item['price_krw']}` ({item['raw_price_usd']}) &nbsp;|&nbsp; **평점:** ⭐ {item['rating']}점 (리뷰 {item['reviews']:,}개)"
                    )

                    match_pct = int(item["match_ratio"] * 100)
                    st.progress(
                        item["match_ratio"],
                        text=f"C1~C8 가중치 반영 일치율: {match_pct}%",
                    )

                    with st.expander("🔍 매칭 사유 및 점수 상세 내역 보기", expanded=True):
                        st.markdown("**[조건 일치 매칭 사유]**")
                        r_col1, r_col2 = st.columns(2)
                        for r_idx, reason in enumerate(item["reasons"]):
                            if r_idx < 4:
                                r_col1.markdown(f"- {reason}")
                            else:
                                r_col2.markdown(f"- {reason}")

                        st.markdown("---")
                        st.markdown("**[점수 상세 산출 내역]**")
                        for k, v in item["breakdown"].items():
                            st.write(f"- {k}: **{v}점**")

                with col_btn:
                    st.metric("AI 맞춤 적합도", f"{item['score']} 점")
                    click_count = st.session_state.click_data.get(item["asin"], 0)
                    st.caption(f"앱 내 관심 등록 수: {click_count}회")

                    st.link_button(
                        "🛍️ 아마존 최저가 확인",
                        item["url"],
                        use_container_width=True,
                    )

                    if st.button(
                        "👍 관심 상품 등록", key=f"btn_fav_{idx}_{item['asin']}"
                    ):
                        record_click(item["asin"])
                        st.toast(f"'{item['title']}' 관심 피드백이 반영되었습니다!")

                st.markdown("<br>", unsafe_allow_html=True)


# ==========================================
# TAB 2: 대화형 AI 패션 스타일리스트 챗봇
# ==========================================
with tab2:
    st.subheader("💬 1:1 대화형 AI 패션 스타일리스트")
    st.caption(
        "TPO, 특수 상황, 디테일한 스타일 요구사항을 자유롭게 입력하시면 실시간 아마존 대화형 추천을 제공합니다."
    )

    # 챗봇 메시지 히스토리 출력
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "items" in msg and msg["items"]:
                st.markdown("---")
                st.markdown("🛍️ **AI 스타일리스트 실시간 탐색 상품:**")
                cols = st.columns(len(msg["items"]))
                for idx, prod in enumerate(msg["items"]):
                    with cols[idx]:
                        if prod["img"]:
                            st.image(prod["img"], use_container_width=True)
                        st.markdown(f"**{prod['title'][:35]}...**")
                        st.write(f"💰 {prod['price']}")
                        st.write(f"⭐ {prod['rating']}점")
                        st.link_button(
                            "구매링크", prod["url"], use_container_width=True
                        )

    # 사용자 프롬프트 입력
    if prompt := st.chat_input("스타일 고민이나 원하시는 옷을 입력하세요..."):
        # 1. 사용자 메시지 기록
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 2. 챗봇 처리 및 실시간 상품 검색
        with st.chat_message("assistant"):
            with st.spinner("AI 스타일리스트가 코디 분석 및 아마존 상품을 찾아보고 있습니다..."):
                advice, items, search_query = generate_chatbot_response(prompt)
                st.markdown(advice)

                if items:
                    st.markdown("---")
                    st.markdown(
                        f"🛍️ **아마존 실시간 매칭 아이템 (검색어: '{search_query}'):**"
                    )
                    cols = st.columns(len(items))
                    for idx, prod in enumerate(items):
                        with cols[idx]:
                            if prod["img"]:
                                st.image(prod["img"], use_container_width=True)
                            st.markdown(f"**{prod['title'][:35]}...**")
                            st.write(f"💰 {prod['price']}")
                            st.write(f"⭐ {prod['rating']}점")
                            st.link_button(
                                "구매링크", prod["url"], use_container_width=True
                            )

            # 3. 어시스턴트 메시지 세션 저장
            st.session_state.messages.append(
                {"role": "assistant", "content": advice, "items": items}
            )