"""Upsert the deterministic demo persona without replacing unrelated profile data."""

import argparse
import os

import boto3
from dotenv import load_dotenv

from backend.demo_persona import DEMO_PERSONA


def seed(user_id: str) -> None:
    load_dotenv()
    table = boto3.resource(
        "dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1")
    ).Table(os.getenv("USERS_TABLE", "shopping-users"))

    names = {f"#f{index}": key for index, key in enumerate(DEMO_PERSONA)}
    values = {f":v{index}": value for index, value in enumerate(DEMO_PERSONA.values())}
    assignments = [f"{name} = {value}" for name, value in zip(names, values)]
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(assignments),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    print(f"Demo persona updated for {user_id} in {table.name}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default="user_001")
    seed(parser.parse_args().user_id)
