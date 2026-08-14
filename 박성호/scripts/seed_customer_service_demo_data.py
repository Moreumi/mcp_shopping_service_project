"""Create the Customer Service demo DynamoDB tables and seed 20 mock orders.

These tables are independent of the main shopping-assistant's DynamoDB
tables (shopping-orders / shopping-users). The schema, field names and
status vocabulary follow the original mini-project (미니 프로젝트_수정 - Copy)
exactly: int order_id/customer_id, delivery_status enum, separate
orders/payments/refunds records.

The seeded data is designed to exercise every branch of every policy in
backend/cs/policies/*.py at least once.
"""

import os

import boto3
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
ORDERS_TABLE = os.getenv("CS_ORDERS_TABLE", "customer-service-demo-orders")
PAYMENTS_TABLE = os.getenv("CS_PAYMENTS_TABLE", "customer-service-demo-payments")
REFUNDS_TABLE = os.getenv("CS_REFUNDS_TABLE", "customer-service-demo-refunds")

client = boto3.client("dynamodb", region_name=REGION)
resource = boto3.resource("dynamodb", region_name=REGION)


def ensure_table(table_name: str, key_name: str):
    try:
        client.describe_table(TableName=table_name)
        print(f"table already exists: {table_name}")
        return
    except client.exceptions.ResourceNotFoundException:
        pass

    print(f"creating table: {table_name}")
    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[{"AttributeName": key_name, "AttributeType": "N"}],
        KeySchema=[{"AttributeName": key_name, "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=table_name)
    print(f"table active: {table_name}")


# =========================================================
# 가상 주문 데이터 (20건)
# order_completion / payment_completion / order_cancel /
# delivery_address_change / order_payment_consistency
# 정책의 모든 분기를 최소 한 번씩 exercise 한다.
# =========================================================

# shopping-orders(DynamoDB, New Thread가 쓰는 메인 주문 테이블)에 실제로 들어있는
# 주문들의 실제 Amazon Fashion 카탈로그 상품명이다. 가상의 상품명이 아니라, 그 테이블의
# order_001~010에 실제로 연결된 product_id/title을 그대로 재사용한다.
CATALOG_PRODUCT_NAMES = [
    "Casio F91W-1 Classic Resin Strap Digital Sport Watch",
    "Sport Watch, 50M Waterproof Watch, Digital Watch with Alarm Date and Time (Black)",
    "Nike Men's Epic React Flyknit Running Shoes",
    "PUMA Challenger Backpack Fully Padded, 15\" Laptop Pocket Black",
    "Russell Athletic Men's Dri-Power Fleece Hoodies & Sweatshirts",
    "Uneek UC604 Mens Classic Full Zip Micro Fleece Jacket",
    "Women's Fashion Sunglasses UV400 Protection Polarized Sunglasses (black, 70mm)",
    "NELEUS Women's 3 Pack Compression Base Layer Dry Fit Tank Top",
    "Boston Leather 1-1/4\" Garrison Leather Belt Black 46",
    "Augus Leather Messenger Bag for Men Vintage Travel Backpack 17 inch laptop Brief",
]

orders = [
    # 시나리오 A/B: 취소 가능한 정상 주문 두 건 (배송준비중)
    {"order_id": 20001, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[0], "delivery_address": "서울시 성동구 왕십리로 10", "order_date": "2026-08-01", "total_price": 45000, "delivery_status": "preparing_shipment", "order_status": "order_completed"},
    {"order_id": 20002, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[1], "delivery_address": "서울시 성동구 왕십리로 10", "order_date": "2026-08-03", "total_price": 28000, "delivery_status": "preparing_shipment", "order_status": "order_completed"},

    # 시나리오 C: 이미 취소된 주문 (already_canceled / consistent_canceled)
    {"order_id": 20003, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[2], "delivery_address": "서울시 강남구 테헤란로 152", "order_date": "2026-07-28", "total_price": 65000, "delivery_status": "preparing_shipment", "order_status": "order_canceled"},

    # 시나리오 D: 배송중 -> 취소/배송지변경 불가 (in_transit)
    {"order_id": 20004, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[3], "delivery_address": "서울시 마포구 월드컵로 96", "order_date": "2026-08-05", "total_price": 57000, "delivery_status": "in_transit", "order_status": "order_completed"},

    # 시나리오 E: 배송완료 -> 취소/배송지변경 불가 (delivered)
    {"order_id": 20005, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[4], "delivery_address": "서울시 송파구 올림픽로 300", "order_date": "2026-07-20", "total_price": 41000, "delivery_status": "delivered", "order_status": "order_completed"},

    # 시나리오 F: 계좌이체 취소 -> refund_account_required 플로우
    {"order_id": 20006, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[5], "delivery_address": "서울시 종로구 사직로 161", "order_date": "2026-08-09", "total_price": 73000, "delivery_status": "preparing_shipment", "order_status": "order_completed"},

    # 시나리오 G: 주문 실패 (order_failed / consistent_failed)
    {"order_id": 20007, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[6], "delivery_address": "서울시 은평구 통일로 866", "order_date": "2026-08-02", "total_price": 39000, "delivery_status": "preparing_shipment", "order_status": "order_failed"},

    # 시나리오 H: 주문완료 + 결제실패 -> needs_review (order_completed, payment_failed)
    {"order_id": 20008, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[7], "delivery_address": "서울시 노원구 동일로 1414", "order_date": "2026-08-04", "total_price": 52000, "delivery_status": "preparing_shipment", "order_status": "order_completed"},

    # 시나리오 I: 주문완료 + 결제취소 -> needs_review (order_completed, payment_canceled)
    {"order_id": 20009, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[8], "delivery_address": "서울시 강서구 화곡로 302", "order_date": "2026-08-06", "total_price": 33000, "delivery_status": "preparing_shipment", "order_status": "order_completed"},

    # 시나리오 J/K: 취소된 주문 두 건 -> needs_review / consistent_not_completed
    {"order_id": 20010, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[9], "delivery_address": "서울시 동작구 상도로 369", "order_date": "2026-07-15", "total_price": 61000, "delivery_status": "preparing_shipment", "order_status": "order_canceled"},
    {"order_id": 20011, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[0], "delivery_address": "서울시 동작구 상도로 369", "order_date": "2026-07-22", "total_price": 47000, "delivery_status": "preparing_shipment", "order_status": "order_canceled"},

    # 시나리오 L/M: 주문 실패 두 건 -> needs_review / consistent_not_completed
    {"order_id": 20012, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[1], "delivery_address": "서울시 관악구 남부순환로 1500", "order_date": "2026-07-18", "total_price": 29000, "delivery_status": "preparing_shipment", "order_status": "order_failed"},
    {"order_id": 20013, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[2], "delivery_address": "서울시 관악구 남부순환로 1500", "order_date": "2026-07-19", "total_price": 31000, "delivery_status": "preparing_shipment", "order_status": "order_failed"},

    # 시나리오 N: 깔끔한 정상 완료 주문 (order_confirmation / payment_confirmation / 결제수단변경 데모용)
    {"order_id": 20014, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[3], "delivery_address": "서울시 영등포구 여의대로 24", "order_date": "2026-08-10", "total_price": 88000, "delivery_status": "preparing_shipment", "order_status": "order_completed"},

    # 시나리오 O: delivery_status 값이 정의되지 않은 상태 -> needs_review/unknown_delivery_status
    {"order_id": 20015, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[4], "delivery_address": "서울시 광진구 능동로 120", "order_date": "2026-08-07", "total_price": 42000, "delivery_status": "customs_hold", "order_status": "order_completed"},

    # 시나리오 P: order_status 값이 정의되지 않은 상태 -> needs_review/unknown_order_status
    {"order_id": 20016, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[5], "delivery_address": "서울시 서대문구 연세로 50", "order_date": "2026-08-08", "total_price": 36000, "delivery_status": "preparing_shipment", "order_status": "order_on_hold"},

    # 시나리오 Q: 계좌이체 취소 두 번째 사례 + 배송지 변경 성공 데모
    {"order_id": 20017, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[6], "delivery_address": "서울시 중구 을지로 100", "order_date": "2026-08-11", "total_price": 54000, "delivery_status": "preparing_shipment", "order_status": "order_completed"},

    # 시나리오 R: 배송중 + 결제취소 (in_transit 이면서 결제 불일치까지 겹치는 엣지 케이스)
    {"order_id": 20018, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[7], "delivery_address": "서울시 성북구 안암로 145", "order_date": "2026-08-05", "total_price": 49000, "delivery_status": "in_transit", "order_status": "order_completed"},

    # 시나리오 S: 배송완료 + 결제실패 (delivered 이면서 결제 불일치까지 겹치는 엣지 케이스)
    {"order_id": 20019, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[8], "delivery_address": "서울시 용산구 이태원로 200", "order_date": "2026-07-30", "total_price": 67000, "delivery_status": "delivered", "order_status": "order_completed"},

    # 시나리오 T: 결제 정보가 아예 없는 주문 -> payment_not_found 데모
    {"order_id": 20020, "customer_id": 1, "product_name": CATALOG_PRODUCT_NAMES[9], "delivery_address": "서울시 양천구 목동로 300", "order_date": "2026-08-12", "total_price": 25000, "delivery_status": "preparing_shipment", "order_status": "order_completed"},
]

# order_id 20020 은 결제 정보가 없는 케이스를 보여주기 위해 결제 레코드를 만들지 않는다.
payments = [
    {"payment_id": 60001, "order_id": 20001, "payment_method": "card", "payment_amount": 45000, "payment_status": "payment_completed", "payment_date": "2026-08-01"},
    {"payment_id": 60002, "order_id": 20002, "payment_method": "card", "payment_amount": 28000, "payment_status": "payment_completed", "payment_date": "2026-08-03"},
    {"payment_id": 60003, "order_id": 20003, "payment_method": "card", "payment_amount": 65000, "payment_status": "payment_canceled", "payment_date": "2026-07-28"},
    {"payment_id": 60004, "order_id": 20004, "payment_method": "card", "payment_amount": 57000, "payment_status": "payment_completed", "payment_date": "2026-08-05"},
    {"payment_id": 60005, "order_id": 20005, "payment_method": "card", "payment_amount": 41000, "payment_status": "payment_completed", "payment_date": "2026-07-20"},
    {"payment_id": 60006, "order_id": 20006, "payment_method": "cash", "payment_amount": 73000, "payment_status": "payment_completed", "payment_date": "2026-08-09"},
    {"payment_id": 60007, "order_id": 20007, "payment_method": "card", "payment_amount": 39000, "payment_status": "payment_failed", "payment_date": "2026-08-02"},
    {"payment_id": 60008, "order_id": 20008, "payment_method": "card", "payment_amount": 52000, "payment_status": "payment_failed", "payment_date": "2026-08-04"},
    {"payment_id": 60009, "order_id": 20009, "payment_method": "card", "payment_amount": 33000, "payment_status": "payment_canceled", "payment_date": "2026-08-06"},
    {"payment_id": 60010, "order_id": 20010, "payment_method": "card", "payment_amount": 61000, "payment_status": "payment_completed", "payment_date": "2026-07-15"},
    {"payment_id": 60011, "order_id": 20011, "payment_method": "card", "payment_amount": 47000, "payment_status": "payment_failed", "payment_date": "2026-07-22"},
    {"payment_id": 60012, "order_id": 20012, "payment_method": "card", "payment_amount": 29000, "payment_status": "payment_completed", "payment_date": "2026-07-18"},
    {"payment_id": 60013, "order_id": 20013, "payment_method": "card", "payment_amount": 31000, "payment_status": "payment_canceled", "payment_date": "2026-07-19"},
    {"payment_id": 60014, "order_id": 20014, "payment_method": "card", "payment_amount": 88000, "payment_status": "payment_completed", "payment_date": "2026-08-10"},
    {"payment_id": 60015, "order_id": 20015, "payment_method": "card", "payment_amount": 42000, "payment_status": "payment_completed", "payment_date": "2026-08-07"},
    {"payment_id": 60016, "order_id": 20016, "payment_method": "card", "payment_amount": 36000, "payment_status": "payment_completed", "payment_date": "2026-08-08"},
    {"payment_id": 60017, "order_id": 20017, "payment_method": "cash", "payment_amount": 54000, "payment_status": "payment_completed", "payment_date": "2026-08-11"},
    {"payment_id": 60018, "order_id": 20018, "payment_method": "card", "payment_amount": 49000, "payment_status": "payment_canceled", "payment_date": "2026-08-05"},
    {"payment_id": 60019, "order_id": 20019, "payment_method": "card", "payment_amount": 67000, "payment_status": "payment_failed", "payment_date": "2026-07-30"},
]

# 이미 취소되어 환불까지 완료된 주문(20003)의 환불 이력을 하나 미리 심어둔다.
# 이후 데모 중 발생하는 신규 취소 건은 order_payment_service.cancel_order()가
# 이 refund_id 이후 번호(80002...)로 자동 채번한다.
refunds = [
    {"refund_id": 80001, "payment_id": 60003, "order_id": 20003, "refund_amount": 65000, "refund_status": "refund_completed", "bank_name": None, "account_number": None, "account_holder": None},
]


def seed():
    ensure_table(ORDERS_TABLE, "order_id")
    ensure_table(PAYMENTS_TABLE, "payment_id")
    ensure_table(REFUNDS_TABLE, "refund_id")

    orders_table = resource.Table(ORDERS_TABLE)
    payments_table = resource.Table(PAYMENTS_TABLE)
    refunds_table = resource.Table(REFUNDS_TABLE)

    with orders_table.batch_writer() as batch:
        for order in orders:
            batch.put_item(Item=order)
    print(f"seeded {len(orders)} orders")

    with payments_table.batch_writer() as batch:
        for payment in payments:
            batch.put_item(Item=payment)
    print(f"seeded {len(payments)} payments")

    with refunds_table.batch_writer() as batch:
        for refund in refunds:
            batch.put_item(Item=refund)
    print(f"seeded {len(refunds)} refunds")


if __name__ == "__main__":
    seed()
