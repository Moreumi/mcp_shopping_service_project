from backend.cs.llm_service import classification_chain

from backend.cs.order_payment_service import (
    check_order_completion,
    generate_order_response,
    check_payment_completion,
    generate_payment_response,
    check_order_payment_consistency,
    check_order_cancel_eligibility,
    cancel_order,
    register_refund_account,
    check_delivery_address_change_eligibility,
    change_delivery_address,
)

from backend.cs.policies.order_payment_consistency_policy import (
    ORDER_PAYMENT_CONSISTENCY_POLICY_CONTEXT,
)

from backend.cs.state_service import (
    reset_state,
    extract_order_id,
    extract_ordinal_index,
    extract_confirmation,
    extract_refund_account,
    extract_delivery_address,
)

from backend.cs.response_service import generate_cs_response

from backend.cs.policies.order_completion_policy import (
    ORDER_COMPLETION_POLICY_CONTEXT,
)

from backend.cs.policies.payment_completion_policy import (
    PAYMENT_COMPLETION_POLICY_CONTEXT,
)

from backend.cs.policies.payment_method_change_policy import (
    judge_payment_method_change,
)


# =========================================================
# 1. 주문 완료 확인 최종 응답 생성
# =========================================================

def build_order_confirmation_response(
    user_input: str,
    result: dict,
    consistency_result: dict | None = None,
) -> str:
    """
    주문 완료 확인 결과와 주문-결제 일관성 결과에 따라
    최종 응답 생성 방식을 결정한다.

    - 주문 조회 실패 / 선택 필요:
      기존 Python 응답 사용

    - 주문 조회 성공 + 일관성 문제 없음:
      fact_summary 사용

    - 주문 조회 성공 + 주문/결제 불일치:
      narrative_guidance 사용
    """

    if result.get("result_type") != "success":
        return generate_order_response(result)

    # 주문-결제 상태가 비정상적이거나
    # 결제 정보를 확인할 수 없는 경우
    if consistency_result is not None:
        consistency_judgment = consistency_result.get(
            "consistency_judgment"
        )

        if consistency_judgment in {
            "needs_review",
            "payment_not_found",
            "order_not_found",
        }:
            combined_result = {
                "order_result": result,
                "consistency_result": consistency_result,
            }

            return generate_cs_response(
                user_input=user_input,
                sub_intent="order_confirmation",
                response_mode="narrative_guidance",
                result=combined_result,
                policy_context=(
                    ORDER_COMPLETION_POLICY_CONTEXT
                    + "\n\n"
                    + ORDER_PAYMENT_CONSISTENCY_POLICY_CONTEXT
                ),
            )

    # 정상적인 조회 결과
    return generate_cs_response(
        user_input=user_input,
        sub_intent="order_confirmation",
        response_mode="fact_summary",
        result=result,
        policy_context=ORDER_COMPLETION_POLICY_CONTEXT,
    )


# =========================================================
# 2. 결제 완료 확인 최종 응답 생성
# =========================================================

def build_payment_confirmation_response(
    user_input: str,
    result: dict,
    consistency_result: dict | None = None,
) -> str:
    """
    결제 완료 확인 결과와 주문-결제 일관성 결과에 따라
    최종 응답 생성 방식을 결정한다.

    - 결제 조회 실패 / 선택 필요:
      기존 Python 응답 사용

    - 결제 조회 성공 + 일관성 문제 없음:
      fact_summary 사용

    - 결제 조회 성공 + 주문/결제 불일치:
      narrative_guidance 사용
    """

    if result.get("result_type") != "success":
        return generate_payment_response(result)

    if consistency_result is not None:
        consistency_judgment = consistency_result.get(
            "consistency_judgment"
        )

        if consistency_judgment in {
            "needs_review",
            "payment_not_found",
            "order_not_found",
        }:
            combined_result = {
                "payment_result": result,
                "consistency_result": consistency_result,
            }

            return generate_cs_response(
                user_input=user_input,
                sub_intent="payment_confirmation",
                response_mode="narrative_guidance",
                result=combined_result,
                policy_context=(
                    PAYMENT_COMPLETION_POLICY_CONTEXT
                    + "\n\n"
                    + ORDER_PAYMENT_CONSISTENCY_POLICY_CONTEXT
                ),
            )

    return generate_cs_response(
        user_input=user_input,
        sub_intent="payment_confirmation",
        response_mode="fact_summary",
        result=result,
        policy_context=PAYMENT_COMPLETION_POLICY_CONTEXT,
    )


# =========================================================
# 3. 주문 취소 가능 여부 결과 → 사용자 응답
# =========================================================

