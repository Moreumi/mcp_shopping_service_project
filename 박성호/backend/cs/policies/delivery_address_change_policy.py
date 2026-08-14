# =========================================================
# 배송지 변경 가능 여부 Policy
# =========================================================

DELIVERY_ADDRESS_CHANGE_POLICY_CONTEXT = """
현재 구현에서는 주문 후 배송지 변경 가능 여부를
order_status와 delivery_status를 기준으로 판단한다.

[주문 상태 기준]

- order_canceled:
  이미 취소된 주문이므로 배송지를 변경할 수 없다.

- order_failed:
  정상적으로 완료되지 않은 주문이므로 배송지를 변경할 수 없다.

- order_completed:
  delivery_status를 추가로 확인한다.

[배송 상태 기준]

- preparing_shipment:
  배송준비중 상태이다.
  배송지 변경이 가능하다.
  단, 사용자의 최종 승인 없이 배송지 변경 Action을 실행하지 않는다.

- in_transit:
  이미 배송이 시작된 상태이므로 배송지를 변경할 수 없다.

- delivered:
  배송이 완료된 상태이므로 배송지를 변경할 수 없다.

배송지 변경 가능 여부를 판단하는 것과
실제 배송지 변경 Action을 실행하는 것은 분리한다.

배송지 변경이 가능한 경우에도
변경할 주소를 확인하고 사용자의 최종 승인을 받은 이후에만
실제 배송지 변경 Action을 실행한다.
"""


def judge_delivery_address_change(
    order_status: str,
    delivery_status: str,
) -> dict:
    """
    주문 상태와 배송 상태를 기준으로
    배송지 변경 가능 여부를 판단한다.

    실제 배송지 변경 Action은 수행하지 않는다.
    """

    # 이미 취소된 주문
    if order_status == "order_canceled":
        return {
            "address_change_judgment": "not_changeable",
            "reason": "order_canceled",
        }

    # 정상적으로 완료되지 않은 주문
    if order_status == "order_failed":
        return {
            "address_change_judgment": "not_changeable",
            "reason": "order_failed",
        }

    # 정의되지 않은 주문 상태
    if order_status != "order_completed":
        return {
            "address_change_judgment": "needs_review",
            "reason": "unknown_order_status",
        }

    # -----------------------------------------------------
    # 여기부터는 order_completed인 주문만 처리
    # -----------------------------------------------------

    # 배송준비중 → 배송지 변경 가능
    if delivery_status == "preparing_shipment":
        return {
            "address_change_judgment": "changeable",
            "reason": None,
        }

    # 배송중 → 배송지 변경 불가
    if delivery_status == "in_transit":
        return {
            "address_change_judgment": "not_changeable",
            "reason": "in_transit",
        }

    # 배송완료 → 배송지 변경 불가
    if delivery_status == "delivered":
        return {
            "address_change_judgment": "not_changeable",
            "reason": "delivered",
        }

    # 정의되지 않은 배송 상태
    return {
        "address_change_judgment": "needs_review",
        "reason": "unknown_delivery_status",
    }
