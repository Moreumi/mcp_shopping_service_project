"""Local Ollama/Qwen adapter for the customer-service workflow."""

from __future__ import annotations

import os

import ollama
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field

from backend.cs.schemas import UserRequest


load_dotenv()
MODEL = os.getenv("OLLAMA_QUERY_MODEL", "qwen3:4b")
KEEP_ALIVE = os.getenv("OLLAMA_QUERY_KEEP_ALIVE", "2h")
_client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))


class CustomerAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=1200)

CLASSIFICATION_SYSTEM = """당신은 쇼핑 고객센터의 질의 이해기입니다.
반드시 제공된 JSON schema만 출력하세요.

판단 순서:
1. 현재 문장에서 고객이 지금 원하는 행동을 찾습니다.
2. 생략된 대상은 대화 맥락의 활성 주문과 최근 주문 목록에서 찾습니다.
3. 현재 문장의 명시적 주문번호와 새 의도를 과거 맥락보다 우선합니다.
4. '그거', '그 주문', '아까 주문', '첫번째/두번째/마지막'은 대화 맥락을
   참고하되 근거가 없으면 추측하지 않습니다.
5. 단순한 예/아니오, 주소, 계좌정보는 진행 중 작업의 입력일 수 있으므로
   새 의도로 과잉 해석하지 않습니다.

intent:
- cs: 고객센터, 주문, 결제, 배송, 교환, 환불, 상품정보 문의
- recommendation: 조건이나 상황에 맞는 상품 추천
- other: 인사 또는 지원 범위 밖 요청

cs_category: member_account, order_payment, exchange_refund, delivery, product_info
지원하는 order_payment sub_intent:
- order_confirmation: 주문 내역/상태 확인
- payment_confirmation: 결제 내역/상태 확인
- payment_method_change: 결제수단 변경
- delivery_address_change: 배송지/주소 변경
- order_cancel: 주문 취소
- order_change: 주문 내용 변경
- unknown: 주문·결제 문의지만 목적이 불명확함

order_id는 현재 문장에 명시되어 있거나 대화 맥락의 활성 주문이 명확할 때만 설정합니다.
"""


def _content(response) -> str:
    message = response["message"] if isinstance(response, dict) else response.message
    return message["content"] if isinstance(message, dict) else message.content


def _chat_messages(prompt_value) -> AIMessage:
    messages = prompt_value.to_messages() if hasattr(prompt_value, "to_messages") else prompt_value
    payload = []
    for message in messages:
        role = "system" if message.type == "system" else "user" if message.type == "human" else "assistant"
        payload.append({"role": role, "content": str(message.content)})
    response = _client.chat(
        model=MODEL,
        messages=payload,
        options={"temperature": 0, "num_predict": 500},
        think=False,
        keep_alive=KEEP_ALIVE,
    )
    return AIMessage(content=_content(response))


def _classify(values: dict) -> UserRequest:
    user_input = str(values.get("user_input") or "")
    conversation_context = str(values.get("conversation_context") or "없음")
    response = _client.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": CLASSIFICATION_SYSTEM},
            {"role": "user", "content": (
                f"[대화 맥락]\n{conversation_context}\n\n"
                f"[현재 고객 메시지]\n{user_input}"
            )},
        ],
        format=UserRequest.model_json_schema(),
        options={"temperature": 0, "num_predict": 120},
        think=False,
        keep_alive=KEEP_ALIVE,
    )
    return UserRequest.model_validate_json(_content(response))


def generate_customer_answer(messages) -> str:
    """Return only a schema-validated Korean customer-facing answer."""
    payload = []
    for message in messages:
        role = "system" if message.type == "system" else "user" if message.type == "human" else "assistant"
        payload.append({"role": role, "content": str(message.content)})
    payload.insert(0, {"role": "system", "content": (
        "최종 고객 안내문만 한국어로 작성하세요. 사고 과정, 분석, 계획, 영어 설명을 절대 출력하지 마세요. "
        "제공된 사실만 사용하고 핵심 결론부터 간결하게 답하세요."
    )})
    response = _client.chat(
        model=MODEL,
        messages=payload,
        format=CustomerAnswer.model_json_schema(),
        options={"temperature": 0, "num_predict": 350},
        think=False,
        keep_alive=KEEP_ALIVE,
    )
    answer = CustomerAnswer.model_validate_json(_content(response)).answer.strip()
    if not any("가" <= char <= "힣" for char in answer):
        raise ValueError("Customer answer did not contain Korean text")
    return answer


# Preserve the existing LangChain pipe/invoke interfaces used by the CS modules.
llm = RunnableLambda(_chat_messages)
classification_chain = RunnableLambda(_classify)
