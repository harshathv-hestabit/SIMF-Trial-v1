from datetime import datetime
from app.common.azure_services.cosmos import build_async_cosmos_client, ensure_async_container
from ..config import settings
from .insight_job_state import build_insight_document_id


async def update_db(state: dict):
    async with build_async_cosmos_client(settings.COSMOS_URL, settings.COSMOS_KEY) as client:
        container = await ensure_async_container(
            client,
            database_name=settings.COSMOS_DB,
            container_name=settings.INSIGHTS_CONTAINER,
            partition_key_path=settings.INSIGHTS_CONTAINER_PARTITION_ID,
        )
        news = state["news_document"]
        client_id = state["client_id"]
        news_doc_id = news.get("id")
        doc = {
            "id": build_insight_document_id(client_id, news_doc_id),
            "type": "insight",
            "workflow_type": "generate_insight",
            "job_key": state.get("job_key"),
            "client_id": client_id,
            "news_doc_id": news_doc_id,
            "insight": state["insight_draft"],
            "verification_score": state["verification_score"],
            "news_title": news.get("title"),
            "tickers": news.get("tickers"),
            "status": state["status"],
            "token_usage": state.get("token_usage", {}),
            "timestamp": datetime.now().isoformat(),
        }

        await container.upsert_item(doc)
