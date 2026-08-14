from backend.cs.policies.order_completion_policy import judge_order_completion
from backend.cs.policies.payment_completion_policy import judge_payment_completion
from backend.cs.policies.order_cancel_policy import judge_order_cancel

from backend.cs.policies.order_payment_consistency_policy import (
    judge_order_payment_consistency,
)

from backend.cs.policies.delivery_address_change_policy import (
    judge_delivery_address_change,
)


def _recent_order_choices(
    orders: list[dict], limit: int = 3, payments: list[dict] | None = None
) -> list[dict]:
    """Compact, newest-first order choices shared by all CS selection flows."""
    recent = sorted(orders, key=lambda order: order.get("order_date", ""), reverse=True)[:limit]
    payment_by_order = {payment["order_id"]: payment for payment in (payments or [])}
    return [
        {
            "order_id": order["order_id"],
            "product_name": order.get("product_name") or "상품명 확인 불가",
            "order_date": order["order_date"],
            "total_price": order["total_price"],
            "payment_method": payment_by_order.get(order["order_id"], {}).get("payment_method"),
            **({"delivery_address": order["delivery_address"]} if order.get("delivery_address") else {}),
        }
        for order in recent
    ]

# =========================================================
# 주문 완료 상태 확인
# =========================================================

def check_order_completion(
    orders: list[dict],
    customer_id: int,
    order_id: int | None = None
) -> dict:

    # 해당 고객의 주문만 조회
    customer_orders = [
        order
        for order in orders
        if order["customer_id"] == customer_id
    ]

    # 해당 고객의 주문이 없는 경우
    if not customer_orders:
        return {
            "result_type": "not_found"
        }

    # 주문번호가 제공된 경우
    if order_id is not None:

        matched_orders = [
            order
            for order in customer_orders
            if order["order_id"] == order_id
        ]

        if not matched_orders:
            return {
                "result_type": "not_found"
            }

        order = matched_orders[0]

        return {
            "result_type": "success",
            "judgment": judge_order_completion(order["order_status"]),
            "order_id": order["order_id"],
            "product_name": order.get("product_name"),
            "order_status": order["order_status"],
            "order_date": order["order_date"],
            "total_price": order["total_price"]
        }

    # 주문번호가 없고 해당 고객 주문이 한 건인 경우
    if len(customer_orders) == 1:

        order = customer_orders[0]

        return {
            "result_type": "success",
            "judgment": judge_order_completion(order["order_status"]),
            "order_id": order["order_id"],
            "product_name": order.get("product_name"),
            "order_status": order["order_status"],
            "order_date": order["order_date"],
            "total_price": order["total_price"]
        }

    # 주문번호가 없고 해당 고객 주문이 여러 건인 경우
    # 현재 시각 기준 최근 3건만 선택지로 제공한다.
    return {
        "result_type": "need_order_selection",
        "candidate_orders": _recent_order_choices(customer_orders),
    }


# =========================================================
# 주문 취소 가능 여부 확인
# =========================================================

def check_order_cancel_eligibility(
    orders: list[dict],
    customer_id: int,
    order_id: int | None = None,
    payments: list[dict] | None = None,
) -> dict:
    """
    고객의 주문을 조회한 뒤
    Order Cancel Policy를 사용하여 주문 취소 가능 여부를 판단한다.

    실제 주문 취소 Action은 수행하지 않는다.
    """

    # -----------------------------------------------------
    # 1. 해당 고객의 주문만 조회

    customer_orders = [
        order
        for order in orders
        if order["customer_id"] == customer_id
    ]

    # 고객의 주문이 없는 경우
    if not customer_orders:
        return {
            "result_type": "not_found",
        }

    # -----------------------------------------------------
    # 2. 사용자가 주문번호를 직접 입력한 경우

    if order_id is not None:
        selected_order = next(
            (
                order
                for order in customer_orders
                if order["order_id"] == order_id
            ),
            None,
        )

        # 해당 고객의 주문이 아닌 경우
        if selected_order is None:
            return {
                "result_type": "not_found",
            }

    # -----------------------------------------------------
    # 3. 주문번호가 없는 경우

    else:
        # 주문이 여러 건이면 사용자가 선택해야 함
        if len(customer_orders) > 1:
            return {
                "result_type": "need_order_selection",
                "candidate_orders": _recent_order_choices(customer_orders, payments=payments),
            }

        # 주문이 한 건이면 자동 선택
        selected_order = customer_orders[0]

    # -----------------------------------------------------
    # 4. 주문 취소 가능 여부 Policy 판단

    cancel_result = judge_order_cancel(
        order_status=selected_order["order_status"],
        delivery_status=selected_order["delivery_status"],
    )

    # -----------------------------------------------------
    # 5. 조회 결과 + Policy 결과 반환

    return {
        "result_type": "success",
        "order_id": selected_order["order_id"],
        "product_name": selected_order.get("product_name") or "상품명 확인 불가",
        "order_status": selected_order["order_status"],
        "delivery_status": selected_order["delivery_status"],
        "order_date": selected_order["order_date"],
        "total_price": selected_order["total_price"],
        "cancel_judgment": cancel_result["cancel_judgment"],
        "reason": cancel_result["reason"],
    }


