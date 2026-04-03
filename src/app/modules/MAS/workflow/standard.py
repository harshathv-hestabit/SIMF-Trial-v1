from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.common.azure_services.cosmos import (
    build_sync_cosmos_client,
    get_container_client,
    get_database_client,
)
from app.common.mongo_backup import backup_document_sync
from app.common.news_monitor import merge_news_monitoring, update_news_lifecycle

from ..config import process_news_stream, settings
from ..relevance import (
    build_client_profile_summary,
    build_compact_portfolio_context_from_grounding,
    build_relevance_payload,
    ground_candidate_against_holdings,
)
from ..util import EventExecutor


RELEVANCE_THRESHOLD = float(settings.RELEVANCE_MIN_SCORE)
RETRIEVAL_K = 20
FINAL_TOP_N = max(int(settings.RELEVANCE_FINAL_TOP_N), 1)

cosmos_client = build_sync_cosmos_client(settings.COSMOS_URL, settings.COSMOS_KEY)

news_container = get_container_client(
    get_database_client(cosmos_client, settings.COSMOS_DB),
    settings.NEWS_CONTAINER,
)


class StandardState(TypedDict):
    trigger_event: dict
    news_batch: list[dict]
    relevance_results: dict[str, list[dict]]
    relevance_map: list[dict]
    grounded_relevance_map: list[dict]
    generate_insight_events: list[dict]


def standard_agent_activation(state: StandardState) -> StandardState:
    print(
        f"[Standard] Activated by scheduled trigger: "
        f"{state['trigger_event'].get('job_id', 'N/A')}"
    )
    return state


def _record_news_stage(
    news_doc: dict,
    *,
    stage: str,
    status: str,
    details: dict | None = None,
) -> None:
    latest_doc = news_container.read_item(
        item=news_doc["id"],
        partition_key=news_doc.get("id"),
    )
    merge_news_monitoring(news_doc, latest_doc)
    update_news_lifecycle(news_doc, stage=stage, status=status, details=details)
    news_container.upsert_item(news_doc)
    backup_document_sync(
        settings,
        collection_name=settings.NEWS_CONTAINER,
        document=news_doc,
    )


def _parse_iso_datetime(value: object | None) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _eligible_before_iso(trigger_event: dict) -> str:
    eligible_before = (
        _parse_iso_datetime(trigger_event.get("checkpoint_end"))
        or _parse_iso_datetime(trigger_event.get("requested_at"))
        or datetime.now(timezone.utc)
    )
    return eligible_before.astimezone(timezone.utc).isoformat()


def fetch_news_batch(state: StandardState) -> StandardState:
    eligible_before = _eligible_before_iso(state["trigger_event"])
    batch_limit = max(int(settings.STANDARD_WORKFLOW_BATCH_LIMIT), 1)
    query = f"""
    SELECT TOP {batch_limit} * FROM c
    WHERE IS_DEFINED(c.monitoring.stages.retail_batch.status)
      AND c.monitoring.stages.retail_batch.status = @pending_status
      AND IS_DEFINED(c.monitoring.stages.retail_batch.timestamp)
      AND c.monitoring.stages.retail_batch.timestamp <= @eligible_before
    ORDER BY c.monitoring.stages.retail_batch.timestamp ASC
    """
    news_batch = list(
        news_container.query_items(
            query=query,
            parameters=[
                {"name": "@pending_status", "value": "pending"},
                {"name": "@eligible_before", "value": eligible_before},
            ],
            enable_cross_partition_query=True,
        )
    )
    state["news_batch"] = news_batch

    for news_doc in news_batch:
        _record_news_stage(
            news_doc,
            stage="mas_standard",
            status="processing",
            details={
                "job_id": state["trigger_event"].get("job_id"),
                "eligible_before": eligible_before,
            },
        )

    print(
        f"[Standard] Fetched {len(news_batch)} delayed news items "
        f"eligible_before={eligible_before}"
    )
    return state


def map_relevance(state: StandardState) -> StandardState:
    news_lookup = {doc["id"]: doc for doc in state["news_batch"]}
    relevance_results = process_news_stream(
        news_docs=state["news_batch"],
        retrieval_k=RETRIEVAL_K,
        final_top_n=FINAL_TOP_N,
        min_score=RELEVANCE_THRESHOLD,
        client_segments=["retail"],
    )
    relevance_map = []
    for news_id, matched_clients in relevance_results.items():
        news_doc = news_lookup.get(news_id)
        if news_doc is None:
            continue
        for client in matched_clients:
            relevance_map.append(
                {
                    "client_id": client["client_id"],
                    "client_name": client.get("client_name"),
                    "news_id": news_id,
                    "news_document": news_doc,
                    "candidate": client,
                }
            )

    state["relevance_results"] = relevance_results
    state["relevance_map"] = relevance_map
    print(f"[Standard] Relevance map: {len(relevance_map)} retail client/news pairs")
    return state


