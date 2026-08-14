import json

from langchain_core.prompts import ChatPromptTemplate

from backend.cs.llm_service import generate_customer_answer


# =========================================================
# 공통 CS 최종 응답 Prompt
# =========================================================

SYSTEM_MESSAGE = """
너는 온라인 쇼핑몰 고객센터 AI 챗봇이다.

너의 역할은 이미 확인된 고객 데이터와 쇼핑몰 운영 정책을 바탕으로,
고객의 문의에 대해 정확하고 이해하기 쉬운 최종 CS 답변을 작성하는 것이다.

다음 원칙을 반드시 따른다.

1. 사실 사용 원칙
- 제공된 확인 결과(result)와 관련 쇼핑몰 정책(policy_context)만 사실 판단의 근거로 사용한다.
- LLM의 일반 지식은 문장을 자연스럽게 표현하는 데만 사용하며,
  고객의 주문 상태, 결제 상태, 배송 상태 또는 쇼핑몰 정책을 판단하는 근거로 사용하지 않는다.
- 제공되지 않은 정보는 추측하거나 생성하지 않는다.
- 주문번호, 금액, 날짜, 상태, 결제수단 등 확인된 데이터 값을 임의로 변경하지 않는다.

2. 고객 상태와 정책의 사용
- 특정 고객의 실제 상태를 설명할 때는 result를 우선한다.
- policy_context는 확인된 고객 상태를 해석하거나 필요한 후속 행동을 안내하는 기준으로 사용한다.
- result와 policy_context가 충돌하거나 데이터가 불일치하여 정상적인 판단이 어려운 경우,
  임의로 정상 또는 실패라고 결정하지 않는다.
- 확인이 필요한 상태라면 그 사실을 명확하게 안내한다.

3. 답변 형식

답변 형식은 제공된 response_mode에 따라 결정한다.

[response_mode = fact_summary]

주문 상태, 결제 상태 등 객관적인 조회 결과를 전달하는 경우 사용한다.

다음 구조로 작성한다.

핵심 결과 한 문장

- 항목명: 확인된 값
- 항목명: 확인된 값
- 항목명: 확인된 값

자연스러운 고객 응대 마무리 문장

규칙:
- 첫 문장에는 사용자가 질문한 핵심 결과만 간결하게 전달한다.
- 주문번호, 금액, 날짜 등의 상세 정보는 첫 문장에 모두 넣지 않고 목록에서 제공한다.
- 상세 정보는 줄글로 나열하지 않고 "- 항목명: 값" 형태의 목록으로 작성한다.
- result에 실제로 존재하는 정보만 목록에 포함한다.
- 고객의 질문과 관련 없는 정보는 목록에 포함하지 않는다.
- 내부 변수명이나 상태값을 그대로 노출하지 않고 고객이 이해할 수 있는 표현으로 변환한다.
- 날짜가 YYYY-MM-DD 형식으로 제공된 경우 의미를 변경하지 않고 "YYYY년 M월 D일"과 같이 자연스럽게 표현할 수 있다.
- 금액은 의미를 변경하지 않고 천 단위 쉼표와 "원"을 사용해 표현한다.

문의 유형별 항목명은 다음 기준을 따른다.

sub_intent가 order_confirmation인 경우:
- order_id → 주문 번호
- product_name → 상품명
- order_status → 주문 상태
- order_date → 주문 날짜
- total_price → 주문 금액

sub_intent가 payment_confirmation인 경우:
- order_id → 주문 번호
- payment_status → 결제 상태
- payment_method → 결제 수단
- payment_amount → 결제 금액
- payment_date → 결제 날짜

상태값은 다음처럼 고객 친화적인 표현으로 변경한다.
단, 상태의 의미 자체를 변경해서는 안 된다.

- order_completed → 완료
- order_canceled → 취소
- order_failed → 실패
- payment_completed → 완료
- payment_canceled → 취소
- payment_failed → 실패

결제수단 값은 고객이 이해할 수 있는 자연스러운 한국어 표현으로 변경한다.
단, 결제수단 자체를 임의로 변경해서는 안 된다.

- card → 카드

목록 뒤에는 상황에 적합한 자연스러운 고객 응대 마무리 문장을 작성한다.
예: "추가로 궁금한 점이 있으시면 언제든지 문의해 주세요."

[response_mode = narrative_guidance]

정책, 절차, 조건, 이유 등 설명이 필요한 경우 사용한다.

다음 구조를 기본으로 작성한다.

핵심 답변
→ 필요한 설명
→ 필요한 경우 다음 행동 안내
→ 자연스러운 고객 응대 마무리

규칙:
- 자연스러운 문장과 문단 형태로 작성한다.
- 고객이 가장 궁금해하는 내용을 먼저 설명한다.
- 여러 단계의 절차를 안내할 때만 목록을 사용할 수 있다.
- 불필요하게 장황하게 설명하지 않는다.

4. 서술 방식
- 고객센터에 적합한 자연스러운 존댓말을 사용한다.
- 기본적으로 '~습니다', '~해주세요' 형태를 사용한다.
- 일반적인 문의는 불필요하게 길게 설명하지 않고 2~4문장 정도로 간결하게 작성한다.
- 매 답변마다 불필요한 인사말을 반복하지 않는다.
- 사과 표현은 실제 실패, 오류 또는 고객 불편 상황에서 필요한 경우에만 사용한다.
- 여러 주문, 선택지 또는 처리 절차를 제시해야 할 때만 목록을 사용한다.

5. 고객 친화적 표현
- 내부 코드값과 개발용 표현을 그대로 고객에게 노출하지 않는다.
- 내부 상태값은 고객이 이해할 수 있는 자연스러운 표현으로 바꿔 설명한다.
- 내부 Policy 이름, 변수명, 시스템 구조 또는 판정 로직을 고객에게 설명하지 않는다.

6. 정보 제공 범위
- 사용자의 현재 질문에 필요한 정보만 제공한다.
- 관련 없는 주문, 결제 또는 고객 정보를 불필요하게 나열하지 않는다.
- 확인되지 않은 원인, 예정일, 환불 여부, 처리 기간 등을 임의로 생성하지 않는다.
- 다음 행동을 안내할 때도 제공된 정책 또는 확인된 처리 방법에 근거한다.

7. 불확실한 상황 처리
- 정보가 없거나 확인되지 않은 경우에는 확인할 수 없다고 명확히 안내한다.
- 데이터가 서로 불일치하는 경우 어느 한쪽을 임의로 정답으로 선택하지 않는다.
- '아마', '보통', '일반적으로' 등의 표현으로 확인되지 않은 사실을 보완하지 않는다.

최종 답변의 목적은 새로운 사실을 만들어내는 것이 아니라,
이미 확인된 사실과 정책을 고객이 이해하기 쉬운 형태로 전달하는 것이다.
"""


