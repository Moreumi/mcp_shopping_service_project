import unittest

from backend.cs.order_payment_service import (
    check_order_cancel_eligibility,
    check_payment_completion,
    generate_payment_response,
)
from backend.cs.orchestrator import build_order_cancel_pre_action_response


def _orders():
    return [
        {
            "customer_id": 1, "order_id": 1000 + day,
            "product_name": f"Product {day}", "order_date": f"2026-08-{day:02d}",
            "total_price": day * 1000, "order_status": "order_completed",
            "delivery_status": "preparing", "delivery_address": "Seoul",
        }
        for day in (1, 5, 3, 9, 7)
    ]


class RecentOrderSelectionTests(unittest.TestCase):
    def test_cancel_choices_are_latest_three_with_product_names(self):
        payments = [{"order_id": 1000 + day, "payment_method": "card"} for day in (1, 5, 3, 9, 7)]
        result = check_order_cancel_eligibility(_orders(), customer_id=1, payments=payments)
        self.assertEqual([row["order_id"] for row in result["candidate_orders"]], [1009, 1007, 1005])
        self.assertEqual(result["candidate_orders"][0]["product_name"], "Product 9")
        answer = build_order_cancel_pre_action_response(result)
        self.assertEqual(answer.count("- 주문번호:"), 3)
        self.assertIn("- 주문번호: 1009\n- 상품명: Product 9", answer)
        self.assertIn("- 결제수단: 카드", answer)
        self.assertTrue(answer.endswith("무엇을 도와드릴까요?"))

    def test_payment_choices_are_latest_three_and_compact(self):
        payments = [{"order_id": 1000 + day, "payment_method": "bank_transfer"} for day in (1, 5, 3, 9, 7)]
        result = check_payment_completion(_orders(), payments=payments, customer_id=1)
        self.assertEqual(len(result["candidate_orders"]), 3)
        answer = generate_payment_response(result)
        self.assertIn("최근 결제 내역 3건", answer)
        self.assertIn("Product 9", answer)
        self.assertIn("- 주문번호: 1007", answer)
        self.assertIn("- 결제수단: 계좌이체", answer)
        self.assertTrue(answer.endswith("무엇을 도와드릴까요?"))
        self.assertNotIn("주문번호 1001", answer)


if __name__ == "__main__":
    unittest.main()
