from __future__ import annotations

from pymongo import MongoClient
from pymongo.database import Database


def build_sync_mongo_client(
    mongo_uri: str,
    *,
    server_selection_timeout_ms: int = 5000,
) -> MongoClient:
    if not mongo_uri:
        raise ValueError("MONGO_URI must be configured for MongoDB access")

    client = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
    )
    client.admin.command("ping")
    return client


def get_database_client(client: MongoClient, database_name: str) -> Database:
    if not database_name:
        raise ValueError("MONGO_DB must be configured for MongoDB access")
    return client[database_name]
