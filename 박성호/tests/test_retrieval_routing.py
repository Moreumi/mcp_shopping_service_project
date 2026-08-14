import unittest
from unittest.mock import patch

from backend.agent_graph import _retrieval_mode
from tools import hybrid_search


class RetrievalRoutingTests(unittest.TestCase):
    def test_mode_policy(self):
        self.assertEqual(_retrieval_mode("Nike Air Max", None, "Nike"), "keyword")
        self.assertEqual(_retrieval_mode("comfortable running shoes", None, None), "semantic")
        self.assertEqual(_retrieval_mode("red running shoes", "Red", None), "visual")

    @patch("tools.hybrid_search.client.search")
    @patch("tools.hybrid_search._embed_query")
    def test_keyword_mode_skips_all_embeddings(self, embed_query, search):
        search.return_value = {"hits": {"hits": []}}
        result = hybrid_search.hybrid_search("Nike Air Max", retrieval_mode="keyword")
        self.assertEqual(result, [])
        embed_query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
