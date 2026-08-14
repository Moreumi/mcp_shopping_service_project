"""End-to-end smoke test for the configured shopping workflow."""

import json
from uuid import uuid4

from backend.agent_graph import invoke_shopping_graph_result


if __name__ == "__main__":
    result = invoke_shopping_graph_result(
        "리뷰가 좋은 검은 여성 신발 추천해줘",
        user_id="user_001",
        thread_id=str(uuid4()),
    )
    print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
