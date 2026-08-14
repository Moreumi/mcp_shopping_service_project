import unittest
from unittest.mock import patch

from backend.query_understanding import SearchIntent, compile_search_intent


def _ollama_response(intent: SearchIntent):
    return {"message": {"content": intent.model_dump_json()}}


class QueryUnderstandingTests(unittest.TestCase):
    def tearDown(self):
        compile_search_intent.cache_clear()

    @patch("backend.query_understanding._client")
    def test_known_product_kind_skips_llm(self, client):
        intent = compile_search_intent("men black sneakers")
        client.chat.assert_not_called()
        self.assertEqual(intent.category, "Shoes")
        self.assertEqual(intent.audience, "Men")
        self.assertEqual(intent.color, "Black")

    @patch("backend.query_understanding._client")
    def test_validated_free_form_product_plan(self, client):
        client.chat.return_value = _ollama_response(SearchIntent(
            semantic_query="soccer football jersey uniform",
            visual_query="a soccer football jersey uniform shirt",
            product_terms=["soccer", "football", "jersey", "uniform"],
            product_phrases=["soccer jersey", "soccer uniform"],
            category="Clothing",
        ))
        intent = compile_search_intent("축구 유니폼 추천")
        self.assertEqual(intent.category, "Clothing")
        self.assertIn("jersey", intent.product_terms)
        self.assertEqual(client.chat.call_args.kwargs["model"], "qwen3:4b")
        self.assertIn("format", client.chat.call_args.kwargs)

    @patch("backend.query_understanding._client")
    def test_failure_uses_safe_existing_parser(self, client):
        client.chat.side_effect = RuntimeError("offline")
        intent = compile_search_intent("검은 여성 원피스 추천")
        self.assertEqual(intent.category, "Clothing")
        self.assertEqual(intent.audience, "Women")
        self.assertEqual(intent.color, "Black")

    @patch("backend.query_understanding._client")
    def test_placeholder_plan_is_rejected(self, client):
        client.chat.return_value = _ollama_response(SearchIntent(
            semantic_query="string", visual_query="string", product_terms=["string"],
            category="Jewelry", audience="Women", color="string",
        ))
        intent = compile_search_intent("여성 팔찌 보여줘")
        self.assertEqual(intent.category, "Jewelry")
        self.assertEqual(intent.audience, "Women")
        self.assertIn("bracelet", intent.semantic_query)

    @patch("backend.query_understanding._client")
    def test_explicit_category_overrides_model_inference(self, client):
        client.chat.return_value = _ollama_response(SearchIntent(
            semantic_query="men wallet", visual_query="men wallet",
            product_terms=["wallet"], product_phrases=["wallet"],
            category="Accessories", audience="Men",
        ))
        intent = compile_search_intent("남성 지갑 보여줘")
        self.assertEqual(intent.category, "Bags")

    @patch("backend.query_understanding._client")
    def test_explicit_brand_overrides_model_inference(self, client):
        client.chat.return_value = _ollama_response(SearchIntent(
            semantic_query="bag", visual_query="bag", product_terms=["bag"],
            category="Bags",
        ))
        intent = compile_search_intent("나이키 가방 보여줘")
        self.assertEqual(intent.brand, "nike")


if __name__ == "__main__":
    unittest.main()
