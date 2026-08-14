"""Verify and warm every dependency required by the live demo."""

from __future__ import annotations

import json
import sys
import time

from tools.customer_context import get_orders, get_user_profile
from tools.hybrid_search import embedding_model_status, warm_embedding_model
from backend.query_understanding import warm_query_model
from backend.reranker import warm_reranker
from tools.search_products import INDEX_NAME, client


def run(user_id: str = "user_001") -> dict:
    started = time.perf_counter()
    warm_embedding_model()
    warm_query_model()
    warm_reranker()
    embedding = embedding_model_status()

    opensearch = {"ready": False, "index": INDEX_NAME}
    try:
        cluster = client.cluster.health(request_timeout=5)
        count = client.count(index=INDEX_NAME, request_timeout=5)["count"]
        opensearch.update({
            "ready": cluster.get("status") in {"green", "yellow"} and count > 0,
            "cluster_status": cluster.get("status"),
            "documents": count,
        })
    except Exception as error:
        opensearch["error"] = type(error).__name__

    customer = {"ready": False}
    try:
        profile = get_user_profile(user_id)
        orders = get_orders(user_id)
        customer.update({
            "ready": bool(profile.get("found")) and orders.get("count", 0) > 0,
            "profile_found": bool(profile.get("found")),
            "orders": orders.get("count", 0),
        })
    except Exception as error:
        customer["error"] = type(error).__name__

    ready = embedding["ready"] and opensearch["ready"] and customer["ready"]
    return {
        "ready": ready,
        "embedding": embedding,
        "opensearch": opensearch,
        "customer": customer,
        "latency_ms": round((time.perf_counter() - started) * 1000),
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ready"] else 1)