def build_order_cancel_pre_action_response(result: dict) -> str:
    """
    실제 주문 취소 Action을 실행하기 전 단계의 응답을 생성한다.

    - 주문 조회 실패
    - 주문 선택 필요
    - 취소 가능 → 최종 승인 요청
    - 취소 불가
    - 이미 취소됨

    을 처리한다.
    """

    result_type = result["result_type"]

    # 주문을 찾지 못한 경우
    if result_type == "not_found":
        return (
            "취소할 주문을 확인할 수 없습니다. "
            "주문번호를 다시 확인해주세요."
        )

    # 주문이 여러 건이라 선택이 필요한 경우
    if result_type == "need_order_selection":
        candidate_orders = result["candidate_orders"][:3]

        method_labels = {"card": "카드", "bank_transfer": "계좌이체", "virtual_account": "가상계좌"}
        order_list = "\n\n".join(
            f"- 주문번호: {order['order_id']}\n"
            f"- 상품명: {order.get('product_name') or '상품명 확인 불가'}\n"
            f"- 주문일: {order['order_date']}\n"
            f"- 금액: {order['total_price']:,}원\n"
            f"- 결제수단: {method_labels.get(order.get('payment_method'), order.get('payment_method') or '확인 불가')}"
            for order in candidate_orders
        )

        return (
            "최근 결제 내역 3건입니다. 취소할 주문을 선택해 주세요.\n\n"
            f"{order_list}\n\n무엇을 도와드릴까요?"
        )

    # 정상 조회가 아닌 예상하지 못한 결과
    if result_type != "success":
        return "주문 취소 가능 여부를 확인하는 중 문제가 발생했습니다."

    cancel_judgment = result["cancel_judgment"]
    reason = result["reason"]
    order_id = result["order_id"]

    # 취소 가능 → 아직 Action 실행 X
    if cancel_judgment == "cancelable":
        return (
            "아래 주문을 취소하시겠어요?\n\n"
            f"- 주문번호: {order_id}\n"
            f"- 상품명: {result.get('product_name') or '상품명 확인 불가'}\n"
            f"- 금액: {result.get('total_price', 0):,}원\n\n"
            "예 / 아니오"
        )

    # 이미 취소된 주문
    if cancel_judgment == "already_canceled":
        return "이미 정상적으로 주문이 취소되었습니다."

    # 배송중
    if (
        cancel_judgment == "not_cancelable"
        and reason == "in_transit"
    ):
        return (
            "현재 배송 중인 주문은 취소가 어렵습니다. "
            "상품을 수령하신 후 취소를 원하시는 경우에는 "
            "교환/환불 카테고리로 문의해 주세요."
        )

    # 배송완료
    if (
        cancel_judgment == "not_cancelable"
        and reason == "delivered"
    ):
        return (
            "배송이 이미 완료되어 현재 주문 취소는 어렵습니다. "
            "배송 완료된 주문에 대해 취소를 원하시는 경우에는 "
            "교환/환불 카테고리로 문의해 주세요."
        )

    # 주문 실패
    if (
        cancel_judgment == "not_cancelable"
        and reason == "order_failed"
    ):
        return (
            "정상적으로 완료되지 않은 주문으로 "
            "주문 취소를 진행할 수 없습니다."
        )

    # 정의하지 않은 상태
    return (
        "현재 주문 상태만으로 취소 가능 여부를 확인하기 어렵습니다. "
        "추가 확인이 필요합니다."
    )


# =========================================================
# 4. 주문 취소 Action 결과 → 사용자 응답
# =========================================================

def build_order_cancel_action_response(result: dict) -> str:
    """
    실제 주문 취소 Action 실행 후 결과에 따라
    사용자에게 안내할 응답을 생성한다.
    """

    result_type = result["result_type"]

    # 카드 결제 취소
    if (
        result_type == "success"
        and result.get("payment_method") == "card"
    ):
        return (
            "주문이 정상적으로 취소되었습니다. "
            "카드 결제 취소는 카드사를 통해 처리되며, "
            "환불 완료까지 영업일 기준 7일 정도 소요될 수 있습니다."
        )

    # 계좌이체 결제 취소
    if result_type == "refund_account_required":
        return (
            "주문이 정상적으로 취소되었습니다. "
            "환불을 위해 환불받으실 계좌 정보를 입력해 주세요."
        )

    # Action 실패
    if result_type == "action_failed":
        return (
            "주문 취소 처리 중 문제가 발생했습니다. "
            "현재 주문 상태를 다시 확인해 주세요."
        )

    return "주문 취소 처리 결과를 확인하는 중 문제가 발생했습니다."


# =========================================================
# 배송지 변경 가능 여부 결과 → 사용자 응답
# =========================================================

def build_delivery_address_change_response(result: dict) -> str:

    result_type = result["result_type"]

    # 주문을 찾지 못한 경우
    if result_type == "not_found":
        return (
            "배송지를 변경할 주문을 확인할 수 없습니다. "
            "주문번호를 다시 확인해 주세요."
        )

    # 여러 주문 중 선택이 필요한 경우
    if result_type == "need_order_selection":
        candidate_orders = result["candidate_orders"]

        order_list = "\n\n".join(
            f"- 주문번호 {order['order_id']}\n"
            f"  · 주문일: {order['order_date']}\n"
            f"  · 금액: {order['total_price']:,}원\n"
            f"  · 배송지: {order['delivery_address']}"
            for order in candidate_orders
        )

        return (
            "배송지를 변경할 주문을 선택해 주세요.\n\n"
            f"{order_list}"
        )

    if result_type != "success":
        return "배송지 변경 가능 여부를 확인하는 중 문제가 발생했습니다."

    judgment = result["address_change_judgment"]
    reason = result["reason"]

    # 배송지 변경 가능
    if judgment == "changeable":
        return "변경할 새로운 배송지를 입력해 주세요."

    if (
        judgment == "not_changeable"
        and reason == "in_transit"
    ):
        return (
            "이미 배송이 시작된 주문은 "
            "배송지를 변경할 수 없습니다."
        )

    if (
        judgment == "not_changeable"
        and reason == "delivered"
    ):
        return (
            "이미 배송이 완료된 주문은 "
            "배송지를 변경할 수 없습니다."
        )

    if (
        judgment == "not_changeable"
        and reason == "order_canceled"
    ):
        return (
            "이미 취소된 주문은 "
            "배송지를 변경할 수 없습니다."
        )

    if (
        judgment == "not_changeable"
        and reason == "order_failed"
    ):
        return (
            "정상적으로 완료되지 않은 주문은 "
            "배송지를 변경할 수 없습니다."
        )

    return (
        "현재 주문 상태만으로 배송지 변경 가능 여부를 "
        "확인하기 어렵습니다. 추가 확인이 필요합니다."
    )

# =========================================================
# 결제수단 변경 Policy 결과 → 사용자 응답
# =========================================================

