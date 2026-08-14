import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.result = {
            "answer": "추천 결과입니다.",
            "products": [{"product_id": "p1", "title": "Shoe"}],
            "orders": [],
            "suggestions": ["비슷한 상품 보여줘"],
            "service_status": "ok",
            "response_mode": "search",
        }

    def test_structured_chat_response(self):
        with patch("backend.api.invoke_shopping_graph_result", return_value=self.result):
            response = self.client.post(
                "/chat",
                json={
                    "message": "신발 추천",
                    "user_id": "user_001",
                    "thread_id": "thread-1",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.result)

    def test_sse_stream_separates_status_and_result(self):
        with patch("backend.api.invoke_shopping_graph_result", return_value=self.result):
            response = self.client.post(
                "/chat/stream",
                json={"message": "신발 추천", "thread_id": "thread-1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: status", response.text)
        self.assertIn("event: answer_delta", response.text)
        self.assertIn("event: result", response.text)
        self.assertIn('"product_id": "p1"', response.text)
        self.assertIn("event: done", response.text)

    def test_customer_service_sse_streams_answer(self):
        cs_result = {"response": "결제수단은 카드입니다.", "route": "payment_confirmation"}
        with patch("backend.api._execute_cs_request", return_value=cs_result):
            response = self.client.post(
                "/cs/chat/stream",
                json={"message": "결제수단 알려줘", "customer_id": 1, "thread_id": "cs-sse"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
        self.assertIn("event: status", response.text)
        self.assertIn("event: answer_delta", response.text)
        self.assertIn("결제수단은", response.text)
        self.assertIn("event: result", response.text)
        self.assertIn("event: done", response.text)

    def test_internal_error_is_hidden(self):
        with patch("backend.api.invoke_shopping_graph_result", side_effect=RuntimeError("secret endpoint")):
            response = self.client.post(
                "/chat",
                json={"message": "신발 추천", "user_id": "user_001"},
            )
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret endpoint", response.text)

    def test_sse_emits_product_cards_before_answer_tokens(self):
        def invoke(*args, **kwargs):
            kwargs["event_callback"]("products", {"products": self.result["products"]})
            kwargs["answer_callback"]("first answer chunk")
            return self.result

        with patch("backend.api.invoke_shopping_graph_result", side_effect=invoke):
            response = self.client.post(
                "/chat/stream",
                json={"message": "shoe recommendation", "thread_id": "thread-card-first"},
            )

        self.assertLess(
            response.text.index("event: products"),
            response.text.index("event: answer_delta"),
        )

    def test_unknown_demo_user_is_rejected(self):
        with patch("backend.api.DEMO_USER_IDS", {"user_001"}):
            response = self.client.post(
                "/chat",
                json={"message": "신발 추천", "user_id": "unknown"},
            )
        self.assertEqual(response.status_code, 403)

    def test_isolated_guest_user_is_allowed(self):
        with patch("backend.api.DEMO_USER_IDS", {"user_001"}), patch(
            "backend.api.invoke_shopping_graph_result", return_value=self.result
        ):
            response = self.client.post(
                "/chat", json={"message": "신발 추천", "user_id": "demo_guest-2"}
            )
        self.assertEqual(response.status_code, 200)

    def test_invalid_user_id_is_rejected_by_schema(self):
        response = self.client.post(
            "/chat", json={"message": "신발 추천", "user_id": "../../bad"}
        )
        self.assertEqual(response.status_code, 422)

    def test_personalized_recommendations_return_structured_products(self):
        result = {
            "query": "Men's black straight fit cotton pants",
            "priorities": ["color", "fit"],
            "products": [{"asin": "B000TEST", "title": "Black cotton pants", "score": 91.2}],
        }
        payload = {
            "answers": {
                "gender": "남자",
                "color": "블랙 / 차콜 / 다크톤",
                "fit": "스트레이트 (일자)",
                "material": "면 (코튼 / 치노)",
                "mood": "캐주얼 / 데일리",
                "use": "일상 / 데일리",
                "budget": "3~5만원대 ($22~$37)",
                "season": "봄·가을용 (기본)",
            },
            "priorities": ["color", "fit"],
            "user_id": "user_001",
        }
        with patch("backend.api.recommend_live_amazon", return_value=result) as recommend:
            response = self.client.post("/personalized/recommendations", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)
        recommend.assert_called_once_with("bottoms", payload["answers"], payload["priorities"])

    def test_personalized_recommendations_report_missing_api_key(self):
        payload = {
            "answers": {},
            "priorities": [],
            "user_id": "user_001",
        }
        with patch(
            "backend.api.recommend_live_amazon",
            side_effect=RuntimeError("RAPIDAPI_KEY is not configured"),
        ):
            response = self.client.post("/personalized/recommendations", json=payload)

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("not configured", response.text)


if __name__ == "__main__":
    unittest.main()