# =========================================================
# 배송지 변경 가능 여부 확인
# =========================================================

def check_delivery_address_change_eligibility(
    orders: list[dict],
    customer_id: int,
    order_id: int | None = None,
) -> dict:
    """
    고객의 주문을 조회한 뒤
    Delivery Address Change Policy를 사용하여
    배송지 변경 가능 여부를 판단한다.

    실제 배송지 변경 Action은 수행하지 않는다.
    """

    # -----------------------------------------------------
    # 1. 해당 고객의 주문만 조회
    # -----------------------------------------------------

    customer_orders = [
        order
        for order in orders
        if order["customer_id"] == customer_id
    ]

    if not customer_orders:
        return {
            "result_type": "not_found",
        }

    # -----------------------------------------------------
    # 2. 주문번호가 직접 제공된 경우
    # -----------------------------------------------------

    if order_id is not None:
        selected_order = next(
            (
                order
                for order in customer_orders
                if order["order_id"] == order_id
            ),
            None,
        )

        if selected_order is None:
            return {
                "result_type": "not_found",
            }

    # -----------------------------------------------------
    # 3. 주문번호가 없는 경우
    # -----------------------------------------------------

    else:
        # 여러 주문이 있으면 사용자가 선택해야 함
        if len(customer_orders) > 1:
            return {
                "result_type": "need_order_selection",
                "candidate_orders": _recent_order_choices(customer_orders),
            }

        # 주문이 한 건이면 자동 선택
        selected_order = customer_orders[0]

    # -----------------------------------------------------
    # 4. 배송지 변경 가능 여부 Policy 판단
    # -----------------------------------------------------

    address_change_result = judge_delivery_address_change(
        order_status=selected_order["order_status"],
        delivery_status=selected_order["delivery_status"],
    )

    # -----------------------------------------------------
    # 5. 조회 결과 + Policy 결과 반환
    # -----------------------------------------------------

    return {
        "result_type": "success",
        "order_id": selected_order["order_id"],
        "order_status": selected_order["order_status"],
        "delivery_status": selected_order["delivery_status"],
        "delivery_address": selected_order["delivery_address"],
        "order_date": selected_order["order_date"],
        "total_price": selected_order["total_price"],
        "address_change_judgment": (
            address_change_result["address_change_judgment"]
        ),
        "reason": address_change_result["reason"],
    }


# =========================================================
# 주문 취소 Action
# =========================================================

