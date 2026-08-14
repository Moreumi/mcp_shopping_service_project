# =========================================================
# 결제 완료 확인 Policy
# =========================================================

PAYMENT_COMPLETION_POLICY_CONTEXT = """
현재 MVP에서 결제 완료 여부는 payment_status를 기준으로 판단한다.

- payment_completed: 결제가 정상적으로 완료된 상태
- payment_failed: 결제가 정상적으로 완료되지 않은 상태
- payment_canceled: 현재 결제가 취소된 상태
- 그 외 상태: 자동으로 완료 여부를 판단하지 않고 추가 확인이 필요한 상태

결제 취소 상태가 과거에 정상 승인된 결제였는지,
환불까지 완료되었는지는 현재 데이터만으로 추론하지 않는다.
"""


def judge_payment_completion(payment_status: str) -> str:
    if payment_status == "payment_completed":
        return "completed"

    if payment_status == "payment_failed":
        return "failed"

    if payment_status == "payment_canceled":
        return "canceled"

    return "needs_review"
