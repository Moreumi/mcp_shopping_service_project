import unittest
from unittest.mock import patch

from backend.reranker import confidence_filter, lexical_relevance, rerank_products


class RerankerTests(unittest.TestCase):
    def test_specific_product_beats_unrelated_item(self):
        products = [
            {"product_id": "bad", "title": "Trading Card Collector Pack"},
            {"product_id": "good", "title": "Men's Black Running Sneakers"},
        ]
        ranked = rerank_products(
            "men black sneakers running shoes",
            products,
            product_terms=["men", "black", "sneakers", "running"],
            product_phrases=["running sneakers", "running shoes"],
        )
        self.assertEqual(ranked[0]["product_id"], "good")
        self.assertGreater(ranked[0]["relevance_score"], ranked[1]["relevance_score"])

    def test_confidence_gate_does_not_fill_with_weak_items(self):
        products = [
            {"product_id": "good", "relevance_score": 0.8},
            {"product_id": "weak", "relevance_score": 0.1},
        ]
        self.assertEqual([item["product_id"] for item in confidence_filter(products)], ["good"])

    @patch("backend.reranker.ENABLED", True)
    @patch("backend.reranker._model_scores", side_effect=RuntimeError("model missing"))
    def test_missing_model_falls_back_safely(self, _scores):
        result = rerank_products("black sneakers", [{"product_id": "p1", "title": "Black Sneakers"}])
        self.assertEqual(result[0]["product_id"], "p1")
        self.assertGreater(lexical_relevance("black sneakers", result[0]), 0)


if __name__ == "__main__":
    unittest.main()
