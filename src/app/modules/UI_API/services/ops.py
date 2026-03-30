from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.modules.UI_API.settings import settings


NEWS_STAGE_LABELS = {
    "dps_news_processor": "DPS processed",
    "change_feed_to_mas": "Queued to MAS",
    "mas_hnw": "MAS relevance",
    "generate_insight_queue": "Queued to IG",
    "generate_insight": "Insight generation",
}


def load_metrics(database_client) -> dict[str, int]:
    news_container = database_client.get_container_client(settings.NEWS_CONTAINER)
    insights_container = _get_container_or_none(database_client, settings.INSIGHTS_CONTAINER)
    return {
        "news_docs": _count_query(
            news_container,
            "SELECT VALUE COUNT(1) FROM c",
        ),
        "queued_to_mas": _count_query(
            news_container,
            (
                "SELECT VALUE COUNT(1) FROM c "
                "WHERE IS_DEFINED(c.monitoring.current_stage) "
                "AND c.monitoring.current_stage = @stage"
            ),
            parameters=[{"name": "@stage", "value": "change_feed_to_mas"}],
        ),
        "in_insight_generation": _count_query(
            news_container,
            (
                "SELECT VALUE COUNT(1) FROM c "
                "WHERE IS_DEFINED(c.monitoring.current_stage) "
                "AND c.monitoring.current_stage = @stage"
            ),
            parameters=[{"name": "@stage", "value": "generate_insight"}],
        ),
        "insights_saved": _count_query(
            insights_container,
            "SELECT VALUE COUNT(1) FROM c",
        ),
        "failed_news_docs": _count_query(
            news_container,
            (
                "SELECT VALUE COUNT(1) FROM c "
                "WHERE IS_DEFINED(c.monitoring.current_status) "
                "AND c.monitoring.current_status = 'failed'"
            ),
        ),
    }


def load_news_rows(database_client, limit: int) -> list[dict[str, Any]]:
    news_container = database_client.get_container_client(settings.NEWS_CONTAINER)
    query = """
    SELECT TOP @limit
        c.id,
        c.title,
        c.source,
        c.symbols,
        c.published_at,
        c._ts,
        c.monitoring
    FROM c
    ORDER BY c._ts DESC
    """
    rows = list(
        news_container.query_items(
            query=query,
            parameters=[{"name": "@limit", "value": limit}],
            enable_cross_partition_query=True,
        )
    )
    return [_serialize_news_summary(row) for row in rows]


def load_recent_insights(database_client, limit: int) -> list[dict[str, Any]]:
    insights_container = _get_container_or_none(database_client, settings.INSIGHTS_CONTAINER)
    if insights_container is None:
        return []
    query = """
    SELECT TOP @limit
        c.client_id,
        c.news_doc_id,
        c.news_title,
        c.status,
        c.verification_score,
        c.timestamp
    FROM c
    ORDER BY c._ts DESC
    """
    rows = list(
        insights_container.query_items(
            query=query,
            parameters=[{"name": "@limit", "value": limit}],
            enable_cross_partition_query=True,
        )
    )
    return [
        {
            "client_id": row.get("client_id"),
            "news_doc_id": row.get("news_doc_id"),
            "news_title": row.get("news_title") or "Untitled Insight",
            "status": row.get("status", "unknown"),
            "verification_score": row.get("verification_score"),
            "timestamp": row.get("timestamp"),
        }
        for row in rows
    ]


def load_news_detail(database_client, news_id: str) -> dict[str, Any] | None:
    news_container = database_client.get_container_client(settings.NEWS_CONTAINER)
    try:
        row = news_container.read_item(news_id, partition_key=news_id)
    except CosmosResourceNotFoundError:
        return None

    monitoring = row.get("monitoring") or {}
    return {
        "id": row.get("id"),
        "title": row.get("title") or "Untitled",
        "source": row.get("source") or "-",
        "symbols": row.get("symbols") or [],
        "published_at": _format_timestamp(row.get("published_at")),
        "current_stage": _format_stage(monitoring.get("current_stage")),
        "current_status": monitoring.get("current_status", "unknown"),
        "updated_at": _format_timestamp(monitoring.get("updated_at"), row.get("_ts")),
        "timeline": _serialize_timeline(monitoring.get("timeline") or []),
        "raw_monitoring": monitoring,
    }


def _serialize_news_summary(row: dict[str, Any]) -> dict[str, Any]:
    monitoring = row.get("monitoring") or {}
    symbols = row.get("symbols") or []
    return {
        "id": row.get("id"),
        "title": row.get("title") or "Untitled",
        "source": row.get("source") or "-",
        "symbols": symbols,
        "symbols_preview": ", ".join(symbols[:5]) if symbols else "-",
        "stage": _format_stage(monitoring.get("current_stage")),
        "status": monitoring.get("current_status", "unknown"),
        "updated_at": _format_timestamp(monitoring.get("updated_at"), row.get("_ts")),
        "published_at": _format_timestamp(row.get("published_at")),
    }


def _serialize_timeline(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for item in reversed(timeline):
        details = item.get("details") or {}
        events.append(
            {
                "timestamp": item.get("timestamp"),
                "stage": _format_stage(item.get("stage")),
                "status": item.get("status"),
                "details": json.dumps(details, ensure_ascii=True) if details else "-",
            }
        )
    return events


def _count_query(container, query: str, parameters: list[dict[str, Any]] | None = None) -> int:
    if container is None:
        return 0
    try:
        return next(
            iter(
                container.query_items(
                    query=query,
                    parameters=parameters,
                    enable_cross_partition_query=True,
                )
            ),
            0,
        )
    except CosmosResourceNotFoundError:
        return 0


def _get_container_or_none(database_client, container_name: str):
    try:
        container = database_client.get_container_client(container_name)
        container.read()
        return container
    except CosmosResourceNotFoundError:
        return None


def _format_stage(stage: str | None) -> str:
    if not stage:
        return "Untracked"
    return NEWS_STAGE_LABELS.get(stage, stage.replace("_", " ").title())


def _format_timestamp(value: str | None, fallback_ts: int | None = None) -> str:
    if value:
        return value
    if fallback_ts:
        return datetime.fromtimestamp(fallback_ts, tz=timezone.utc).isoformat()
    return "-"
