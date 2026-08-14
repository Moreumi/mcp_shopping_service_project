# =========================================================
# Customer Service 데모 데이터
#
# 미니 프로젝트_수정 - Copy와 동일하게 orders/payments/refunds를
# 모듈 레벨 list로 노출한다. 다만 하드코딩된 리터럴 대신, 이 프로젝트
# 전용 DynamoDB 테이블(customer-service-demo-*)에서 불러온다.
# New Thread(메인 쇼핑 어시스턴트)가 쓰는 shopping-orders/shopping-users
# 테이블과는 완전히 분리된 별도 테이블이다.
# =========================================================

import logging

from backend.cs.dynamodb_store import (
    load_orders,
    load_payments,
    load_refunds,
    save_order,
    save_payment,
    save_refund,
)

logger = logging.getLogger(__name__)


def _load_or_empty(loader, label: str) -> list[dict]:
    """Keep the API importable when optional demo AWS data is unavailable."""
    try:
        return loader()
    except Exception as error:
        logger.warning("cs_demo_%s_unavailable: %s", label, type(error).__name__)
        return []


orders = _load_or_empty(load_orders, "orders")
payments = _load_or_empty(load_payments, "payments")
refunds = _load_or_empty(load_refunds, "refunds")


def persist_all() -> None:
    """orchestrator의 Write Action이 in-memory list를 변경한 뒤,
    변경분을 DynamoDB에 그대로 반영한다."""

    for order in orders:
        save_order(order)

    for payment in payments:
        save_payment(payment)

    for refund in refunds:
        save_refund(refund)
