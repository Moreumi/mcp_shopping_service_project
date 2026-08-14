import unittest
from unittest.mock import Mock, patch

from langchain_core.messages import HumanMessage, SystemMessage

from backend.cs.llm_service import generate_customer_answer


class CustomerServiceLlmTests(unittest.TestCase):
    @patch("backend.cs.llm_service._client")
    def test_only_schema_validated_answer_is_returned(self, client):
        client.chat.return_value = {
            "message": {"content": '{"answer":"주문은 완료됐지만 결제 상태는 추가 확인이 필요합니다."}'},
        }
        result = generate_customer_answer([
            SystemMessage(content="Use supplied facts."),
            HumanMessage(content="order 20020"),
        ])
        self.assertEqual(result, "주문은 완료됐지만 결제 상태는 추가 확인이 필요합니다.")
        self.assertFalse(client.chat.call_args.kwargs["think"])
        self.assertIn("format", client.chat.call_args.kwargs)

    @patch("backend.cs.llm_service._client")
    def test_non_korean_answer_is_rejected(self, client):
        client.chat.return_value = {"message": {"content": '{"answer":"Let us analyze this."}'}}
        with self.assertRaises(ValueError):
            generate_customer_answer([HumanMessage(content="order 20020")])


if __name__ == "__main__":
    unittest.main()