def build_payment_method_change_response(result: dict) -> str:
    """
    결제 완료 후 결제수단 변경 요청에 대한
    Policy 결과를 사용자 안내 문장으로 변환한다.
    """

    judgment = result["payment_method_change_judgment"]
    recommended_action = result["recommended_action"]

    if (
        judgment == "not_changeable"
        and recommended_action == "cancel_and_reorder"
    ):
        return (
            "결제가 완료된 주문은 결제수단을 직접 변경할 수 없습니다. "
            "다른 결제수단을 이용하시려면 기존 주문을 취소한 후 "
            "원하시는 결제수단으로 다시 주문해 주세요."
        )

    return (
        "결제수단 변경 가능 여부를 확인하는 중 "
        "문제가 발생했습니다."
    )

# =========================================================
# 5. 이전 대화에서 처리 중인 State 확인
# =========================================================

_INTERRUPTIBLE_PENDING_STATES = {
    "order_cancel_selection",
    "delivery_address_change_selection",
    "order_confirmation",
    "payment_confirmation",
    "confirm_cancel",
    "collect_refund_account",
    "collect_delivery_address",
    "confirm_delivery_address_change",
}

_ORDER_LIST_RESET_TERMS = (
    "다른 주문", "다른 거", "다른것", "다른 것", "주문 목록",
    "최근 주문", "전체 주문", "모든 주문", "목록 보여",
)


def _should_reuse_active_order(user_input: str) -> bool:
    """False when the customer explicitly asks to leave the active order."""
    normalized = " ".join(user_input.split()).lower()
    return not any(term in normalized for term in _ORDER_LIST_RESET_TERMS)


def _is_bare_order_overview_request(user_input: str) -> bool:
    """A generic order lookup means 'show my recent orders', not active order."""
    normalized = "".join(user_input.lower().split())
    return normalized in {
        "주문", "주문확인", "주문내역", "내주문", "내주문확인",
        "최근주문", "최근주문확인", "최근주문내역",
    }


def _conversation_context(state: dict) -> str:
    """Build a small, factual context packet for local intent classification."""
    recent_ids = [
        order.get("order_id")
        for order in (state.get("recent_candidate_orders") or [])[:3]
        if order.get("order_id") is not None
    ]
    lines = [
        f"진행 중 작업: {state.get('pending_action') or '없음'}",
        f"활성 주문번호: {state.get('last_order_id') or '없음'}",
        f"최근 목록 작업: {state.get('recent_list_intent') or '없음'}",
        f"최근 목록 주문번호(표시 순서): {recent_ids or '없음'}",
    ]
    history = state.get("history") or []
    if history:
        lines.append("최근 대화:")
        for turn in history[-6:]:
            role = "고객" if turn.get("role") == "user" else "상담원"
            content = " ".join(str(turn.get("content") or "").split())[:300]
            lines.append(f"- {role}: {content}")
    return "\n".join(lines)


def _explicit_sub_intent(user_input: str) -> str | None:
    """Return an intent only when the current message states it explicitly.

    This deterministic layer prevents a local model from copying a stale
    intent from conversation history when the customer clearly changes topic.
    """
    normalized = "".join(user_input.lower().split())
    if (("배송지" in normalized or "주소" in normalized) and
            any(term in normalized for term in ("변경", "바꿔", "바꾸"))):
        return "delivery_address_change"
    if "결제수단" in normalized and any(
        term in normalized for term in ("변경", "바꿔", "바꾸")
    ):
        return "payment_method_change"
    if "결제수단" in normalized and any(
        term in normalized for term in ("알려", "뭐", "무엇", "확인", "조회")
    ):
        return "payment_confirmation"
    if "취소" in normalized:
        return "order_cancel"
    if "주문" in normalized and any(
        term in normalized for term in ("수량변경", "수량바꿔", "수량바꾸", "내용변경")
    ):
        return "order_change"
    if "결제" in normalized and any(
        term in normalized for term in ("확인", "내역", "상태", "됐", "완료")
    ):
        return "payment_confirmation"
    if "주문" in normalized and any(
        term in normalized for term in ("확인", "내역", "상태", "됐", "완료")
    ):
        return "order_confirmation"
    return None


def _prefer_explicit_current_intent(user_input: str, request):
    explicit_intent = _explicit_sub_intent(user_input)
    if explicit_intent is not None:
        request.intent = "cs"
        request.cs_category = "order_payment"
        request.sub_intent = explicit_intent
    return request


def _reset_if_new_topic(user_input: str, state: dict) -> bool:
    """A pending flow waiting for an order number can get stuck forever if the
    customer instead types an unrelated new request (e.g. "주문확인" while a
    never-completed 주문 취소 flow is still pending) - extract_order_id finds
    no digits and the flow just re-prompts for a number indefinitely. If the
    message doesn't look like an order number and re-classifies to a
    different, valid CS request, treat it as a topic change instead.
    """
    if state["pending_action"] not in _INTERRUPTIBLE_PENDING_STATES:
        return False

    pending_action = state["pending_action"]
    if pending_action in {
        "order_cancel_selection", "delivery_address_change_selection",
        "order_confirmation", "payment_confirmation",
    } and (
        extract_order_id(user_input) is not None
        or extract_ordinal_index(user_input) is not None
    ):
        return False
    if pending_action in {
        "confirm_cancel", "confirm_delivery_address_change"
    } and extract_confirmation(user_input) is not None:
        return False
    if pending_action == "collect_refund_account" and extract_refund_account(user_input) is not None:
        return False
    if (
        pending_action == "collect_delivery_address"
        and _explicit_sub_intent(user_input) is None
        and extract_delivery_address(user_input) is not None
    ):
        return False
    try:
        request = classification_chain.invoke({
            "user_input": user_input,
            "conversation_context": _conversation_context(state),
        })
        request = _prefer_explicit_current_intent(user_input, request)
    except Exception:
        return False
    if (
        request.intent == "cs"
        and request.cs_category == "order_payment"
        and request.sub_intent not in (None, "unknown")
    ):
        reset_state(state)
        state["pending_data"]["topic_switch_request"] = request.model_dump()
        return True
    return False


