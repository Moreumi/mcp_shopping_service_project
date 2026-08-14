"""DynamoDB customer context adapter used directly by the workflow."""

import os

import boto3
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv


load_dotenv()

_dynamodb = boto3.resource(
    "dynamodb",
    region_name=os.getenv("AWS_REGION", "ap-northeast-2"),
)
_users = _dynamodb.Table(os.getenv("USERS_TABLE", "shopping-users"))
_orders = _dynamodb.Table(os.getenv("ORDERS_TABLE", "shopping-orders"))


def get_user_profile(user_id: str):
    item = _users.get_item(Key={"user_id": user_id}).get("Item")
    if not item:
        return {"found": False, "message": "사용자를 찾지 못했습니다."}
    return {"found": True, "user": item}


def get_orders(user_id: str):
    orders = _orders.query(
        KeyConditionExpression=Key("user_id").eq(user_id)
    ).get("Items", [])
    orders.sort(key=lambda item: item.get("purchase_date", ""), reverse=True)
    return {"user_id": user_id, "count": len(orders), "orders": orders}
