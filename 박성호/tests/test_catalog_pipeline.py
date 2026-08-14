import unittest

from scripts.create_catalog_index import index_body
from scripts.embed_catalog import make_product_text
from scripts.upload_catalog import actions


class CatalogPipelineTests(unittest.TestCase):
    def test_demo_scenario_fixture_covers_core_flow(self):
        import json
        from pathlib import Path

        scenarios = json.loads(Path("tests/fixtures/demo_scenarios.json").read_text(encoding="utf-8"))
        ids = {scenario["id"] for scenario in scenarios}
        self.assertTrue({"women_black_shoes", "followup_compare", "recent_orders"}.issubset(ids))

    def test_index_is_single_node_friendly(self):
        settings = index_body()["settings"]["index"]
        self.assertEqual(settings["number_of_shards"], 1)
        self.assertEqual(settings["number_of_replicas"], 0)
        self.assertEqual(
            index_body()["mappings"]["properties"]["embedding"]["dimension"],
            768,
        )

    def test_embedding_text_contains_comfort_evidence_fields(self):
        text = make_product_text(
            {
                "title": "Daily Shoe",
                "bullet_points": ["Cushioned footbed"],
                "description": "Soft lining",
                "keywords": ["walking"],
            }
        )

        self.assertIn("Cushioned footbed", text)
        self.assertIn("Soft lining", text)
        self.assertIn("walking", text)

    def test_embedding_text_adds_korean_fashion_aliases(self):
        text = make_product_text(
            {
                "title": "Women's Daily Sneaker",
                "category": "Amazon Fashion > Shoes",
                "audience": "Women",
            }
        )
        self.assertIn("운동화", text)
        self.assertIn("여성", text)

    def test_upload_resume_skips_completed_lines(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "products.jsonl"
            path.write_text("\n".join(
                json.dumps({"product_id": f"p{number}"}) for number in range(3)
            ), encoding="utf-8")
            remaining = list(actions(path, "index", skip_lines=2))
        self.assertEqual([item["_id"] for item in remaining], ["p2"])


if __name__ == "__main__":
    unittest.main()
