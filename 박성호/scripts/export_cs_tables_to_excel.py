"""One-off: export the Customer Service demo DynamoDB tables to an Excel
workbook (one sheet per table) so they can be reviewed outside DynamoDB."""

import os
from decimal import Decimal

import boto3
from dotenv import load_dotenv
from openpyxl import Workbook

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
TABLES = {
    "orders": os.getenv("CS_ORDERS_TABLE", "customer-service-demo-orders"),
    "payments": os.getenv("CS_PAYMENTS_TABLE", "customer-service-demo-payments"),
    "refunds": os.getenv("CS_REFUNDS_TABLE", "customer-service-demo-refunds"),
}

resource = boto3.resource("dynamodb", region_name=REGION)


def _plain(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return value


def export(output_path: str) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)

    for sheet_name, table_name in TABLES.items():
        table = resource.Table(table_name)
        items = table.scan().get("Items", [])
        items = [{k: _plain(v) for k, v in item.items()} for item in items]

        columns = sorted({key for item in items for key in item.keys()})
        sheet = workbook.create_sheet(title=sheet_name)
        sheet.append(columns)
        for item in items:
            sheet.append([item.get(column, "") for column in columns])

        print(f"{sheet_name} ({table_name}): {len(items)} rows")

    workbook.save(output_path)
    print(f"saved: {output_path}")


if __name__ == "__main__":
    export("data/cs_demo_dynamodb_export.xlsx")
