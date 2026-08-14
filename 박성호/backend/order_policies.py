"""Deterministic order/payment completion judgments.

Ported from the mini-project's order_completion_policy.py,
payment_completion_policy.py and order_payment_consistency_policy.py. The
judgment functions are pure and storage-agnostic — they only need the
order_status/payment_status enum values already used there. Field names on
the DynamoDB order item follow shopping-assistant conventions (see
backend/agent_graph.py's order confirmation handling).
"""

from __future__ import annotations


ORDER_COMPLETION_POLICY_CONTEXT = """
주문 완료 여부는 order_status를 기준으로 판단한다.

- order_completed: 주문이 정상적으로 접수된 상태
- order_canceled: 주문이 취소된 상태
- order_failed: 주문이 정상적으로 완료되지 않은 상태
- 그 외 상태: 자동으로 완료 여부를 판단하지 않고 추가 확인이 필요한 상태
"""

PAYMENT_COMPLETION_POLICY_CONTEXT = """
결제 완료 여부는 payment_status를 기준으로 판단한다.

- payment_completed: 결제가 정상적으로 완료된 상태
- payment_failed: 결제가 정상적으로 완료되지 않은 상태
- payment_canceled: 결제가 취소된 상태
- 그 외 상태: 자동으로 완료 여부를 판단하지 않고 추가 확인이 필요한 상태
"""

ORDER_PAYMENT_CONSISTENCY_POLICY_CONTEXT = """
주문 상태와 결제 상태가 서로 모순되는 경우(예: 주문은 취소됐는데 결제는 완료 상태) 어느 한쪽을
임의로 정상 상태라고 판단하지 않는다. 이 경우 고객에게 추가 확인이 필요함을 안내한다.
"""

_CONSISTENCY_MAP = {
    ("order_completed", "payment_completed"): "consistent_completed",
    ("order_completed", "payment_failed"): "needs_review",
    ("order_completed", "payment_canceled"): "needs_review",
    ("order_canceled", "payment_completed"): "needs_review",
    ("order_canceled", "payment_failed"): "consistent_not_completed",
    ("order_canceled", "payment_canceled"): "consistent_canceled",
    ("order_failed", "payment_completed"): "needs_review",
    ("order_failed", "payment_failed"): "consistent_failed",
    ("order_failed", "payment_canceled"): "consistent_not_completed",
}


def judge_order_completion(order_status: str | None) -> str:
    if order_status == "order_completed":
        return "completed"
    if order_status == "order_canceled":
        return "canceled"
    if order_status == "order_failed":
        return "failed"
    return "needs_review"


def judge_payment_completion(payment_status: str | None) -> str:
    if payment_status == "payment_completed":
        return "completed"
    if payment_status == "payment_failed":
        return "failed"
    if payment_status == "payment_canceled":
        return "canceled"
    return "needs_review"


def judge_order_payment_consistency(order_status: str | None, payment_status: str | None) -> str:
    return _CONSISTENCY_MAP.get((order_status, payment_status), "needs_review")
