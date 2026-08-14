import re


# =========================================================
# State 초기값
# =========================================================

state = {
    "pending_action": None,
    "candidate_orders": [],
    "selected_order_id": None,
    "last_order_id": None,
    "recent_candidate_orders": [],
    "recent_list_intent": None,
    "history": [],
    "pending_data":{},
}


# =========================================================
# State 초기화
# =========================================================

def reset_state(state: dict) -> None:
    state["pending_action"] = None
    state["candidate_orders"] = []
    state["selected_order_id"] = None
    # Keep last_order_id across workflow cleanup for contextual follow-ups.
    # Also keep the most recently displayed order list so ordinal follow-ups
    # such as "첫번째" remain meaningful after one selection is completed.
    state["pending_data"] = {}


# =========================================================
# 사용자가 선택한 주문번호 추출
# =========================================================

def extract_order_id(user_input: str) -> int | None:

    match = re.search(r"\d+", user_input)

    if match:
        return int(match.group())

    return None


# =========================================================
# 목록에서 서수/위치 표현으로 선택한 항목 추출
# =========================================================

_ORDINAL_WORDS = {
    "첫번째": 0, "첫 번째": 0, "첫째": 0,
    "두번째": 1, "두 번째": 1, "둘째": 1,
    "세번째": 2, "세 번째": 2, "셋째": 2,
    "네번째": 3, "네 번째": 3, "넷째": 3,
    "다섯번째": 4, "다섯 번째": 4, "다섯째": 4,
}


def extract_ordinal_index(user_input: str) -> int | None:
    """
    안내된 목록에서 실제 주문번호 대신 "첫번째", "2번째", "마지막"처럼
    위치로 고르는 경우를 위한 0-based 인덱스를 추출한다.

    -1은 "마지막"을 의미한다.

    실제 주문번호(예: 20001)와 헷갈리지 않도록, "번째"/"번"이 뒤따르는
    숫자만 서수로 인정한다.
    """

    text = user_input.strip()

    if any(term in text for term in ("마지막", "맨 뒤", "맨뒤", "맨 마지막")):
        return -1

    match = re.search(r"(\d+)\s*번째?", text)
    if match:
        return int(match.group(1)) - 1

    for term, index in _ORDINAL_WORDS.items():
        if term in text:
            return index

    return None


# =========================================================
# 주문 취소 최종 승인 여부 확인
# =========================================================

def extract_confirmation(user_input: str) -> bool | None:
    """
    사용자의 주문 취소 최종 승인 여부를 확인한다.

    True:
        명확하게 승인한 경우

    False:
        명확하게 거절한 경우

    None:
        승인/거절 여부가 명확하지 않은 경우

    LLM의 추측으로 승인 여부를 판단하지 않는다.
    """

    normalized_input = user_input.strip().lower()

    approve_inputs = {
        "예",
        "네",
        "응",
        "yes",
        "y",
    }

    reject_inputs = {
        "아니오",
        "아니요",
        "아니",
        "no",
        "n",
    }

    if normalized_input in approve_inputs:
        return True

    if normalized_input in reject_inputs:
        return False

    return None

# =========================================================
# 환불계좌 정보 추출
# =========================================================

def extract_refund_account(user_input: str) -> dict | None:
    """
    환불계좌 정보를 다음 형식으로 입력받는다.

    은행명 / 계좌번호 / 예금주

    예:
    국민은행 / 1234567890 / 홍길동
    """

    parts = [
        part.strip()
        for part in user_input.split("/")
    ]

    # 정확히 세 항목이 필요
    if len(parts) != 3:
        return None

    bank_name, account_number, account_holder = parts

    # 빈 값이 있는 경우
    if not bank_name or not account_number or not account_holder:
        return None

    # 계좌번호는 숫자와 '-'만 허용
    normalized_account_number = account_number.replace("-", "")

    if not normalized_account_number.isdigit():
        return None

    return {
        "bank_name": bank_name,
        "account_number": account_number,
        "account_holder": account_holder,
    }

# =========================================================
# 배송지 정보 추출
# =========================================================

def extract_delivery_address(user_input: str) -> str | None:
    """
    배송지 변경 과정에서 사용자가 입력한 새 주소를 추출한다.

    현재 MVP에서는 주소 자체의 유효성을 외부 주소 API로 검증하지 않고,
    공백이 아닌 문자열인지 여부만 확인한다.
    """

    address = user_input.strip()

    if not address:
        return None

    # Do not consume a clear customer-service question as an address merely
    # because the previous turn happened to be waiting for address input.
    normalized = "".join(address.lower().split())
    non_address_terms = (
        "결제수단", "결제내역", "주문취소", "주문확인", "환불",
        "알려줘", "확인해줘", "조회해줘",
    )
    if any(term in normalized for term in non_address_terms):
        return None
    account_parts = [part.strip() for part in address.split("/")]
    if (
        len(account_parts) == 3
        and account_parts[1].replace("-", "").isdigit()
    ):
        return None

    return address
