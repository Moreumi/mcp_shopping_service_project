"""Run the end-to-end demo conversation set and emit a machine-readable score."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from backend.agent_graph import invoke_shopping_graph_result
from backend.policies import filter_products


def evaluate_scenario(scenario: dict, user_id: str) -> dict:
    thread_id = f"eval-{scenario['id']}-{uuid4()}"
    result = None
    started = time.perf_counter()
    for message in scenario["steps"]:
        result = invoke_shopping_graph_result(message, user_id, thread_id)

    expected = scenario["expect"]
    products = result.get("products", [])
    checks = {
        "service_available": result.get("service_status") == "ok",
        "mode": result.get("response_mode") == expected.get("mode"),
    }
    if "products" in expected:
        checks["product_count"] = len(products) == expected["products"]
    if "minimum_orders" in expected:
        checks["order_count"] = len(result.get("orders", [])) >= expected["minimum_orders"]
    if products and any(expected.get(field) for field in ("category", "audience", "color")):
        filtered = filter_products(
            products,
            category=expected.get("category"),
            audience=expected.get("audience"),
            required_color=expected.get("color"),
        )
        checks["hard_filters"] = len(filtered) == len(products)

    return {
        "id": scenario["id"],
        "passed": all(checks.values()),
        "checks": checks,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "product_ids": [product.get("product_id") for product in products],
    }


def run(path: str, user_id: str) -> dict:
    scenarios = json.loads(Path(path).read_text(encoding="utf-8"))
    results = [evaluate_scenario(scenario, user_id) for scenario in scenarios]
    return {
        "passed": sum(result["passed"] for result in results),
        "total": len(results),
        "pass_rate": round(sum(result["passed"] for result in results) / len(results), 3),
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default="tests/fixtures/demo_scenarios.json")
    parser.add_argument("--user-id", default="user_001")
    args = parser.parse_args()
    print(json.dumps(run(args.scenarios, args.user_id), ensure_ascii=False, indent=2))