def cancel_order(
    orders: list[dict],
    payments: list[dict],
    refunds: list[dict],
    customer_id: int,
    order_id: int,
) -> dict:
    """
    사용자의 최종 승인이 확인된 이후
    실제 주문 및 결제 상태를 취소 처리한다.

    이 함수는 Write Action이므로
    Orchestrator가 사용자 승인을 확인한 이후에만 호출해야 한다.
    """

    # -----------------------------------------------------
    # 1. 고객의 주문 확인

    order = next(
        (
            order
            for order in orders
            if order["customer_id"] == customer_id
            and order["order_id"] == order_id
        ),
        None,
    )

    if order is None:
        return {
            "result_type": "action_failed",
            "reason": "order_not_found",
            "order_id": order_id,
        }

    # -----------------------------------------------------
    # 2. 결제 정보 확인

    payment = next(
        (
            payment
            for payment in payments
            if payment["order_id"] == order_id
        ),
        None,
    )

    if payment is None:
        return {
            "result_type": "action_failed",
            "reason": "payment_not_found",
            "order_id": order_id,
        }

    # -----------------------------------------------------
    # 3. Action 직전 주문 취소 가능 여부 재확인

    cancel_result = judge_order_cancel(
        order_status=order["order_status"],
        delivery_status=order["delivery_status"],
    )

    if cancel_result["cancel_judgment"] != "cancelable":
        return {
            "result_type": "action_failed",
            "reason": cancel_result["reason"],
            "order_id": order_id,
        }

    # 결제 상태도 Action 직전에 다시 확인
    if payment["payment_status"] != "payment_completed":
        return {
            "result_type": "action_failed",
            "reason": "invalid_payment_status",
            "order_id": order_id,
        }

    payment_method = payment["payment_method"]

    if payment_method not in {"card", "cash"}:
        return {
            "result_type": "action_failed",
            "reason": "unsupported_payment_method",
            "order_id": order_id,
        }

    # -----------------------------------------------------
    # 4. 주문 및 결제 취소

    order["order_status"] = "order_canceled"
    payment["payment_status"] = "payment_canceled"

    # -----------------------------------------------------
    # 5. Refund ID 생성

    refund_id = (
        max(
            refund["refund_id"]
            for refund in refunds
        )
        + 1
        if refunds
        else 70001
    )

    # -----------------------------------------------------
    # 6. 결제 방식에 따른 환불 상태 결정

    if payment_method == "card":
        refund_status = "refund_processing"
        result_type = "success"

    else:
        refund_status = "refund_account_required"
        result_type = "refund_account_required"

    # -----------------------------------------------------
    # 7. 환불 데이터 생성

    refund = {
        "refund_id": refund_id,
        "payment_id": payment["payment_id"],
        "order_id": order_id,
        "refund_amount": payment["payment_amount"],
        "refund_status": refund_status,
        "bank_name": None,
        "account_number": None,
        "account_holder": None,
    }

    refunds.append(refund)

    # -----------------------------------------------------
    # 8. Action 결과 반환

    return {
        "result_type": result_type,
        "order_id": order_id,
        "order_status": order["order_status"],
        "payment_id": payment["payment_id"],
        "payment_method": payment_method,
        "payment_status": payment["payment_status"],
        "refund_id": refund_id,
        "refund_status": refund_status,
    }

# =========================================================
# 환불계좌 등록 Action
# =========================================================

def register_refund_account(
    refunds: list[dict],
    order_id: int,
    bank_name: str,
    account_number: str,
    account_holder: str,
) -> dict:
    """
    계좌이체 주문 취소 후 환불계좌를 등록한다.

    refund_account_required 상태인 환불 건에만
    계좌정보를 저장하고 refund_processing으로 변경한다.
    """

    # -----------------------------------------------------
    # 1. 해당 주문의 환불 데이터 확인
    # -----------------------------------------------------

    refund = next(
        (
            refund
            for refund in refunds
            if refund["order_id"] == order_id
        ),
        None,
    )

    if refund is None:
        return {
            "result_type": "action_failed",
            "reason": "refund_not_found",
            "order_id": order_id,
        }

    # -----------------------------------------------------
    # 2. 현재 환불 상태 재확인
    # -----------------------------------------------------

    if refund["refund_status"] != "refund_account_required":
        return {
            "result_type": "action_failed",
            "reason": "invalid_refund_status",
            "order_id": order_id,
        }

    # -----------------------------------------------------
    # 3. 환불계좌 정보 저장
    # -----------------------------------------------------

    refund["bank_name"] = bank_name
    refund["account_number"] = account_number
    refund["account_holder"] = account_holder

    # 계좌정보 등록 완료 → 환불 처리중
    refund["refund_status"] = "refund_processing"

    # -----------------------------------------------------
    # 4. 결과 반환
    # -----------------------------------------------------

    return {
        "result_type": "success",
        "order_id": order_id,
        "refund_id": refund["refund_id"],
        "refund_status": refund["refund_status"],
        "bank_name": refund["bank_name"],
        "account_number": refund["account_number"],
        "account_holder": refund["account_holder"],
    }

# =========================================================
# 배송지 변경 Action
# =========================================================

