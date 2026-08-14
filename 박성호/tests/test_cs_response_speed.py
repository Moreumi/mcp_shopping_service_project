import unittest
from unittest.mock import patch

from backend.cs.response_service import generate_cs_response


class CustomerServiceResponseSpeedTests(unittest.TestCase):
    @patch("backend.cs.response_service.generate_customer_answer")
    def test_fact_summary_does_not_call_llm_writer(self, writer):
        answer = generate_cs_response(
            user_input="결제수단 알려줘",
            sub_intent="payment_confirmation",
            response_mode="fact_summary",
            result={
                "result_type": "success",
                "order_id": 20014,
                "payment_status": "payment_completed",
                "payment_method": "card",
                "payment_amount": 88000,
                "payment_date": "2026-08-10",
            },
            policy_context="",
        )

        writer.assert_not_called()
        self.assertIn("- 결제수단: 카드", answer)
        self.assertIn("- 결제금액: 88,000원", answer)


if __name__ == "__main__":
    unittest.main()
