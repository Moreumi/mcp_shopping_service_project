"""Customer Service 데모 전용 DynamoDB 연동.

New Thread(메인 쇼핑 어시스턴트)가 사용하는 shopping-orders / shopping-users
테이블과는 완전히 분리된 별도 테이블(customer-service-demo-*)을 사용한다.

여기서 읽어오는 dict의 필드명/타입은 미니 프로젝트_수정 - Copy 폴더의
sample_data.py 구조(정수 order_id/customer_id, delivery_status 등)를
그대로 따른다. backend/cs/orchestrator.py 이하 로직은 이 형태를 그대로
기대하므로 별도 수정이 필요 없다.
"""

import os
from decimal import Decimal

import boto3
from dotenv import load_dotenv

load_dotenv()

_dynamodb = boto3.resource(
    "dynamodb",
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)

ORDERS_TABLE = os.getenv("CS_ORDERS_TABLE", "customer-service-demo-orders")
PAYMENTS_TABLE = os.getenv("CS_PAYMENTS_TABLE", "customer-service-demo-payments")
REFUNDS_TABLE = os.getenv("CS_REFUNDS_TABLE", "customer-service-demo-refunds")

_orders_table = _dynamodb.Table(ORDERS_TABLE)
_payments_table = _dynamodb.Table(PAYMENTS_TABLE)
_refunds_table = _dynamodb.Table(REFUNDS_TABLE)


def _from_dynamodb(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, list):
        return [_from_dynamodb(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_dynamodb(v) for k, v in value.items()}
    return value


def _to_dynamodb(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamodb(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_dynamodb(v) for k, v in value.items()}
    return value


def load_orders() -> list[dict]:
    items = _orders_table.scan().get("Items", [])
    return [_from_dynamodb(item) for item in items]


def load_payments() -> list[dict]:
    items = _payments_table.scan().get("Items", [])
    return [_from_dynamodb(item) for item in items]


def load_refunds() -> list[dict]:
    items = _refunds_table.scan().get("Items", [])
    return [_from_dynamodb(item) for item in items]


def save_order(order: dict) -> None:
    _orders_table.put_item(Item=_to_dynamodb(order))


def save_payment(payment: dict) -> None:
    _payments_table.put_item(Item=_to_dynamodb(payment))


def save_refund(refund: dict) -> None:
    _refunds_table.put_item(Item=_to_dynamodb(refund))
