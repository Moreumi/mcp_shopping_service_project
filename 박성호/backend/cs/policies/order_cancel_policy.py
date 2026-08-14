# =========================================================
# 주문 취소 가능 여부 Policy
# =========================================================

ORDER_CANCEL_POLICY_CONTEXT = """
현재 MVP에서 주문 취소 가능 여부는
order_status와 delivery_status를 기준으로 판단한다.

[주문 상태 기준]

- order_canceled:
  이미 정상적으로 취소된 주문이다.
  다시 주문 취소 Action을 실행하지 않는다.

- order_failed:
  정상적으로 완료되지 않은 주문이므로
  주문 취소 Action을 실행하지 않는다.

- order_completed:
  delivery_status를 추가로 확인한다.

[배송 상태 기준]

- preparing_shipment:
  배송준비중 상태이다.
  주문 취소가 가능하다.
  단, 사용자의 최종 승인 없이 주문 취소 Action을 실행하지 않는다.

- in_transit:
  현재 배송 중인 상태이므로 주문 취소가 불가능하다.
  상품을 수령한 후 취소를 원하는 경우
  교환/환불 카테고리로 문의하도록 안내한다.

- delivered:
  배송이 완료된 상태이므로 주문 취소가 불가능하다.
  배송 완료된 주문에 대해 취소를 원하는 경우
  교환/환불 카테고리로 문의하도록 안내한다.

이미 취소된 주문을 사용자가 다시 복구하려는 경우에는
취소된 주문을 order_completed 상태로 되돌리지 않는다.
상품 구매를 원하는 경우 새롭게 주문하도록 안내한다.

현재 구현되지 않은 교환/환불 Flow로 자동 Routing하지 않는다.
"""


def judge_order_cancel(
    order_status: str,
    delivery_status: str,
) -> dict:
    """
    주문 상태와 배송 상태를 기준으로
    주문 취소 가능 여부를 판단한다.

    실제 주문 취소 Action은 수행하지 않는다.
    """

    # 이미 취소된 주문
    if order_status == "order_canceled":
        return {
            "cancel_judgment": "already_canceled",
            "reason": "already_canceled",
        }

    # 정상적으로 완료되지 않은 주문
    if order_status == "order_failed":
        return {
            "cancel_judgment": "not_cancelable",
            "reason": "order_failed",
        }

    # 정의되지 않은 주문 상태
    if order_status != "order_completed":
        return {
            "cancel_judgment": "needs_review",
            "reason": "unknown_order_status",
        }

    # -----------------------------------------------------
    # 여기부터는 order_completed인 주문만 처리
    # -----------------------------------------------------

    # 배송준비중 → 취소 가능
    if delivery_status == "preparing_shipment":
        return {
            "cancel_judgment": "cancelable",
            "reason": None,
        }

    # 배송중 → 취소 불가
    if delivery_status == "in_transit":
        return {
            "cancel_judgment": "not_cancelable",
            "reason": "in_transit",
        }

    # 배송완료 → 취소 불가
    if delivery_status == "delivered":
        return {
            "cancel_judgment": "not_cancelable",
            "reason": "delivered",
        }

    # 정의되지 않은 배송 상태
    return {
        "cancel_judgment": "needs_review",
        "reason": "unknown_delivery_status",
    }