def change_delivery_address(
    orders: list[dict],
    customer_id: int,
    order_id: int,
    new_delivery_address: str,
) -> dict:
    """
    사용자의 최종 승인이 확인된 이후
    실제 주문의 배송지를 변경한다.

    이 함수는 Write Action이므로
    Orchestrator가 사용자 승인을 확인한 이후에만 호출해야 한다.
    """

    # -----------------------------------------------------
    # 1. 변경할 주소 기본 검증

    normalized_address = new_delivery_address.strip()

    if not normalized_address:
        return {
            "result_type": "action_failed",
            "reason": "invalid_delivery_address",
            "order_id": order_id,
        }

    # -----------------------------------------------------
    # 2. 해당 고객의 주문 확인

    order = next(
        (
            order
            for order in orders
            if order["customer_id"] == customer_id
            and order["order_id"] == order_id
        ),
        None,
    )

    if order is None:
        return {
            "result_type": "action_failed",
            "reason": "order_not_found",
            "order_id": order_id,
        }

    # -----------------------------------------------------
    # 3. Action 직전 배송지 변경 가능 여부 재확인

    address_change_result = judge_delivery_address_change(
        order_status=order["order_status"],
        delivery_status=order["delivery_status"],
    )

    if (
        address_change_result["address_change_judgment"]
        != "changeable"
    ):
        return {
            "result_type": "action_failed",
            "reason": address_change_result["reason"],
            "order_id": order_id,
        }

    # -----------------------------------------------------
    # 4. 기존 배송지 보관

    previous_delivery_address = order["delivery_address"]

    # -----------------------------------------------------
    # 5. 실제 배송지 변경

    order["delivery_address"] = normalized_address

    # -----------------------------------------------------
    # 6. Action 결과 반환

    return {
        "result_type": "success",
        "order_id": order_id,
        "previous_delivery_address": previous_delivery_address,
        "new_delivery_address": order["delivery_address"],
    }

# =========================================================
# 주문 확인 결과 → 사용자 응답 생성
# =========================================================

def generate_order_response(result: dict) -> str:

    result_type = result["result_type"]

    # 주문을 찾지 못한 경우
    if result_type == "not_found":
        return "확인되는 주문이 없습니다. 주문번호를 다시 확인해주세요."

    # 주문이 여러 개라 선택이 필요한 경우
    if result_type == "need_order_selection":

        candidate_orders = result["candidate_orders"]

        order_list = "\n\n".join(
            f"- 주문번호 {order['order_id']}\n"
            f"  · 상품명: {order.get('product_name') or '상품명 확인 불가'}\n"
            f"  · 주문일: {order['order_date']}\n"
            f"  · 금액: {order['total_price']:,}원"
            for order in candidate_orders
        )

        return (
            "최근 주문이 여러 건 있습니다.\n"
            "확인할 주문을 선택해주세요.\n\n"
            f"{order_list}"
        )

    # 주문을 정상적으로 찾은 경우
    if result_type == "success":

        order_status = result["order_status"]
        order_id = result["order_id"]

        if order_status == "order_completed":
            return (
                f"주문번호 {order_id}의 주문은 "
                "정상적으로 완료되었습니다."
            )

        if order_status == "order_canceled":
            return (
                f"주문번호 {order_id}의 주문은 "
                "취소된 상태입니다."
            )

        if order_status == "order_failed":
            return (
                f"주문번호 {order_id}의 주문은 "
                "정상적으로 완료되지 않았습니다."
            )

    return "주문 상태를 확인하는 중 문제가 발생했습니다."


# =========================================================
# 결제 완료 확인
# =========================================================

def check_payment_completion(
    orders: list[dict],
    payments: list[dict],
    customer_id: int,
    order_id: int | None = None
) -> dict:

    # 해당 고객의 주문만 조회
    customer_orders = [
        order
        for order in orders
        if order["customer_id"] == customer_id
    ]

    # ---------------------------------------------------------
    # 사용자가 주문번호를 직접 입력한 경우
    if order_id is not None:

        selected_order = next(
            (
                order
                for order in customer_orders
                if order["order_id"] == order_id
            ),
            None
        )

        # 해당 고객의 주문이 아닌 경우
        if selected_order is None:
            return {
                "result_type": "not_found"
            }

        selected_order_id = order_id

    # ---------------------------------------------------------
    # 주문번호가 없는 경우
    else:

        # 고객의 주문 자체가 없는 경우
        if len(customer_orders) == 0:
            return {
                "result_type": "not_found"
            }

        # 주문이 여러 개라면 사용자가 선택해야 함
        if len(customer_orders) > 1:
            return {
                "result_type": "need_order_selection",
                "candidate_orders": _recent_order_choices(customer_orders, payments=payments)
            }

        # 주문이 하나라면 자동 선택
        selected_order_id = customer_orders[0]["order_id"]

    # ---------------------------------------------------------
    # 선택된 주문의 결제 데이터 조회
    payment = next(
        (
            payment
            for payment in payments
            if payment["order_id"] == selected_order_id
        ),
        None
    )

    # 결제 데이터가 없는 경우
    if payment is None:
        return {
            "result_type": "not_found"
        }

    # 결제 데이터 조회 성공
    return {
        "result_type": "success",
        "judgment": judge_payment_completion(payment["payment_status"]),
        "order_id": selected_order_id,
        "payment_id": payment["payment_id"],
        "payment_status": payment["payment_status"],
        "payment_method": payment["payment_method"],
        "payment_amount": payment["payment_amount"],
        "payment_date": payment["payment_date"]
    }


