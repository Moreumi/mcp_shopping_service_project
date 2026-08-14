import unittest
from unittest.mock import patch

from backend.cs.orchestrator import route_request
from backend.cs.schemas import UserRequest


class ExplicitOrderTests(unittest.TestCase):
    @patch("backend.cs.orchestrator.classification_chain")
    @patch("backend.cs.orchestrator.generate_cs_response", return_value="주문 확인 완료")
    def test_explicit_order_number_overrides_missing_model_field(self, _response, classifier):
        classifier.invoke.return_value = UserRequest(
            intent="cs", cs_category="order_payment",
            sub_intent="order_confirmation", order_id=None,
        )
        orders = [{
            "customer_id": 1, "order_id": 20020,
            "product_name": "Messenger Bag", "order_status": "order_completed",
            "order_date": "2026-08-12", "total_price": 25000,
            "delivery_status": "preparing",
        }, {
            "customer_id": 1, "order_id": 20017,
            "product_name": "Sunglasses", "order_status": "order_completed",
            "order_date": "2026-08-11", "total_price": 54000,
            "delivery_status": "preparing",
        }]
        state = {"pending_action": None, "candidate_orders": [], "selected_order_id": None, "pending_data": {}}
        result = route_request("20020 주문 확인", 1, orders, state, payments=[], refunds=[])
        self.assertEqual(result["route"], "order_confirmation")
        self.assertEqual(result["result"]["order_id"], 20020)
        self.assertNotEqual(result["result"]["result_type"], "need_order_selection")

    @patch("backend.cs.orchestrator.generate_cs_response", return_value="주문 확인 완료")
    @patch("backend.cs.orchestrator.classification_chain")
    def test_selected_order_is_reused_by_followup_cancel(self, classifier, _response):
        classifier.invoke.side_effect = [
            UserRequest(intent="cs", cs_category="order_payment", sub_intent="order_confirmation"),
            UserRequest(intent="cs", cs_category="order_payment", sub_intent="order_cancel"),
        ]
        orders = [
            {"customer_id": 1, "order_id": order_id, "product_name": name,
             "order_status": "order_completed", "order_date": date, "total_price": price,
             "delivery_status": "preparing_shipment"}
            for order_id, name, date, price in [
                (20020, "Bag", "2026-08-12", 25000),
                (20017, "Sunglasses", "2026-08-11", 54000),
                (20014, "Backpack", "2026-08-10", 88000),
            ]
        ]
        state = {"pending_action": None, "candidate_orders": [], "selected_order_id": None,
                 "last_order_id": None, "pending_data": {}}
        first = route_request("주문 확인", 1, orders, state, payments=[], refunds=[])
        self.assertEqual(first["result"]["result_type"], "need_order_selection")
        selected = route_request("세번째", 1, orders, state, payments=[], refunds=[])
        self.assertEqual(selected["result"]["order_id"], 20014)
        self.assertEqual(state["last_order_id"], 20014)
        cancel = route_request("주문 취소하고 싶어", 1, orders, state, payments=[], refunds=[])
        self.assertEqual(cancel["result"]["order_id"], 20014)
        self.assertNotEqual(cancel["result"]["result_type"], "need_order_selection")
        self.assertIn("- 상품명: Backpack", cancel["response"])
        self.assertIn("예 / 아니오", cancel["response"])

    @patch("backend.cs.orchestrator.classification_chain")
    def test_explicit_list_request_does_not_reuse_active_order(self, classifier):
        classifier.invoke.return_value = UserRequest(
            intent="cs", cs_category="order_payment", sub_intent="order_confirmation",
            # Simulate Qwen copying the active order from conversation context.
            order_id=20020,
        )
        orders = [
            {"customer_id": 1, "order_id": 20020, "product_name": "Bag",
             "order_status": "order_completed", "order_date": "2026-08-12",
             "total_price": 25000, "delivery_status": "preparing"},
            {"customer_id": 1, "order_id": 20017, "product_name": "Glasses",
             "order_status": "order_completed", "order_date": "2026-08-11",
             "total_price": 54000, "delivery_status": "preparing"},
        ]
        state = {"pending_action": None, "candidate_orders": [], "selected_order_id": None,
                 "last_order_id": 20020, "pending_data": {}}
        result = route_request("다른 주문 목록 보여줘", 1, orders, state, payments=[], refunds=[])
        self.assertEqual(result["result"]["result_type"], "need_order_selection")

    @patch("backend.cs.orchestrator.classification_chain")
    def test_recent_order_history_forces_list_even_when_model_returns_active_order(
        self, classifier
    ):
        classifier.invoke.return_value = UserRequest(
            intent="cs", cs_category="order_payment",
            sub_intent="order_confirmation", order_id=20014,
        )
        orders = [
            {"customer_id": 1, "order_id": order_id, "product_name": name,
             "order_status": "order_completed", "order_date": date,
             "total_price": price, "delivery_status": "preparing"}
            for order_id, name, date, price in [
                (20020, "Bag", "2026-08-12", 25000),
                (20017, "Glasses", "2026-08-11", 54000),
                (20014, "Backpack", "2026-08-10", 88000),
            ]
        ]
        state = {
            "pending_action": None, "candidate_orders": [],
            "selected_order_id": None, "last_order_id": 20014,
            "recent_candidate_orders": [], "recent_list_intent": None,
            "pending_data": {},
        }

        result = route_request(
            "최근 주문내역", 1, orders, state, payments=[], refunds=[]
        )

        self.assertEqual(result["result"]["result_type"], "need_order_selection")
        self.assertEqual(
            [row["order_id"] for row in result["result"]["candidate_orders"]],
            [20020, 20017, 20014],
        )

    @patch("backend.cs.orchestrator.classification_chain")
    def test_bare_order_confirmation_means_recent_list(self, classifier):
        classifier.invoke.return_value = UserRequest(
            intent="cs", cs_category="order_payment",
            sub_intent="order_confirmation", order_id=20014,
        )
        orders = [
            {"customer_id": 1, "order_id": order_id, "product_name": str(order_id),
             "order_status": "order_completed", "order_date": date,
             "total_price": 1000, "delivery_status": "preparing"}
            for order_id, date in [(20020, "2026-08-12"), (20017, "2026-08-11"), (20014, "2026-08-10")]
        ]
        state = {"pending_action": None, "candidate_orders": [],
                 "selected_order_id": None, "last_order_id": 20014,
                 "recent_candidate_orders": [], "recent_list_intent": None,
                 "pending_data": {}}

        result = route_request("주문 확인", 1, orders, state, payments=[], refunds=[])

        self.assertEqual(result["result"]["result_type"], "need_order_selection")
        self.assertEqual(len(result["result"]["candidate_orders"]), 3)

    @patch("backend.cs.orchestrator.classification_chain")
    def test_quantity_change_uses_active_order_and_never_mutates_it(self, classifier):
        classifier.invoke.return_value = UserRequest(
            intent="cs", cs_category="order_payment", sub_intent="unknown"
        )
        order = {"customer_id": 1, "order_id": 20020, "product_name": "Bag",
                 "order_status": "order_completed", "order_date": "2026-08-12",
                 "total_price": 25000, "delivery_status": "preparing", "quantity": 1}
        state = {"pending_action": None, "candidate_orders": [],
                 "selected_order_id": None, "last_order_id": 20020,
                 "recent_candidate_orders": [], "recent_list_intent": None,
                 "pending_data": {}}

        result = route_request("주문 수량 변경", 1, [order], state, payments=[], refunds=[])

        self.assertEqual(result["route"], "order_change")
        self.assertEqual(result["result"]["order_id"], 20020)
        self.assertEqual(order["quantity"], 1)
        self.assertIn("직접 변경할 수 없습니다", result["response"])


if __name__ == "__main__":
    unittest.main()