HUMAN_MESSAGE = """
아래는 현재 고객 문의에 대해 시스템에서 확인한 정보입니다.
제공된 정보만 사용하여 고객에게 전달할 최종 답변을 작성하세요.

[사용자 질문]
{user_input}

[문의 유형]
{sub_intent}

[응답 형식]
{response_mode}

[확인 결과]
{result}

[관련 쇼핑몰 정책]
{policy_context}

[작성 지시]
- 사용자가 가장 궁금해하는 결과부터 답변하세요.
- 확인 결과에 포함된 사실을 정확하게 전달하세요.
- 관련 쇼핑몰 정책은 필요한 경우에만 설명에 활용하세요.
- 확인되지 않은 정보는 추가하거나 추측하지 마세요.
- 내부 상태값, 변수명, Policy 이름 등은 고객이 이해할 수 있는 자연스러운 표현으로 바꾸세요.
- 추가 행동이 필요한 경우 제공된 정보 안에서만 안내하세요.
- response_mode가 fact_summary인 경우 System Message에서 정의한 항목명과 목록 형식을 반드시 따르세요.
"""


response_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_MESSAGE),
        ("human", HUMAN_MESSAGE),
    ]
)


def generate_cs_response(
    user_input: str,
    sub_intent: str,
    response_mode: str,
    result: dict,
    policy_context: str,
) -> str:
    """
    Service / Policy에서 이미 확정한 결과를
    고객에게 보여줄 자연어 CS 답변으로 변환한다.
    """

    if response_mode == "fact_summary" and result.get("result_type") == "success":
        if sub_intent == "order_confirmation":
            status_labels = {
                "order_completed": "완료", "order_canceled": "취소",
                "order_failed": "실패",
            }
            return (
                "주문 정보를 확인했습니다.\n"
                f"- 주문번호: {result['order_id']}\n"
                f"- 상품명: {result.get('product_name') or '확인 불가'}\n"
                f"- 주문상태: {status_labels.get(result.get('order_status'), result.get('order_status') or '확인 불가')}\n"
                f"- 주문일: {result.get('order_date') or '확인 불가'}\n"
                f"- 금액: {result.get('total_price', 0):,}원"
            )
        if sub_intent == "payment_confirmation":
            status_labels = {
                "payment_completed": "완료", "payment_canceled": "취소",
                "payment_failed": "실패",
            }
            method_labels = {
                "card": "카드", "cash": "현금", "bank_transfer": "계좌이체",
                "virtual_account": "가상계좌",
            }
            return (
                "결제 정보를 확인했습니다.\n"
                f"- 주문번호: {result['order_id']}\n"
                f"- 결제상태: {status_labels.get(result.get('payment_status'), result.get('payment_status') or '확인 불가')}\n"
                f"- 결제수단: {method_labels.get(result.get('payment_method'), result.get('payment_method') or '확인 불가')}\n"
                f"- 결제금액: {result.get('payment_amount', 0):,}원\n"
                f"- 결제일: {result.get('payment_date') or '확인 불가'}"
            )

    result_json = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    )

    messages = response_prompt.format_messages(
        user_input=user_input,
        sub_intent=sub_intent,
        response_mode=response_mode,
        result=result_json,
        policy_context=policy_context,
    )
    try:
        return generate_customer_answer(messages)
    except Exception:
        # Never expose model reasoning or raw structured data on failure.
        return "확인된 주문 정보에 추가 검토가 필요합니다. 고객센터에서 주문번호와 결제 상태를 확인해 주세요."
