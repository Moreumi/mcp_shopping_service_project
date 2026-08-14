# =========================================================
# 결제수단 변경 Policy
# =========================================================

PAYMENT_METHOD_CHANGE_POLICY_CONTEXT = """
결제 완료된 주문의 결제수단은 직접 변경할 수 없다.

다른 결제수단을 이용하려는 경우
기존 주문을 취소한 후 원하는 결제수단으로 다시 주문해야 한다.

결제수단 변경 문의 자체에서는
주문 취소 Action을 자동으로 실행하지 않는다.

실제 주문 취소를 원하는 경우에는
사용자가 별도로 주문 취소를 요청해야 한다.
"""


def judge_payment_method_change() -> dict:
    """
    결제 완료 후 결제수단 변경 요청에 대한
    쇼핑몰 Business Rule을 반환한다.

    이 기능에서는 주문 상태나 배송 상태를 조회하지 않는다.
    실제 데이터를 변경하는 Write Action도 실행하지 않는다.
    """

    return {
        "payment_method_change_judgment": "not_changeable",
        "recommended_action": "cancel_and_reorder",
    }