# =========================================================
# 결제 완료 확인 응답 생성
# =========================================================
def generate_payment_response(result: dict) -> str:

    result_type = result["result_type"]

    # ---------------------------------------------------------
    # 주문 또는 결제 정보를 찾지 못한 경우

    if result_type == "not_found":
        return "확인할 수 있는 주문 또는 결제 정보가 없습니다."

    # ---------------------------------------------------------
    # 주문이 여러 개라 사용자의 선택이 필요한 경우

    if result_type == "need_order_selection":

        candidate_orders = result["candidate_orders"][:3]

        method_labels = {"card": "카드", "bank_transfer": "계좌이체", "virtual_account": "가상계좌"}
        order_list = "\n\n".join(
            [
                f"- 주문번호: {order['order_id']}\n"
                f"- 상품명: {order.get('product_name') or '상품명 확인 불가'}\n"
                f"- 주문일: {order['order_date']}\n"
                f"- 금액: {order['total_price']:,}원\n"
                f"- 결제수단: {method_labels.get(order.get('payment_method'), order.get('payment_method') or '확인 불가')}"
                for order in candidate_orders
            ]
        )

        return (
            "최근 결제 내역 3건입니다. 확인할 주문을 선택해 주세요.\n\n"
            f"{order_list}\n\n무엇을 도와드릴까요?"
        )

    # ---------------------------------------------------------
    # 결제 데이터 조회 성공
    if result_type == "success":

        order_id = result["order_id"]
        payment_status = result["payment_status"]
        payment_method = result["payment_method"]
        payment_amount = result["payment_amount"]
        payment_date = result["payment_date"]

        if payment_status == "payment_completed":
            return (
                f"주문번호 {order_id}의 결제가 정상적으로 완료되었습니다.\n"
                f"결제금액: {payment_amount:,}원\n"
                f"결제수단: {payment_method}\n"
                f"결제일: {payment_date}"
            )

        if payment_status == "payment_failed":
            return (
                f"주문번호 {order_id}의 결제가 완료되지 않았습니다. "
                "결제 시도 중 실패한 것으로 확인됩니다."
            )

        if payment_status == "payment_canceled":
            return (
                f"주문번호 {order_id}의 결제는 취소된 상태입니다."
            )

    return "결제 상태를 확인할 수 없습니다."

def check_order_payment_consistency(
    orders: list[dict],
    payments: list[dict],
    customer_id: int,
    order_id: int,
) -> dict:
    """
    특정 주문의 주문 상태와 결제 상태가
    서로 일관된지 확인한다.
    """


    # 1. 해당 고객의 주문 확인

    order = next(
        (
            order
            for order in orders
            if order["customer_id"] == customer_id
            and order["order_id"] == order_id
        ),
        None,
    )

    if order is None:
        return {
            "result_type": "order_not_found",
            "consistency_judgment": "order_not_found",
            "order_id": order_id,
        }

    # 2. 해당 주문의 결제 정보 확인

    payment = next(
        (
            payment
            for payment in payments
            if payment["order_id"] == order_id
        ),
        None,
    )

    if payment is None:
        return {
            "result_type": "payment_not_found",
            "consistency_judgment": "payment_not_found",
            "order_id": order_id,
            "order_status": order["order_status"],
        }

    # 3. 주문-결제 상태 일관성 판정

    consistency_judgment = judge_order_payment_consistency(
        order_status=order["order_status"],
        payment_status=payment["payment_status"],
    )

    return {
        "result_type": "success",
        "consistency_judgment": consistency_judgment,
        "order_id": order_id,
        "order_status": order["order_status"],
        "payment_status": payment["payment_status"],
    }
