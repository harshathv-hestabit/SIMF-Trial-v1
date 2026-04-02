from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.modules.UI_API.settings import settings


NEWS_STAGE_LABELS = {
    "dps_news_processor": "DPS processed",
    "change_feed_to_mas": "Queued to MAS",
    "mas_hnw": "MAS relevance",
    "generate_insight_queue": "Queued to IG",
    "generate_insight": "Insight generation",
}


def load_metrics(database_client) -> dict[str, int]:
    news_collection = database_client[settings.NEWS_CONTAINER]
    insights_collection = database_client[settings.INSIGHTS_CONTAINER]
    return {
        "news_docs": news_collection.count_documents({}),
        "queued_to_mas": news_collection.count_documents(
            {"monitoring.current_stage": "change_feed_to_mas"},
        ),
        "in_insight_generation": news_collection.count_documents(
            {"monitoring.current_stage": "generate_insight"},
        ),
        "insights_saved": insights_collection.count_documents(
            {
                "$or": [
                    {"type": {"$exists": False}},
                    {"type": "insight"},
                ]
            },
        ),
        "failed_news_docs": news_collection.count_documents(
            {"monitoring.current_status": "failed"},
        ),
    }


def load_news_rows(database_client, limit: int) -> list[dict[str, Any]]:
    rows = list(
        database_client[settings.NEWS_CONTAINER]
        .find(
            {},
            {
                "_id": 0,
                "id": 1,
                "title": 1,
                "source": 1,
                "symbols": 1,
                "published_at": 1,
                "_ts": 1,
                "monitoring": 1,
            },
        )
        .sort("_ts", -1)
        .limit(limit)
    )
    return [_serialize_news_summary(row) for row in rows]


def load_recent_insights(database_client, limit: int) -> list[dict[str, Any]]:
    rows = list(
        database_client[settings.INSIGHTS_CONTAINER]
        .find(
            {
                "$or": [
                    {"type": {"$exists": False}},
                    {"type": "insight"},
                ]
            },
            {
                "_id": 0,
                "client_id": 1,
                "news_doc_id": 1,
                "news_title": 1,
                "status": 1,
                "verification_score": 1,
                "timestamp": 1,
            },
        )
        .sort("_ts", -1)
        .limit(limit)
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
    row = database_client[settings.NEWS_CONTAINER].find_one(
        {
            "$or": [
                {"id": news_id},
                {"_id": news_id},
            ]
        },
        {"_id": 0},
    )
    if row is None:
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
