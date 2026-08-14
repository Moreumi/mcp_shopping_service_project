import unittest
from unittest.mock import Mock

from scripts.translate_review_summaries import source_hash, translate_batch


class ReviewTranslationTests(unittest.TestCase):
    def test_source_hash_is_stable_and_content_sensitive(self):
        self.assertEqual(source_hash(["Positive: good"]), source_hash(["Positive: good"]))
        self.assertNotEqual(source_hash(["Positive: good"]), source_hash(["Caution: good"]))

    def test_translation_batch_preserves_product_count(self):
        client = Mock()
        client.chat.return_value = {
            "message": {"content": '{"translations":[["장점: 편안합니다."],["주의: 작게 나옵니다."]]}'},
        }
        rows = [("p1", ["Positive: comfortable"], "h1"), ("p2", ["Caution: runs small"], "h2")]
        result = translate_batch(client, rows, "qwen3:4b")
        self.assertEqual(len(result), 2)
        self.assertFalse(client.chat.call_args.kwargs["think"])

    def test_translation_batch_rejects_missing_rows(self):
        client = Mock()
        client.chat.return_value = {"message": {"content": '{"translations":[]}'}}
        with self.assertRaises(ValueError):
            translate_batch(client, [("p1", ["Positive: good"], "h1")], "qwen3:4b")

    def test_english_batch_output_is_retried_individually(self):
        client = Mock()
        client.chat.side_effect = [
            {"message": {"content": '{"translations":[["Positive: comfortable"]]}'}},
            {"message": {"content": '{"translation":["장점: 편안합니다."]}'}},
        ]
        result = translate_batch(client, [("p1", ["Positive: comfortable"], "h1")], "qwen3:4b")
        self.assertEqual(result, [["장점: 편안합니다."]])
        self.assertEqual(client.chat.call_count, 2)


if __name__ == "__main__":
    unittest.main()
