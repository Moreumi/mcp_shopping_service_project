"""Read-only connectivity check for the OpenSearch domain configured in .env."""

from __future__ import annotations

import json
import os
import time

from tools.search_products import client


def check():
    result = {"configured_index": os.getenv("OPENSEARCH_INDEX")}
    for name, operation in (
        ("info", lambda: client.info(request_timeout=30)),
        ("health", lambda: client.cluster.health(request_timeout=30)),
    ):
        started = time.perf_counter()
        try:
            value = operation()
            result[name] = {
                "ok": True,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "value": value,
            }
        except Exception as error:
            result[name] = {
                "ok": False,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "error": f"{type(error).__name__}: {str(error)[:300]}",
            }
    result["ready"] = all(result[name]["ok"] for name in ("info", "health"))
    return result


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False, indent=2, default=str))
