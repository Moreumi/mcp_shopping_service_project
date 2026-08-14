"""Evaluate local SigLIP reranking without changing the active workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.search_products import INDEX_NAME, client
from tools.siglip_vision import rerank_candidates, runtime_status
from tools.hybrid_search import hybrid_search
from backend.policies import filter_products


DEFAULT_CASES = [
    {
        "name": "reported_red_sneaker_failure",
        "kind": "Sneakers",
        "color": "Red",
        "ids": ["B01AYA572G", "B07XBHLZW5"],
        "expected_rejected": ["B01AYA572G", "B07XBHLZW5"],
    },
    {"name": "nike_black_sneaker_positive", "kind": "Sneakers", "color": "Black", "ids": ["B000VHVZHE"], "expected_accepted": ["B000VHVZHE"]},
    {"name": "spor_black_sneaker_positive", "kind": "Sneakers", "color": "Black", "ids": ["B09FHK8WT6"], "expected_accepted": ["B09FHK8WT6"]},
    {"name": "black_loafer_positive", "kind": "FormalShoes", "color": "Black", "ids": ["B00MIYJMRI"], "expected_accepted": ["B00MIYJMRI"]},
    {"name": "brown_formal_negative", "kind": "FormalShoes", "color": "Black", "ids": ["B06XKBKBS1"], "expected_rejected": ["B06XKBKBS1"]},
    {"name": "gray_running_negative", "kind": "Sneakers", "color": "Red", "ids": ["B083FQWNBP"], "expected_rejected": ["B083FQWNBP"]},
]

SEARCH_CASES = [
    {"name": "men_red_sneakers", "query": "men red sneakers running shoes", "kind": "Sneakers", "color": "Red", "audience": "Men"},
    {"name": "women_black_sneakers", "query": "women black sneakers walking shoes", "kind": "Sneakers", "color": "Black", "audience": "Women"},
    {"name": "men_black_formal_shoes", "query": "men black formal dress shoes loafers", "kind": "FormalShoes", "color": "Black", "audience": "Men"},
]


def fetch_products(product_ids: list[str]) -> list[dict]:
    response = client.mget(index=INDEX_NAME, body={"ids": product_ids})
    products = []
    for document in response.get("docs", []):
        if document.get("found"):
            source = document["_source"]
            products.append({"product_id": source.get("product_id", document["_id"]), **source})
    return products


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/amazon_fashion/siglip_method_b_report.json")
    args = parser.parse_args()

    report = {"runtime": runtime_status(), "cases": []}
    for case in DEFAULT_CASES:
        products = fetch_products(case["ids"])
        accepted, audit = rerank_candidates(
            products,
            requested_kind=case["kind"],
            required_color=case["color"],
        )
        accepted_ids = {item["product_id"] for item in accepted}
        rejected_ids = {
            item["product_id"] for item in audit
            if not item["accepted"] and not item["reason"].startswith("vision_error:")
        }
        expected_rejected = set(case.get("expected_rejected", []))
        expected_accepted = set(case.get("expected_accepted", []))
        passed = expected_rejected.issubset(rejected_ids) and expected_accepted.issubset(accepted_ids)
        report["cases"].append({
            **case,
            "passed": passed,
            "accepted_ids": sorted(accepted_ids),
            "audit": audit,
        })

    for case in SEARCH_CASES:
        retrieved = hybrid_search(
            query=case["query"],
            size=30,
            category="Shoes",
            audience=case["audience"],
            # Do not trust catalog color here: method B exists specifically to
            # let the image decide visible color after broad retrieval.
            required_color=None,
            product_kind=case["kind"],
        )
        products = filter_products(
            retrieved,
            audience=case["audience"],
            category="Shoes",
            requested_kind=case["kind"],
            required_color=None,
        )
        accepted, audit = rerank_candidates(
            products,
            requested_kind=case["kind"],
            required_color=case["color"],
        )
        # A demo response needs three good cards. Requiring at least three also
        # guards against a visually precise filter that destroys recall.
        passed = len(accepted) >= 3
        report["cases"].append({
            **case,
            "passed": passed,
            "retrieved_count": len(retrieved),
            "code_filtered_count": len(products),
            "accepted_count": len(accepted),
            "accepted": [
                {"product_id": item["product_id"], "title": item.get("title"), "vision_score": item["vision_score"]}
                for item in accepted
            ],
            "audit": audit,
        })

    controlled = report["cases"][:len(DEFAULT_CASES)]
    report["controlled_accuracy"] = sum(case["passed"] for case in controlled) / len(controlled)
    report["search_coverage_passed"] = all(case["passed"] for case in report["cases"][len(DEFAULT_CASES):])
    # Method B validates classification precision. Search coverage is reported
    # separately because method A is what removes the metadata-retrieval ceiling.
    report["passed"] = bool(report["runtime"].get("ready")) and report["controlled_accuracy"] >= 0.9
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
