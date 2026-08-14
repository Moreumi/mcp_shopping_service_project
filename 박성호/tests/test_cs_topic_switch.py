import unittest
from unittest.mock import patch

from backend.cs.orchestrator import _reset_if_new_topic, route_request
from backend.cs.schemas import UserRequest


class PendingTopicSwitchTests(unittest.TestCase):
    @patch("backend.cs.orchestrator.generate_cs_response", return_value="결제수단: 카드")
    @patch("backend.cs.orchestrator.classification_chain")
    def test_payment_method_question_interrupts_address_collection(
        self, classifier, _response
    ):
        classifier.invoke.return_value = UserRequest(
            intent="cs",
            cs_category="order_payment",
            # Simulate stale model output from the address workflow.
            sub_intent="delivery_address_change",
        )
        orders = [{
            "customer_id": 1,
            "order_id": 20014,
            "product_name": "Backpack",
            "order_status": "order_completed",
            "order_date": "2026-08-10",
            "total_price": 88000,
            "delivery_status": "preparing",
            "delivery_address": "서울시 강남구 기존로 1",
        }]
        payments = [{
            "order_id": 20014,
            "payment_id": 301,
            "payment_status": "payment_completed",
            "payment_method": "card",
            "payment_amount": 88000,
            "payment_date": "2026-08-10",
        }]
        state = {
            "pending_action": "collect_delivery_address",
            "candidate_orders": [],
            "selected_order_id": 20014,
            "last_order_id": 20014,
            "recent_candidate_orders": [],
            "recent_list_intent": None,
            "pending_data": {},
        }

        result = route_request(
            "결제수단 알려줘", 1, orders, state, payments=payments, refunds=[]
        )

        self.assertEqual(result["route"], "payment_confirmation")
        self.assertEqual(result["result"]["order_id"], 20014)
        self.assertEqual(result["result"]["payment_method"], "card")
        self.assertNotEqual(state["pending_action"], "confirm_delivery_address_change")

    @patch("backend.cs.orchestrator.generate_cs_response", return_value="주문 확인 완료")
    @patch("backend.cs.orchestrator.classification_chain")
    def test_ordinal_followup_reuses_recent_list_after_pending_state_clears(
        self, classifier, _response
    ):
        orders = [
            {
                "customer_id": 1,
                "order_id": 20020,
                "product_name": "Bag",
                "order_status": "order_completed",
                "order_date": "2026-08-12",
                "total_price": 25000,
                "delivery_status": "preparing",
            },
            {
                "customer_id": 1,
                "order_id": 20017,
                "product_name": "Sunglasses",
                "order_status": "order_completed",
                "order_date": "2026-08-11",
                "total_price": 54000,
                "delivery_status": "preparing",
            },
        ]
        state = {
            "pending_action": None,
            "candidate_orders": [],
            "selected_order_id": None,
            "last_order_id": 20017,
            "recent_candidate_orders": orders,
            "recent_list_intent": "order_confirmation",
            "pending_data": {},
        }

        result = route_request("첫번째", 1, orders, state, payments=[], refunds=[])

        self.assertEqual(result["route"], "order_confirmation")
        self.assertEqual(result["result"]["order_id"], 20020)
        classifier.invoke.assert_not_called()

    @patch("backend.cs.orchestrator.classification_chain")
    def test_delivery_address_request_interrupts_refund_account_collection(
        self, classifier
    ):
        classifier.invoke.return_value = UserRequest(
            intent="cs",
            cs_category="order_payment",
            # Simulate the local model copying the stale cancellation intent.
            sub_intent="order_cancel",
        )
        state = {
            "pending_action": "collect_refund_account",
            "candidate_orders": [],
            "selected_order_id": 20017,
            "last_order_id": 20017,
            "pending_data": {},
        }

        switched = _reset_if_new_topic("배송지 변경하고 싶어", state)

        self.assertTrue(switched)
        self.assertIsNone(state["pending_action"])
        self.assertIsNone(state["selected_order_id"])
        self.assertEqual(state["last_order_id"], 20017)
        self.assertEqual(
            state["pending_data"]["topic_switch_request"]["sub_intent"],
            "delivery_address_change",
        )
        classification_input = classifier.invoke.call_args.args[0]
        self.assertIn("활성 주문번호: 20017", classification_input["conversation_context"])

    @patch("backend.cs.orchestrator.classification_chain")
    def test_unrecognized_refund_input_keeps_refund_account_collection(
        self, classifier
    ):
        classifier.invoke.return_value = UserRequest(
            intent="other",
            cs_category=None,
            sub_intent=None,
        )
        state = {
            "pending_action": "collect_refund_account",
            "candidate_orders": [],
            "selected_order_id": 20017,
            "last_order_id": 20017,
            "pending_data": {},
        }

        switched = _reset_if_new_topic("박성호 01025895573", state)

        self.assertFalse(switched)
        self.assertEqual(state["pending_action"], "collect_refund_account")
        self.assertEqual(state["selected_order_id"], 20017)


if __name__ == "__main__":
    unittest.main()
