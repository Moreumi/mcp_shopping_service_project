import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import conversation_store


class ConversationStoreTests(unittest.TestCase):
    def test_round_trip_survives_memory_reset(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            conversation_store, "DB_PATH", Path(directory) / "conversations.sqlite3"
        ):
            conversation_store._initialized = False
            state = {
                "products": [{"product_id": "B012345678", "title": "Shoe"}],
                "history": [{"role": "user", "content": "신발 추천"}],
            }
            conversation_store.save_conversation("user_001", "thread-1", state)
            conversation_store._initialized = False
            restored = conversation_store.load_conversation("user_001", "thread-1")

        conversation_store._initialized = False
        self.assertEqual(restored["products"][0]["product_id"], "B012345678")
        self.assertEqual(restored["history"][0]["role"], "user")


if __name__ == "__main__":
    unittest.main()
