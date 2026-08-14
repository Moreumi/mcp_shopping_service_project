import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_amazon_fashion import build_catalog, clean_metadata, parse_price


class AmazonFashionTests(unittest.TestCase):
    def test_metadata_normalization(self):
        product = clean_metadata(
            {
                "parent_asin": "p1",
                "title": "Walking Shoe",
                "store": "Example",
                "categories": ["Women", "Shoes"],
                "features": ["Cushioned footbed"],
                "description": ["Daily shoe"],
                "price": "$39.99",
                "images": [{"large": "https://example/image.jpg"}],
                "details": "{'Color': 'Black', 'Fabric type': 'Cotton'}",
            },
            {"average_rating": 4.5, "review_count": 10, "verified_review_count": 8},
        )
        self.assertEqual(product["product_id"], "p1")
        self.assertEqual(product["price"], 39.99)
        self.assertEqual(product["color"], "Black")
        self.assertEqual(product["category"], "Amazon Fashion > Shoes")
        self.assertEqual(product["image_url"], "https://example/image.jpg")

    def test_streaming_build_selects_reviewed_products(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reviews = root / "reviews.jsonl"
            metadata = root / "meta.jsonl"
            output = root / "products.jsonl"
            review_rows = []
            for product_id, count in (("popular", 4), ("second", 3), ("low", 1)):
                for index in range(count):
                    review_rows.append({
                        "parent_asin": product_id,
                        "rating": 5 if index % 2 == 0 else 1,
                        "verified_purchase": True,
                        "helpful_vote": index,
                        "title": "Review",
                        "text": f"Evidence {product_id} {index}",
                    })
            reviews.write_text("\n".join(json.dumps(row) for row in review_rows), encoding="utf-8")
            metadata.write_text("\n".join(json.dumps({
                "parent_asin": product_id,
                "title": product_id,
                "categories": ["Fashion"],
            }) for product_id in ("popular", "second", "low")), encoding="utf-8")

            result = build_catalog(reviews, metadata, output, limit=2, candidate_limit=3, min_reviews=2)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(result["products"], 2)
            self.assertEqual([row["product_id"] for row in rows], ["popular", "second"])
            self.assertTrue(rows[0]["positive_review_evidence"])

    def test_price_missing_is_not_invented(self):
        self.assertIsNone(parse_price(None))
        self.assertIsNone(parse_price("Unavailable"))


if __name__ == "__main__":
    unittest.main()
