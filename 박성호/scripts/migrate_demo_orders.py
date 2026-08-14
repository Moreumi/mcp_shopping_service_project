"""Write the prepared Amazon Fashion demo orders after explicit --apply."""

from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal

import boto3
from dotenv import load_dotenv

from backend.demo_persona import DEMO_ORDERS


def main(apply: bool):
    if not apply:
        print(json.dumps({"dry_run": True, "orders": DEMO_ORDERS}, ensure_ascii=False, indent=2))
        return
    load_dotenv(".env")
    table = boto3.resource(
        "dynamodb", region_name=os.getenv("AWS_REGION", "ap-northeast-2")
    ).Table(os.getenv("ORDERS_TABLE", "shopping-orders"))
    for order in DEMO_ORDERS:
        item = dict(order)
        if item.get("price") is not None:
            item["price"] = Decimal(str(item["price"]))
        table.put_item(Item=item)
    print(json.dumps({"written": len(DEMO_ORDERS)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    main(args.apply)
