from __future__ import annotations

from typing import Any

from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.modules.UI_API.settings import settings


def load_clients(database_client) -> list[dict[str, str]]:
    container = database_client.get_container_client(settings.CLIENT_PORTFOLIO_CONTAINER)
    query = """
    SELECT c.client_id, c.client_name
    FROM c
    """
    items = list(
        container.query_items(
            query=query,
            enable_cross_partition_query=True,
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
    container = database_client.get_container_client(settings.CLIENT_PORTFOLIO_CONTAINER)
    query = """
    SELECT TOP 1 *
    FROM c
    WHERE c.client_id = @client_id
    """
    items = list(
        container.query_items(
            query=query,
            parameters=[{"name": "@client_id", "value": client_id}],
            partition_key=client_id,
        )
    )
    if not items:
        return None

    portfolio = items[0]
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
    try:
        container = database_client.get_container_client(settings.INSIGHTS_CONTAINER)
        container.read()
    except CosmosResourceNotFoundError:
        return []
    query = """
    SELECT c.id, c.client_id, c.insight, c.verification_score,
           c.news_title, c.tickers, c.status, c.timestamp
    FROM c
    WHERE c.client_id = @client_id
    ORDER BY c.timestamp DESC
    """
    insights = list(
        container.query_items(
            query=query,
            parameters=[{"name": "@client_id", "value": client_id}],
            partition_key=client_id,
        )
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
