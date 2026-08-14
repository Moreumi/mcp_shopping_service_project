import unittest
from unittest.mock import patch

from tools.siglip_vision import evaluate_candidate, rerank_candidates


class SiglipVisionTests(unittest.TestCase):
    @patch("tools.siglip_vision.score_image")
    def test_rejects_accessory_and_wrong_color(self, score_image):
        score_image.return_value = {
            "a photo of a sneaker": 0.1,
            "a photo of an athletic shoe": 0.1,
            "a photo of a shoe care kit": 0.8,
            "a photo of shoe accessories": 0.7,
            "a photo of socks": 0.0,
            "a photo of product packaging without shoes": 0.6,
            "a product whose main visible color is red": 0.2,
            "a product whose main visible color is black": 0.3,
            "a product whose main visible color is white": 0.4,
            "a product whose main visible color is blue": 0.1,
            "a product whose main visible color is brown": 0.1,
            "a product whose main visible color is green": 0.1,
            "a product whose main visible color is pink": 0.1,
            "a product whose main visible color is gray": 0.5,
            "a product whose main visible color is beige": 0.1,
            "a product whose main visible color is navy blue": 0.1,
        }
        result = evaluate_candidate({"image_url": "https://example/image.jpg"}, "Sneakers", "Red")
        self.assertFalse(result["accepted"])
        self.assertIn("wrong_product_kind", result["reason"])
        self.assertIn("wrong_visible_color", result["reason"])

    @patch("tools.siglip_vision.evaluate_candidate")
    def test_rerank_only_returns_accepted_catalog_products(self, evaluate):
        evaluate.side_effect = [
            {"accepted": False, "reason": "wrong", "vision_score": -0.2},
            {"accepted": True, "reason": "matched", "vision_score": 0.3},
        ]
        products = [{"product_id": "bad", "image_url": "a"}, {"product_id": "good", "image_url": "b"}]
        accepted, audit = rerank_candidates(products, requested_kind="Sneakers", required_color="Red")
        self.assertEqual([item["product_id"] for item in accepted], ["good"])
        self.assertEqual(len(audit), 2)


if __name__ == "__main__":
    unittest.main()