def _resolve_selected_order_id(user_input: str, candidate_orders: list[dict]) -> int | None:
    """A customer picking from an announced list may type the real order
    number, or may just say "첫번째" (the first one) / "2번째" (the second
    one) / "마지막" (the last one) - resolve either form to the actual
    order_id. Ordinal must be checked first: extract_order_id's bare \\d+
    scan would otherwise misread the "2" in "2번째" as a literal order
    number instead of "index 1"."""
    index = extract_ordinal_index(user_input)
    if index is not None:
        try:
            return candidate_orders[index]["order_id"]
        except IndexError:
            return None
    return extract_order_id(user_input)


def _remember_order_list(state: dict, orders: list[dict], sub_intent: str) -> None:
    """Keep list context independently from the currently pending workflow."""
    state["recent_candidate_orders"] = list(orders)
    state["recent_list_intent"] = sub_intent


def handle_pending_state(
    user_input: str,
    customer_id: int,
    orders: list[dict],
    state: dict,
    payments: list[dict] | None = None,
    refunds: list[dict] | None = None,
) -> dict | None:

    # 현재 기다리고 있는 후속 작업이 없는 경우
    if state["pending_action"] is None:
        return None

    # 주문번호를 기다리는 중인데 전혀 다른 새 요청이 들어온 경우,
    # 계속 재입력을 요구하지 않고 새 요청으로 전환한다.
    if _reset_if_new_topic(user_input, state):
        return None

    # -----------------------------------------------------
    # 배송지 변경 - 새 주소 입력
    # -----------------------------------------------------

    if state["pending_action"] == "collect_delivery_address":

        selected_order_id = state["selected_order_id"]

        # 어떤 주문의 배송지를 변경하는지 확인할 수 없는 경우
        if selected_order_id is None:
            reset_state(state)

            return {
                "route": "delivery_address_change",
                "result": {
                    "result_type": "action_failed",
                    "reason": "selected_order_not_found",
                },
                "response": (
                    "배송지를 변경할 주문 정보를 확인할 수 없습니다. "
                    "주문번호를 다시 입력해 주세요."
                ),
            }

        # 현재 고객의 해당 주문 확인
        selected_order = next(
            (
                order
                for order in orders
                if order["customer_id"] == customer_id
                and order["order_id"] == selected_order_id
            ),
            None,
        )

        if selected_order is None:
            reset_state(state)

            return {
                "route": "delivery_address_change",
                "result": {
                    "result_type": "action_failed",
                    "reason": "order_not_found",
                },
                "response": (
                    "배송지를 변경할 주문을 확인할 수 없습니다. "
                    "주문번호를 다시 확인해 주세요."
                ),
            }

        # 사용자가 입력한 새 배송지 추출
        new_delivery_address = extract_delivery_address(
            user_input
        )

        # 주소가 비어 있는 경우
        if new_delivery_address is None:
            return {
                "route": "delivery_address_change",
                "result": None,
                "response": "변경할 새로운 배송지를 입력해 주세요.",
            }

        # -------------------------------------------------
        # 새 주소는 실제 주문에 반영하지 않고 State에만 저장
        # -------------------------------------------------

        state["pending_data"]["new_delivery_address"] = (
            new_delivery_address
        )

        state["pending_action"] = (
            "confirm_delivery_address_change"
        )

        current_delivery_address = (
            selected_order["delivery_address"]
        )

        return {
            "route": "delivery_address_change",
            "result": {
                "result_type": "confirmation_required",
                "order_id": selected_order_id,
                "current_delivery_address": (
                    current_delivery_address
                ),
                "new_delivery_address": (
                    new_delivery_address
                ),
            },
            "response": (
                f"현재 배송지: {current_delivery_address}\n"
                f"변경 배송지: {new_delivery_address}\n\n"
                "이 배송지로 변경하시겠어요? (예/아니오)"
            ),
        }

        # -----------------------------------------------------
    # 배송지 변경 - 최종 승인
    # -----------------------------------------------------

    if state["pending_action"] == "confirm_delivery_address_change":

        selected_order_id = state["selected_order_id"]

        new_delivery_address = state["pending_data"].get(
            "new_delivery_address"
        )

        # 어떤 주문인지 확인할 수 없는 경우
        if selected_order_id is None:
            reset_state(state)

            return {
                "route": "delivery_address_change",
                "result": {
                    "result_type": "action_failed",
                    "reason": "selected_order_not_found",
                },
                "response": (
                    "배송지를 변경할 주문 정보를 확인할 수 없습니다. "
                    "주문번호를 다시 입력해 주세요."
                ),
            }

        # 새 배송지 정보가 State에 없는 경우
        if new_delivery_address is None:
            reset_state(state)

            return {
                "route": "delivery_address_change",
                "result": {
                    "result_type": "action_failed",
                    "reason": "delivery_address_not_found",
                },
                "response": (
                    "변경할 배송지 정보를 확인할 수 없습니다. "
                    "배송지 변경을 다시 요청해 주세요."
                ),
            }

        # -------------------------------------------------
        # 사용자 최종 승인 여부 확인
        # -------------------------------------------------

        confirmation = extract_confirmation(user_input)

        # 승인/거절이 불명확
        if confirmation is None:
            return {
                "route": "delivery_address_change",
                "result": None,
                "response": (
                    f"배송지를 '{new_delivery_address}'로 "
                    "변경하시려면 '예', 변경하지 않으시려면 "
                    "'아니오'라고 입력해 주세요."
                ),
            }

        # -------------------------------------------------
        # 사용자가 변경을 거절
        # -------------------------------------------------

        if confirmation is False:
            reset_state(state)

            return {
                "route": "delivery_address_change",
                "result": {
                    "result_type": "change_aborted",
                    "order_id": selected_order_id,
                },
                "response": "배송지 변경을 진행하지 않았습니다.",
            }

        # -------------------------------------------------
        # 사용자가 명확하게 승인
        # 여기서만 Write Action 실행
        # -------------------------------------------------

        result = change_delivery_address(
            orders=orders,
            customer_id=customer_id,
            order_id=selected_order_id,
            new_delivery_address=new_delivery_address,
        )

        # Action 성공
        if result["result_type"] == "success":

            reset_state(state)

            return {
                "route": "delivery_address_change",
                "result": result,
                "response": (
                    "배송지가 정상적으로 변경되었습니다.\n\n"
                    f"- 이전 배송지: "
                    f"{result['previous_delivery_address']}\n"
                    f"- 변경 배송지: "
                    f"{result['new_delivery_address']}"
                ),
            }

        # Action 실패
        reset_state(state)

        return {
            "route": "delivery_address_change",
            "result": result,
            "response": (
                "배송지 변경을 처리하지 못했습니다. "
                "현재 주문 상태를 다시 확인해 주세요."
            ),
        }

    # -----------------------------------------------------
    # 배송지 변경 - 주문 선택
    # -----------------------------------------------------

    if state["pending_action"] == "delivery_address_change_selection":

        selected_order_id = _resolve_selected_order_id(user_input, state["candidate_orders"])

        # 주문번호를 확인할 수 없는 경우
        if selected_order_id is None:
            return {
                "route": "delivery_address_change",
                "result": None,
                "response": (
                    "배송지를 변경할 주문번호를 입력해 주세요."
                ),
            }

        # 사용자가 선택할 수 있는 주문인지 확인
        candidate_order_ids = {
            order["order_id"]
            for order in state["candidate_orders"]
        }

        if selected_order_id not in candidate_order_ids:
            return {
                "route": "delivery_address_change",
                "result": None,
                "response": (
                    "선택 가능한 주문번호가 아닙니다. "
                    "안내된 주문번호 중에서 선택해 주세요."
                ),
            }

        # 선택한 주문의 배송지 변경 가능 여부 재확인
        result = check_delivery_address_change_eligibility(
            orders=orders,
            customer_id=customer_id,
            order_id=selected_order_id,
        )

        # 배송지 변경 가능
        if (
            result["result_type"] == "success"
            and result["address_change_judgment"] == "changeable"
        ):
            state["pending_action"] = "collect_delivery_address"
            state["candidate_orders"] = []
            state["selected_order_id"] = selected_order_id
            state["last_order_id"] = selected_order_id
            state["pending_data"] = {}

        # 변경할 수 없는 주문이거나 조회에 문제가 있는 경우
        else:
            reset_state(state)

        response = build_delivery_address_change_response(result)

        return {
            "route": "delivery_address_change",
            "result": result,
            "response": response,
        }

    # -----------------------------------------------------
    # 주문 취소 최종 승인
    # -----------------------------------------------------

    if state["pending_action"] == "confirm_cancel":

        selected_order_id = state["selected_order_id"]

        # 어떤 주문에 대한 승인인지 확인할 수 없는 경우
        if selected_order_id is None:
            reset_state(state)

            return {
                "route": "order_cancel",
                "result": {
                    "result_type": "action_failed",
                    "reason": "selected_order_not_found",
                },
                "response": (
                    "취소할 주문 정보를 확인할 수 없습니다. "
                    "주문번호를 다시 입력해 주세요."
                ),
            }

        confirmation = extract_confirmation(user_input)

        # 승인/거절 여부가 명확하지 않은 경우
        if confirmation is None:
            return {
                "route": "order_cancel",
                "result": None,
                "response": (
                    f"주문번호 {selected_order_id}번 주문 취소를 "
                    "진행하시려면 '예', 취소하지 않으시려면 "
                    "'아니오'라고 입력해 주세요."
                ),
            }

        # 사용자가 취소를 거절한 경우
        if confirmation is False:
            reset_state(state)

            return {
                "route": "order_cancel",
                "result": {
                    "result_type": "cancel_aborted",
                    "order_id": selected_order_id,
                },
                "response": "주문 취소를 진행하지 않았습니다.",
            }

        # 사용자가 명확하게 승인한 경우
        # 여기서만 Write Action 실행
        if payments is None:
            payments = []

        if refunds is None:
            refunds = []

        result = cancel_order(
            orders=orders,
            payments=payments,
            refunds=refunds,
            customer_id=customer_id,
            order_id=selected_order_id,
        )

        response = build_order_cancel_action_response(result)

        # 계좌이체라 환불계좌가 필요한 경우
        if result["result_type"] == "refund_account_required":
            state["pending_action"] = "collect_refund_account"
            state["candidate_orders"] = []
            state["selected_order_id"] = selected_order_id
            state["last_order_id"] = selected_order_id

        # 카드 취소 성공 또는 Action 실패
        else:
            reset_state(state)

        return {
            "route": "order_cancel",
            "result": result,
            "response": response,
        }
    # -----------------------------------------------------
    # 환불계좌 정보 입력
    # -----------------------------------------------------

    if state["pending_action"] == "collect_refund_account":

        selected_order_id = state["selected_order_id"]

        # 어떤 주문의 환불인지 확인할 수 없는 경우
        if selected_order_id is None:
            reset_state(state)

            return {
                "route": "order_cancel",
                "result": {
                    "result_type": "action_failed",
                    "reason": "selected_order_not_found",
                },
                "response": (
                    "환불할 주문 정보를 확인할 수 없습니다. "
                    "주문번호를 다시 확인해 주세요."
                ),
            }

        # -------------------------------------------------
        # 사용자 입력에서 환불계좌 정보 추출

        account_info = extract_refund_account(user_input)

        # 입력 형식이 올바르지 않은 경우
        if account_info is None:
            return {
                "route": "order_cancel",
                "result": None,
                "response": (
                    "환불계좌 정보를 다음 형식으로 입력해 주세요.\n"
                    "은행명 / 계좌번호 / 예금주\n"
                    "예: 국민은행 / 1234567890 / 홍길동"
                ),
            }

        # refunds가 전달되지 않은 경우
        if refunds is None:
            refunds = []

        # -------------------------------------------------
        # 환불계좌 등록 Action

        result = register_refund_account(
            refunds=refunds,
            order_id=selected_order_id,
            bank_name=account_info["bank_name"],
            account_number=account_info["account_number"],
            account_holder=account_info["account_holder"],
        )

        # -------------------------------------------------
        # 계좌 등록 성공

        if result["result_type"] == "success":
            reset_state(state)

            return {
                "route": "order_cancel",
                "result": result,
                "response": (
                    "환불계좌가 정상적으로 등록되었습니다. "
                    "계좌이체 환불은 영업일 기준 "
                    "3~5일 정도 소요될 수 있습니다."
                ),
            }

        # -------------------------------------------------
        # 계좌 등록 Action 실패

        reset_state(state)

        return {
            "route": "order_cancel",
            "result": result,
            "response": (
                "환불계좌 등록 중 문제가 발생했습니다. "
                "환불 상태를 다시 확인해 주세요."
            ),
        }


    # -----------------------------------------------------
    # 주문 취소할 주문 선택
    # -----------------------------------------------------

    if state["pending_action"] == "order_cancel_selection":

        selected_order_id = _resolve_selected_order_id(user_input, state["candidate_orders"])

        # 주문번호를 찾지 못한 경우
        if selected_order_id is None:
            return {
                "route": "order_cancel",
                "result": None,
                "response": "취소할 주문번호를 입력해주세요.",
            }

        candidate_order_ids = [
            order["order_id"]
            for order in state["candidate_orders"]
        ]

        # 후보에 없는 주문번호를 선택한 경우
        if selected_order_id not in candidate_order_ids:
            return {
                "route": "order_cancel",
                "result": None,
                "response": (
                    "선택 가능한 주문번호 중에서 "
                    "다시 선택해주세요."
                ),
            }

        result = check_order_cancel_eligibility(
            orders=orders,
            customer_id=customer_id,
            order_id=selected_order_id,
            payments=payments,
        )

        # 취소 가능한 주문이면 최종 승인 State로 이동
        if (
            result["result_type"] == "success"
            and result["cancel_judgment"] == "cancelable"
        ):
            state["pending_action"] = "confirm_cancel"
            state["candidate_orders"] = []
            state["selected_order_id"] = selected_order_id
            state["last_order_id"] = selected_order_id

        # 취소 불가능하거나 이미 취소된 경우 작업 종료
        else:
            reset_state(state)

        response = build_order_cancel_pre_action_response(result)

        return {
            "route": "order_cancel",
            "result": result,
            "response": response,
        }

    # -----------------------------------------------------
    # 주문 완료 확인
    # -----------------------------------------------------

    if state["pending_action"] == "order_confirmation":

        selected_order_id = _resolve_selected_order_id(user_input, state["candidate_orders"])

        # 주문번호를 찾지 못한 경우
        if selected_order_id is None:
            return {
                "route": "order_confirmation",
                "result": None,
                "response": "확인할 주문번호를 입력해주세요.",
            }

        candidate_order_ids = [
            order["order_id"]
            for order in state["candidate_orders"]
        ]

        # 후보에 없는 주문번호를 선택한 경우
        if selected_order_id not in candidate_order_ids:
            return {
                "route": "order_confirmation",
                "result": None,
                "response": (
                    "선택 가능한 주문번호 중에서 다시 선택해주세요."
                ),
            }

        # 정상적인 주문번호를 선택한 경우
        result = check_order_completion(
            orders=orders,
            customer_id=customer_id,
            order_id=selected_order_id,
        )

        consistency_result = None

        if (
            result.get("result_type") == "success"
            and payments is not None
        ):
            consistency_result = check_order_payment_consistency(
                orders=orders,
                payments=payments,
                customer_id=customer_id,
                order_id=selected_order_id,
            )

        response = build_order_confirmation_response(
            user_input=user_input,
            result=result,
            consistency_result=consistency_result,
        )

        state["last_order_id"] = selected_order_id
        # 하나의 작업이 끝났으므로 State 초기화
        reset_state(state)

        return {
            "route": "order_confirmation",
            "result": result,
            "response": response,
        }

    # -----------------------------------------------------
    # 결제 완료 확인
    # -----------------------------------------------------

    if state["pending_action"] == "payment_confirmation":

        selected_order_id = _resolve_selected_order_id(user_input, state["candidate_orders"])

        # 주문번호를 찾지 못한 경우
        if selected_order_id is None:
            return {
                "route": "payment_confirmation",
                "result": None,
                "response": "결제를 확인할 주문번호를 입력해주세요.",
            }

        candidate_order_ids = [
            order["order_id"]
            for order in state["candidate_orders"]
        ]

        # 후보에 없는 주문번호를 선택한 경우
        if selected_order_id not in candidate_order_ids:
            return {
                "route": "payment_confirmation",
                "result": None,
                "response": (
                    "선택 가능한 주문번호 중에서 다시 선택해주세요."
                ),
            }

        if payments is None:
            payments = []

        result = check_payment_completion(
            orders=orders,
            payments=payments,
            customer_id=customer_id,
            order_id=selected_order_id,
        )

        consistency_result = None

        if result.get("result_type") == "success":
            consistency_result = check_order_payment_consistency(
                orders=orders,
                payments=payments,
                customer_id=customer_id,
                order_id=selected_order_id,
            )

        response = build_payment_confirmation_response(
            user_input=user_input,
            result=result,
            consistency_result=consistency_result,
        )

        state["last_order_id"] = selected_order_id
        # 작업 완료 후 State 초기화
        reset_state(state)

        return {
            "route": "payment_confirmation",
            "result": result,
            "response": response,
        }

    return None


