import unittest
from unittest.mock import patch

from tools import hybrid_search


class HybridSearchCacheTests(unittest.TestCase):
    @patch("tools.hybrid_search.client.mget")
    def test_only_final_products_fetch_heavy_review_fields(self, mget):
        mget.return_value = {"docs": [{
            "_id": "p1",
            "found": True,
            "_source": {"positive_review_evidence": [{"text": "Great fit."}]},
        }]}
        products = hybrid_search.hydrate_products([
            {"product_id": "p1", "title": "Shoe", "_needs_hydration": True}
        ])
        self.assertEqual(products[0]["positive_review_evidence"][0]["text"], "Great fit.")
        self.assertFalse(products[0]["_needs_hydration"])
        self.assertEqual(mget.call_args.kwargs["body"]["ids"], ["p1"])

    def tearDown(self):
        hybrid_search._embed_query.cache_clear()

    def test_repeated_query_reuses_embedding(self):
        hybrid_search._embed_query.cache_clear()
        with patch(
            "tools.hybrid_search.ollama.embed",
            return_value={"embeddings": [[0.1, 0.2, 0.3]]},
        ) as embed:
            first = hybrid_search._embed_query("same query")
            second = hybrid_search._embed_query("same query")

        self.assertEqual(first, second)
        self.assertEqual(embed.call_count, 1)
        self.assertEqual(embed.call_args.kwargs["keep_alive"], hybrid_search.EMBEDDING_KEEP_ALIVE)

    def test_visual_query_uses_hard_constraints_only(self):
        query = hybrid_search._visual_query("Shoes", "Men", "Red", "Sneakers")
        self.assertIn("red", query)
        self.assertIn("men's", query)
        self.assertIn("sneakers", query)

    @patch("tools.hybrid_search.client.search")
    def test_keyword_preview_is_emitted_before_search_returns(self, search):
        search.return_value = {"hits": {"hits": [{
            "_id": "p1",
            "_source": {
                "title": "Running Sneakers", "category": "Shoes",
                "average_rating": 4.5,
            },
        }]}}
        previews = []
        with hybrid_search.retrieval_preview(previews.append):
            products = hybrid_search.hybrid_search(
                "running sneakers", size=1, category="Shoes",
                retrieval_mode="keyword", min_rating=4.0,
            )
        self.assertEqual(previews[0][0]["product_id"], "p1")
        self.assertEqual(products[0]["product_id"], "p1")

    @patch("tools.hybrid_search.evaluate_candidate", return_value={"accepted": True})
    @patch("tools.hybrid_search.embed_visual_query", return_value=[0.4, 0.5, 0.6])
    @patch("tools.hybrid_search._embed_query", return_value=(0.1, 0.2, 0.3))
    @patch("tools.hybrid_search.client.search")
    def test_image_hit_can_supply_visible_color_match(
        self, search, _text_embedding, _image_embedding, _evaluate_candidate
    ):
        empty = {"hits": {"hits": []}}
        image_hit = {
            "hits": {
                "hits": [{
                    "_id": "visual-red",
                    "_source": {
                        "product_id": "visual-red",
                        "title": "Men's Running Sneakers",
                        "category": "Shoes",
                        "audience": "Men",
                        "color": None,
                        "image_url": "https://example/image.jpg",
                    },
                }]
            }
        }
        search.side_effect = [empty, empty, image_hit]
        products = hybrid_search.hybrid_search(
            "men red sneakers",
            size=1,
            category="Shoes",
            audience="Men",
            required_color="Red",
            product_kind="Sneakers",
        )
        self.assertEqual(products[0]["product_id"], "visual-red")
        self.assertTrue(products[0]["visual_color_match"])
        self.assertEqual(search.call_count, 3)

    @patch("tools.hybrid_search.evaluate_candidate", return_value={"accepted": True})
    @patch("tools.hybrid_search.embed_visual_query", return_value=[0.4, 0.5, 0.6])
    @patch("tools.hybrid_search._embed_query", return_value=(0.1, 0.2, 0.3))
    @patch("tools.hybrid_search.client.search")
    def test_explicit_catalog_color_overrides_visual_false_positive(
        self, search, _text_embedding, _image_embedding, _evaluate_candidate
    ):
        empty = {"hits": {"hits": []}}
        image_hit = {"hits": {"hits": [{"_id": "gray", "_source": {
            "product_id": "gray", "title": "Granite Gray Sneakers", "category": "Shoes",
            "audience": "Men", "color": "Gray", "image_url": "https://example/image.jpg",
        }}]}}
        search.side_effect = [empty, empty, image_hit]
        products = hybrid_search.hybrid_search(
            "yellow sneakers", size=1, category="Shoes", required_color="Yellow"
        )
        self.assertEqual(products, [])

    @patch("tools.hybrid_search.embed_visual_query", return_value=[0.4, 0.5, 0.6])
    @patch("tools.hybrid_search._embed_query", return_value=(0.1, 0.2, 0.3))
    @patch("tools.hybrid_search.client.search")
    def test_metadata_free_color_requires_core_visual_rank(self, search, _text, _image):
        empty = {"hits": {"hits": []}}
        visual_hits = [
            {"_id": f"other-{index}", "_source": {
                "product_id": f"other-{index}", "title": "Running Sneakers",
                "category": "Shoes", "image_url": f"https://example/{index}.jpg",
            }} for index in range(10)
        ]
        visual_hits.append({"_id": "late", "_source": {
            "product_id": "late", "title": "Running Sneakers",
            "category": "Shoes", "image_url": "https://example/late.jpg",
        }})
        search.side_effect = [empty, empty, {"hits": {"hits": visual_hits}}]
        products = hybrid_search.hybrid_search(
            "yellow sneakers", size=1, category="Shoes",
            required_color="Yellow", product_kind="Sneakers",
        )
        self.assertNotIn("late", [product["product_id"] for product in products])


if __name__ == "__main__":
    unittest.main()
