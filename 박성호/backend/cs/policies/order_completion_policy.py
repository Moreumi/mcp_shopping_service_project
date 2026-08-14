# =========================================================
# 주문 완료 확인 Policy
# =========================================================

ORDER_COMPLETION_POLICY_CONTEXT = """
현재 MVP에서 주문 완료 여부는 order_status를 기준으로 판단한다.

- order_completed: 주문이 정상적으로 접수된 상태
- order_canceled: 현재 주문이 취소된 상태
- order_failed: 주문이 정상적으로 완료되지 않은 상태
- 그 외 상태: 자동으로 완료 여부를 판단하지 않고 추가 확인이 필요한 상태

취소된 주문이 과거에 정상 완료되었는지는 현재 데이터만으로 추론하지 않는다.
"""


def judge_order_completion(order_status: str) -> str:
    if order_status == "order_completed":
        return "completed"

    if order_status == "order_canceled":
        return "canceled"

    if order_status == "order_failed":
        return "failed"

    return "needs_review"