# =========================================================
# 6. Router / Orchestrator
# =========================================================

def route_request(
    user_input: str,
    customer_id: int,
    orders: list[dict],
    state: dict,
    payments: list[dict] | None = None,
    refunds: list[dict] | None = None,
) -> dict:

    # -----------------------------------------------------
    # 1) 이전 대화에서 진행 중인 작업이 있는지 먼저 확인
    # -----------------------------------------------------

    pending_result = handle_pending_state(
        user_input=user_input,
        customer_id=customer_id,
        orders=orders,
        state=state,
        payments=payments,
        refunds=refunds,
    )

    if pending_result is not None:
        return pending_result

    # -----------------------------------------------------
    # 2) 진행 중인 작업이 없다면 새로운 질문으로 분류
    # -----------------------------------------------------

    # An ordinal-only follow-up refers to the latest list shown in this
    # conversation, even if the previous selection already completed and the
    # transient pending state was cleared.
    ordinal_index = extract_ordinal_index(user_input)
    recent_orders = state.get("recent_candidate_orders") or []
    recent_intent = state.get("recent_list_intent")
    contextual_order_id = None
    if ordinal_index is not None and recent_intent:
        try:
            contextual_order_id = recent_orders[ordinal_index]["order_id"]
        except (IndexError, KeyError, TypeError):
            contextual_order_id = None

    cached_request = state.get("pending_data", {}).pop("topic_switch_request", None)

    if cached_request is not None:
        from backend.cs.schemas import UserRequest

        request = UserRequest.model_validate(cached_request)
    elif contextual_order_id is not None:
        from backend.cs.schemas import UserRequest

        request = UserRequest(
            intent="cs",
            cs_category="order_payment",
            sub_intent=recent_intent,
            order_id=contextual_order_id,
        )
    else:
        request = classification_chain.invoke(
            {
                "user_input": user_input,
                "conversation_context": _conversation_context(state),
            }
        )

    request = _prefer_explicit_current_intent(user_input, request)

    # Explicit order numbers are deterministic evidence and must override a
    # local model that correctly classifies the intent but leaves order_id null.
    # Restrict this to order/payment actions so unrelated numbers are not
    # accidentally treated as order identifiers.
    if request.intent == "cs" and request.cs_category == "order_payment":
        explicit_order_id = extract_order_id(user_input)
        if explicit_order_id is not None:
            request.order_id = explicit_order_id
        elif _is_bare_order_overview_request(user_input) or not _should_reuse_active_order(user_input):
            # A list request is broader than the active-order context. Local
            # models sometimes copy the active order_id from the context even
            # for "최근 주문내역"; discard it deterministically.
            request.order_id = None
        elif request.order_id is None and _should_reuse_active_order(user_input) and request.sub_intent in {
            "order_confirmation", "payment_confirmation", "payment_method_change",
            "delivery_address_change", "order_cancel", "order_change",
        }:
            request.order_id = state.get("last_order_id")

    # -----------------------------------------------------
    # 3) 주문 완료 확인
    # -----------------------------------------------------

    if (
        request.intent == "cs"
        and request.cs_category == "order_payment"
        and request.sub_intent == "order_confirmation"
    ):

        result = check_order_completion(
            orders=orders,
            customer_id=customer_id,
            order_id=request.order_id,
        )

        # 주문이 여러 개라 추가 질문이 필요한 경우
        if result["result_type"] == "need_order_selection":
            state["pending_action"] = "order_confirmation"
            state["candidate_orders"] = result["candidate_orders"]
            _remember_order_list(state, result["candidate_orders"], "order_confirmation")
        elif result.get("result_type") == "success":
            state["last_order_id"] = result["order_id"]

        consistency_result = None

        if (
            result.get("result_type") == "success"
            and payments is not None
        ):
            consistency_result = check_order_payment_consistency(
                orders=orders,
                payments=payments,
                customer_id=customer_id,
                order_id=result["order_id"],
            )

        response = build_order_confirmation_response(
            user_input=user_input,
            result=result,
            consistency_result=consistency_result,
        )

        return {
            "route": "order_confirmation",
            "request": request.model_dump(),
            "result": result,
            "response": response,
        }

    # -----------------------------------------------------
    # 4) 결제 완료 확인
    # -----------------------------------------------------

    if (
        request.intent == "cs"
        and request.cs_category == "order_payment"
        and request.sub_intent == "payment_confirmation"
    ):

        if payments is None:
            payments = []

        result = check_payment_completion(
            orders=orders,
            payments=payments,
            customer_id=customer_id,
            order_id=request.order_id,
        )

        # 주문이 여러 개라 결제를 확인할 주문 선택이 필요한 경우
        if result["result_type"] == "need_order_selection":
            state["pending_action"] = "payment_confirmation"
            state["candidate_orders"] = result["candidate_orders"]
            _remember_order_list(state, result["candidate_orders"], "payment_confirmation")
        elif result.get("result_type") == "success":
            state["last_order_id"] = result["order_id"]

        consistency_result = None

        if result.get("result_type") == "success":
            consistency_result = check_order_payment_consistency(
                orders=orders,
                payments=payments,
                customer_id=customer_id,
                order_id=result["order_id"],
            )

        response = build_payment_confirmation_response(
            user_input=user_input,
            result=result,
            consistency_result=consistency_result,
        )

        return {
            "route": "payment_confirmation",
            "request": request.model_dump(),
            "result": result,
            "response": response,
        }

    # -----------------------------------------------------
    # 5) 주문 취소
    # -----------------------------------------------------

    if (
        request.intent == "cs"
        and request.cs_category == "order_payment"
        and request.sub_intent == "order_cancel"
    ):

        result = check_order_cancel_eligibility(
            orders=orders,
            customer_id=customer_id,
            order_id=request.order_id,
            payments=payments,
        )

        # 주문번호가 없고 주문이 여러 건인 경우
        if result["result_type"] == "need_order_selection":
            state["pending_action"] = "order_cancel_selection"
            state["candidate_orders"] = result["candidate_orders"]
            _remember_order_list(state, result["candidate_orders"], "order_cancel")
            state["selected_order_id"] = None

        # 주문을 찾았고 취소 가능한 경우
        elif (
            result["result_type"] == "success"
            and result["cancel_judgment"] == "cancelable"
        ):
            state["last_order_id"] = result["order_id"]
            state["pending_action"] = "confirm_cancel"
            state["candidate_orders"] = []
            state["selected_order_id"] = result["order_id"]

        response = build_order_cancel_pre_action_response(result)

        return {
            "route": "order_cancel",
            "request": request.model_dump(),
            "result": result,
            "response": response,
        }

    # -----------------------------------------------------
    # 6) 배송지 변경
    # -----------------------------------------------------

    if (
    request.intent == "cs"
    and request.cs_category == "order_payment"
    and request.sub_intent == "delivery_address_change"
    ):

        result = check_delivery_address_change_eligibility(
            orders=orders,
            customer_id=customer_id,
            order_id=request.order_id,
        )

        # 주문을 여러 건 보유하여 선택이 필요한 경우
        if result["result_type"] == "need_order_selection":
            state["pending_action"] = "delivery_address_change_selection"
            state["candidate_orders"] = result["candidate_orders"]
            _remember_order_list(state, result["candidate_orders"], "delivery_address_change")
            state["selected_order_id"] = None
            state["pending_data"] = {}

        # 주문이 특정되었고 배송지 변경이 가능한 경우
        elif (
            result["result_type"] == "success"
            and result["address_change_judgment"] == "changeable"
        ):
            state["pending_action"] = "collect_delivery_address"
            state["candidate_orders"] = []
            state["selected_order_id"] = result["order_id"]
            state["pending_data"] = {}

        response = build_delivery_address_change_response(result)

        return {
            "route": "delivery_address_change",
            "request": request.model_dump(),
            "result": result,
            "response": response,
        }

    # =====================================================
    # 7) 주문 수량/내용 변경
    # =====================================================

    if (
        request.intent == "cs"
        and request.cs_category == "order_payment"
        and request.sub_intent == "order_change"
    ):
        customer_orders = [
            order for order in orders if order.get("customer_id") == customer_id
        ]
        if request.order_id is None:
            candidates = sorted(
                customer_orders,
                key=lambda order: order.get("order_date", ""),
                reverse=True,
            )[:3]
            _remember_order_list(state, candidates, "order_change")
            order_list = "\n\n".join(
                f"- 주문번호: {order['order_id']}\n"
                f"- 상품명: {order.get('product_name') or '확인 불가'}\n"
                f"- 주문일: {order.get('order_date') or '확인 불가'}"
                for order in candidates
            )
            return {
                "route": "order_change",
                "request": request.model_dump(),
                "result": {"result_type": "need_order_selection", "candidate_orders": candidates},
                "response": f"수량을 변경할 주문을 선택해 주세요.\n\n{order_list}",
            }

        selected_order = next(
            (order for order in customer_orders if order.get("order_id") == request.order_id),
            None,
        )
        if selected_order is None:
            return {
                "route": "order_change",
                "request": request.model_dump(),
                "result": {"result_type": "not_found"},
                "response": "수량을 변경할 주문을 확인할 수 없습니다.",
            }

        state["last_order_id"] = selected_order["order_id"]
        return {
            "route": "order_change",
            "request": request.model_dump(),
            "result": {
                "result_type": "not_changeable",
                "order_id": selected_order["order_id"],
                "reason": "quantity_change_requires_reorder",
            },
            "response": (
                "주문 완료 후에는 상품 수량을 직접 변경할 수 없습니다.\n\n"
                f"- 주문번호: {selected_order['order_id']}\n"
                f"- 상품명: {selected_order.get('product_name') or '확인 불가'}\n\n"
                "수량을 변경하려면 취소 가능 여부를 확인한 뒤 원하는 수량으로 다시 주문해 주세요."
            ),
        }

    # =====================================================
    # 8) 결제수단 변경
    # =====================================================

    if (
    request.intent == "cs"
    and request.cs_category == "order_payment"
    and request.sub_intent == "payment_method_change"
    ):

        result = judge_payment_method_change()

        response = build_payment_method_change_response(result)

        return {
            "route": "payment_method_change",
            "request": request.model_dump(),
            "result": result,
            "response": response,
        }


    # -----------------------------------------------------
    # 8) 주문/결제 관련 문의이지만 세부 유형이 불명확한 경우
    #    (예: "주문내역", "주문" 등) -> 대화를 끊지 않고
    #    구체적으로 무엇을 도와줄지 되물어 이어간다.
    # -----------------------------------------------------

    if (
        request.intent == "cs"
        and request.cs_category == "order_payment"
    ):
        return {
            "route": "order_payment_clarification",
            "request": request.model_dump(),
            "result": None,
            "response": (
                "주문/결제 관련 문의로 확인됩니다. 다음 중 어떤 도움이 필요하신가요?\n\n"
                "- 주문 확인\n"
                "- 결제 확인\n"
                "- 주문 취소\n"
                "- 배송지 변경\n"
                "- 결제 수단 변경"
            ),
        }

    # -----------------------------------------------------
    # 9) 아직 구현하지 않은 기능
    # -----------------------------------------------------

    return {
        "route": "not_implemented",
        "request": request.model_dump(),
        "result": None,
        "response": "아직 지원하지 않는 문의입니다.",
    }
