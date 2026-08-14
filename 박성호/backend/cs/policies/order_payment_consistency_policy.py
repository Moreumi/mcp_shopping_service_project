# =========================================================
# 주문-결제 상태 일관성 Policy
# =========================================================

ORDER_PAYMENT_CONSISTENCY_POLICY_CONTEXT = """
주문 상태와 결제 상태는 각각 별도로 관리하며,
두 상태가 서로 일관된지 함께 확인한다.

현재 MVP의 판단 기준은 다음과 같다.

- order_completed + payment_completed
  → 주문과 결제가 모두 정상 완료된 상태

- order_completed + payment_failed
  → 주문과 결제 상태가 일치하지 않아 추가 확인이 필요한 상태

- order_completed + payment_canceled
  → 주문과 결제 상태가 일치하지 않아 추가 확인이 필요한 상태

- order_canceled + payment_completed
  → 주문은 취소되었지만 결제가 완료 상태로 남아 있어 추가 확인이 필요한 상태

- order_canceled + payment_failed
  → 주문과 결제가 정상 완료되지 않은 상태

- order_canceled + payment_canceled
  → 주문과 결제가 모두 취소 상태

- order_failed + payment_completed
  → 주문은 실패했지만 결제가 완료 상태로 남아 있어 추가 확인이 필요한 상태

- order_failed + payment_failed
  → 주문과 결제가 모두 정상 완료되지 않은 상태

- order_failed + payment_canceled
  → 주문이 정상 완료되지 않았고 결제는 취소 상태

상태가 서로 모순되는 경우 어느 한쪽을 임의로 정상 상태라고 판단하지 않는다.
불일치의 원인도 현재 데이터만으로 추측하지 않는다.

주문 상태와 결제 상태가 일치하지 않아
consistency_judgment가 needs_review인 경우,
고객에게 추가 확인이 필요한 상태임을 안내하고
고객센터 또는 상담원을 통한 확인을 안내할 수 있다.
"""


def judge_order_payment_consistency(
    order_status: str,
    payment_status: str,
) -> str:

    consistency_map = {
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

    return consistency_map.get(
        (order_status, payment_status),
        "needs_review",
    )
