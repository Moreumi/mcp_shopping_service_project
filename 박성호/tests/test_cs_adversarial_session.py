import unittest
from unittest.mock import patch

from backend.cs.orchestrator import route_request
from backend.cs.schemas import UserRequest


class AdversarialConversationTests(unittest.TestCase):
    def setUp(self):
        rows = [
            (20020, "Bag", "2026-08-12", 25000),
            (20017, "Sunglasses", "2026-08-11", 54000),
            (20014, "Backpack", "2026-08-10", 88000),
        ]
        self.orders = [{
            "customer_id": 1,
            "order_id": order_id,
            "product_name": name,
            "order_status": "order_completed",
            "order_date": date,
            "total_price": price,
            "delivery_status": "preparing_shipment",
            "delivery_address": f"서울시 테스트로 {index}",
        } for index, (order_id, name, date, price) in enumerate(rows, 1)]
        self.payments = [{
            "order_id": order_id,
            "payment_id": index,
            "payment_status": "payment_completed",
            "payment_method": "card",
            "payment_amount": price,
            "payment_date": date,
        } for index, (order_id, _name, date, price) in enumerate(rows, 1)]
        self.state = {
            "pending_action": None,
            "candidate_orders": [],
            "selected_order_id": None,
            "last_order_id": None,
            "recent_candidate_orders": [],
            "recent_list_intent": None,
            "history": [],
            "pending_data": {},
        }

    @patch("backend.cs.orchestrator.generate_cs_response", return_value="확인 완료")
    @patch("backend.cs.orchestrator.classification_chain")
    def test_twenty_turn_context_and_topic_switch_attacks(self, classifier, _writer):
        def classify(values):
            message = values["user_input"]
            sub_intent = "order_confirmation" if "최근 주문" in message else None
            return UserRequest(
                intent="cs" if sub_intent else "other",
                cs_category="order_payment" if sub_intent else None,
                sub_intent=sub_intent,
            )

        classifier.invoke.side_effect = classify
        turns = [
            ("주문 확인", "order_confirmation"),
            ("두번째", "order_confirmation"),
            ("결제수단 알려줘", "payment_confirmation"),
            ("배송지 변경", "delivery_address_change"),
            ("결제내역 알려줘", "payment_confirmation"),
            ("배송지 바꿔줘", "delivery_address_change"),
            ("서울시 강남구 테헤란로 123", "delivery_address_change"),
            ("아니오", "delivery_address_change"),
            ("그 주문 취소하고 싶어", "order_cancel"),
            ("아니오", "order_cancel"),
            ("최근 주문 보여줘", "order_confirmation"),
            ("마지막", "order_confirmation"),
            ("첫번째", "order_confirmation"),
            ("99999 주문 확인", "order_confirmation"),
            ("그럼 두번째", "order_confirmation"),
            ("결제수단 바꿔줘", "payment_method_change"),
            ("배송지 변경해줘", "delivery_address_change"),
            ("주문 취소해줘", "order_cancel"),
            ("배송지 변경해줘", "delivery_address_change"),
            ("국민은행 / 1234567890 / 홍길동", "delivery_address_change"),
        ]

        outputs = []
        for message, expected_route in turns:
            output = route_request(
                message, 1, self.orders, self.state,
                payments=self.payments, refunds=[],
            )
            outputs.append(output)
            self.assertEqual(output["route"], expected_route, message)
            self.state["history"].extend([
                {"role": "user", "content": message},
                {"role": "assistant", "content": output["response"]},
            ])
            self.state["history"] = self.state["history"][-8:]

        self.assertEqual(outputs[1]["result"]["order_id"], 20017)
        self.assertEqual(outputs[12]["result"]["order_id"], 20020)
        self.assertEqual(outputs[14]["result"]["order_id"], 20017)
        self.assertEqual(outputs[13]["result"]["result_type"], "not_found")
        self.assertEqual(self.state["pending_action"], "collect_delivery_address")
        self.assertNotIn("new_delivery_address", self.state["pending_data"])


if __name__ == "__main__":
    unittest.main()
