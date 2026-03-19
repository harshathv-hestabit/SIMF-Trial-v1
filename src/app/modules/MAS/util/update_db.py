import time
from datetime import datetime
from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey
from ..config import settings

async def _ensure_container(client: CosmosClient):
    db = await client.create_database_if_not_exists(settings.COSMOS_DB)
    container = await db.create_container_if_not_exists(
        id=settings.INSIGHTS_CONTAINER,
        partition_key=PartitionKey(settings.INSIGHTS_CONTAINER_PARTITION_ID),
    )
    return container

async def update_db(state: dict):

    async with CosmosClient(
        settings.COSMOS_URL,
        credential=settings.COSMOS_KEY,
        connection_verify=False,
        enable_endpoint_discovery=False,
        connection_timeout=5,
    ) as client:
        container = await _ensure_container(client)
        news = state["news_document"]
        doc = {
            "id": f"{state['client_id']}_{int(time.time() * 1000)}",
            "client_id": state["client_id"],
            "insight": state["insight_draft"],
            "verification_score": state["verification_score"],
            "news_title": news.get("title"),
            "tickers": news.get("tickers"),
            "status": state["status"],
            "timestamp": datetime.now().isoformat()
        }

        await container.upsert_item(doc)