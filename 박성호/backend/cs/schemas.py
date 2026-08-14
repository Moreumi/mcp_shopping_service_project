from typing import Literal
from pydantic import BaseModel, Field


class UserRequest(BaseModel):
    intent: Literal[
        "cs",
        "recommendation",
        "other"
    ] = Field(
        description="사용자 질문의 최상위 유형"
    )

    cs_category: Literal[
        "member_account",
        "order_payment",
        "exchange_refund",
        "delivery",
        "product_info"
    ] | None = Field(
        default=None,
        description="intent가 cs인 경우의 cs 카테고리"
    )

    sub_intent: Literal[
        "order_confirmation",
        "payment_confirmation",
        "payment_method_change",
        "delivery_address_change",
        "order_cancel",
        "order_change",
        "unknown"
    ] | None = Field(
        default=None,
        description="세부 처리 목적. 현재는 주문/결제 영역을 중심으로 정의"
    )

    order_id: int | None = Field(
        default=None,
        description="사용자 질문에 주문번호가 명시된 경우 해당 주문번호"
    )
