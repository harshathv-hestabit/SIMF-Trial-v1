from __future__ import annotations

from typing import Any

from app.modules.UI_API.settings import settings


def load_clients(database_client) -> list[dict[str, str]]:
    collection = database_client[settings.CLIENT_PORTFOLIO_CONTAINER]
    items = list(
        collection.find(
            {},
            {
                "_id": 0,
                "client_id": 1,
                "client_name": 1,
            },
        )
    )
    deduped: dict[str, dict[str, str]] = {}
    for item in items:
        client_id = item.get("client_id")
        if client_id:
            deduped[client_id] = {
                "client_id": client_id,
                "client_name": item.get("client_name", client_id),
            }
    return sorted(deduped.values(), key=lambda item: item["client_name"])


def load_client_portfolio(database_client, client_id: str) -> dict[str, Any] | None:
    collection = database_client[settings.CLIENT_PORTFOLIO_CONTAINER]
    portfolio = collection.find_one(
        {"client_id": client_id},
        {"_id": 0},
    )
    if portfolio is None:
        return None

    tickers = portfolio.get("ticker_symbols") or []
    currencies = portfolio.get("currencies") or []
    tags = portfolio.get("tags_of_interest") or []

    return {
        "client_id": portfolio.get("client_id"),
        "client_name": portfolio.get("client_name"),
        "client_type": portfolio.get("client_type"),
        "mandate": portfolio.get("mandate"),
        "total_aum_aed": portfolio.get("total_aum_aed"),
        "ticker_count": len(tickers),
        "ticker_symbols": tickers,
        "currencies": currencies,
        "tags_of_interest": tags,
        "query": portfolio.get("query"),
        "classification_weights": _weight_entries(portfolio.get("classification_weights")),
        "asset_type_weights": _weight_entries(portfolio.get("asset_type_weights")),
        "asset_descriptions": (portfolio.get("asset_descriptions") or [])[:20],
        "isins": (portfolio.get("isins") or [])[:20],
    }


def load_client_insights(database_client, client_id: str) -> list[dict[str, Any]]:
    collection = database_client[settings.INSIGHTS_CONTAINER]
    insights = list(
        collection.find(
            {
                "client_id": client_id,
                "$or": [
                    {"type": {"$exists": False}},
                    {"type": "insight"},
                ],
            },
            {
                "_id": 0,
                "id": 1,
                "client_id": 1,
                "insight": 1,
                "verification_score": 1,
                "news_title": 1,
                "tickers": 1,
                "status": 1,
                "timestamp": 1,
            },
        ).sort("timestamp", -1)
    )
    return [
        {
            "id": item.get("id"),
            "client_id": item.get("client_id"),
            "news_title": item.get("news_title") or "Untitled Insight",
            "insight": item.get("insight") or "No insight text available.",
            "verification_score": item.get("verification_score"),
            "tickers": item.get("tickers") or [],
            "status": item.get("status", "unknown"),
            "timestamp": item.get("timestamp"),
        }
        for item in insights
    ]


def _weight_entries(weights: dict[str, Any] | None) -> list[dict[str, float | str]]:
    entries = []
    for key, value in (weights or {}).items():
        entries.append(
            {
                "label": key,
                "weight_percent": round(float(value) * 100, 2),
            }
        )
    return sorted(entries, key=lambda item: item["weight_percent"], reverse=True)