def ground_relevance(state: StandardState) -> StandardState:
    grounded_map = []
    for pair in state["relevance_map"]:
        grounding = ground_candidate_against_holdings(
            news_doc=pair["news_document"],
            candidate=pair["candidate"],
        )
        grounded_relevance = grounding.get("holding_match_summary", {}).get(
            "client_grounded_relevance",
            "none",
        )
        if grounded_relevance == "none":
            continue
        grounded_map.append({**pair, "grounding": grounding})

    state["grounded_relevance_map"] = grounded_map
    print(f"[Standard] Grounded map: {len(grounded_map)} retail client/news pairs")
    return state


def create_insight_events(state: StandardState) -> StandardState:
    events = []
    for pair in state["grounded_relevance_map"]:
        news_doc = pair["news_document"]
        candidate = pair["candidate"]
        profile = candidate.get("search_relevance_profile", {}) or {}
        grounding = pair.get("grounding", {}) or {}
        relevance = build_relevance_payload(candidate, grounding)
        compact_context = build_compact_portfolio_context_from_grounding(
            news_doc=news_doc,
            profile=profile,
            grounding=grounding,
        )
        overflow = grounding.get("overflow", {}) if isinstance(grounding, dict) else {}
        included = int(overflow.get("matched_holding_count_included", 0) or 0)
        total = int(overflow.get("matched_holding_count_total", 0) or 0)
        events.append(
            {
                "event_type": "generate_insight",
                "schema_version": "v1.2",
                "client_id": pair["client_id"],
                "client_name": pair["client_name"] or pair["client_id"],
                "news_doc_id": news_doc["id"],
                "partition_key": news_doc["id"],
                "news_title": news_doc.get("title"),
                "news_document": news_doc,
                "portfolio_snapshot": grounding.get("portfolio_snapshot", {}),
                "client_profile_summary": build_client_profile_summary(profile),
                "relevance": relevance,
                "matched_holdings": grounding.get("matched_holdings", []),
                "overflow": {
                    "omitted_matched_holdings": max(total - included, 0),
                },
                "client_portfolio_document": compact_context,
                "compact_portfolio_context": compact_context,
                "matched_tickers": candidate.get("matched_tickers", []),
                "matched_tags": candidate.get("matched_tags", []),
                "relevance_score": relevance["candidate_score"],
                "priority": "scheduled",
                "source": "mas.standard_workflow",
            }
        )
    state["generate_insight_events"] = events

    print(f"[Standard] Created {len(events)} retail insight events")

    if events:
        with EventExecutor() as executor:
            executor.publish_insight_events(events)

    queued_counts = Counter(event["news_doc_id"] for event in events)
    job_id = state["trigger_event"].get("job_id")

    for news_doc in state["news_batch"]:
        queued_events = queued_counts.get(news_doc["id"], 0)
        _record_news_stage(
            news_doc,
            stage="mas_standard",
            status="completed",
            details={"job_id": job_id, "candidate_count": queued_events},
        )
        if queued_events:
            _record_news_stage(
                news_doc,
                stage="generate_insight_queue",
                status="queued",
                details={"queued_events": queued_events, "workflow": "standard"},
            )
            _record_news_stage(
                news_doc,
                stage="retail_batch",
                status="dispatched",
                details={"job_id": job_id, "queued_events": queued_events},
            )
        else:
            _record_news_stage(
                news_doc,
                stage="retail_batch",
                status="no_matches",
                details={"job_id": job_id, "queued_events": 0},
            )

    return state


def has_news_batch(state: StandardState) -> str:
    return "map_relevance" if state.get("news_batch") else END


def build_standard_graph() -> StateGraph:
    g = StateGraph(StandardState)
    g.add_node("activate", standard_agent_activation)
    g.add_node("fetch_news", fetch_news_batch)
    g.add_node("map_relevance", map_relevance)
    g.add_node("ground_relevance", ground_relevance)
    g.add_node("create_events", create_insight_events)

    g.set_entry_point("activate")
    g.add_edge("activate", "fetch_news")
    g.add_conditional_edges(
        "fetch_news",
        has_news_batch,
        {"map_relevance": "map_relevance", END: END},
    )
    g.add_edge("map_relevance", "ground_relevance")
    g.add_edge("ground_relevance", "create_events")
    g.add_edge("create_events", END)
    return g.compile()
