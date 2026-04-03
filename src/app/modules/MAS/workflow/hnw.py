from typing import Optional, TypedDict

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

cosmos_client = build_sync_cosmos_client(settings.COSMOS_URL, settings.COSMOS_KEY)

news_container = get_container_client(
    get_database_client(cosmos_client, settings.COSMOS_DB),
    settings.NEWS_CONTAINER,
)


class HNWState(TypedDict):
    event_data: dict
    news_doc: Optional[dict]
    relevance_results: dict[str, list[dict]]
    candidate_clients: list[dict]
    grounded_candidates: list[dict]
    generate_insight_events: list[dict]


RELEVANCE_THRESHOLD = float(settings.HNW_RELEVANCE_MIN_SCORE)
RETRIEVAL_K = 20
FINAL_TOP_N = max(int(settings.HNW_RELEVANCE_FINAL_TOP_N), 1)


def hnw_agent_activation(state: HNWState) -> HNWState:
    print(f"[HNW] Activated with event: {state['event_data']}")
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


def fetch_news_document(state: HNWState) -> HNWState:
    news_doc_id = state["event_data"]["news_doc_id"]
    partition_key = state["event_data"].get("partition_key", news_doc_id)
    doc = news_container.read_item(item=news_doc_id, partition_key=partition_key)
    state["news_doc"] = doc
    _record_news_stage(
        doc,
        stage="mas_hnw",
        status="processing",
        details={"source_queue": state["event_data"].get("queue_name", "unknown")},
    )

    print(f"[HNW] Fetched news doc '{news_doc_id}': {doc.get('title', '')[:60]}")
    return state


def score_relevance(state: HNWState) -> HNWState:
    news_doc = state["news_doc"]
    relevance_results = process_news_stream(
        news_docs=[news_doc],
        retrieval_k=RETRIEVAL_K,
        final_top_n=FINAL_TOP_N,
        min_score=RELEVANCE_THRESHOLD,
        client_segments=["hnw"],
    )
    state["relevance_results"] = relevance_results

    print(f"[HNW] Relevance results for {len(relevance_results)} news item(s)")
    return state


def filter_candidates(state: HNWState) -> HNWState:
    seen: set[str] = set()
    candidates: list[dict] = []
    for matched_clients in state["relevance_results"].values():
        for client in matched_clients:
            cid = client["client_id"]

            if cid not in seen:
                seen.add(cid)
                candidates.append(client)
    state["candidate_clients"] = candidates

    print(f"[HNW] Candidates: {[c['client_id'] for c in candidates]}")
    return state


def ground_candidates(state: HNWState) -> HNWState:
    news_doc = state["news_doc"]
    grounded: list[dict] = []
    for candidate in state["candidate_clients"]:
        grounding = ground_candidate_against_holdings(
            news_doc=news_doc,
            candidate=candidate,
        )
        grounded_relevance = grounding.get("holding_match_summary", {}).get(
            "client_grounded_relevance",
            "none",
        )
        if grounded_relevance == "none":
            continue
        grounded.append({**candidate, "grounding": grounding})

    state["grounded_candidates"] = grounded
    print(f"[HNW] Grounded candidates: {[c['client_id'] for c in grounded]}")
    return state


def create_insight_events(state: HNWState) -> HNWState:
    news_doc = state["news_doc"]
    events = []
    for client in state["grounded_candidates"]:
        cid = client["client_id"]
        profile = client.get("search_relevance_profile", {}) or {}
        grounding = client.get("grounding", {}) or {}
        relevance = build_relevance_payload(client, grounding)
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
                "client_id": cid,
                "client_name": client.get("client_name"),
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
                "matched_tickers": client.get("matched_tickers", []),
                "matched_tags": client.get("matched_tags", []),
                "relevance_score": relevance["candidate_score"],
                "priority": "realtime",
                "source": "mas.hnw_workflow",
            }
        )
    state["generate_insight_events"] = events

    print(f"[HNW] Created {len(events)} insight events")

    if events:
        _record_news_stage(
            news_doc,
            stage="mas_hnw",
            status="completed",
            details={"candidate_count": len(events)},
        )
        with EventExecutor() as executor:
            executor.publish_insight_events(events)
        _record_news_stage(
            news_doc,
            stage="generate_insight_queue",
            status="queued",
            details={"queued_events": len(events)},
        )
    else:
        _record_news_stage(
            news_doc,
            stage="mas_hnw",
            status="completed",
            details={"candidate_count": 0},
        )

    return state


def has_news_doc(state: HNWState) -> str:
    return "score" if state.get("news_doc") else END


def build_hnw_graph() -> StateGraph:
    g = StateGraph(HNWState)

    g.add_node("activate", hnw_agent_activation)
    g.add_node("fetch_news", fetch_news_document)
    g.add_node("score", score_relevance)
    g.add_node("filter", filter_candidates)
    g.add_node("ground", ground_candidates)
    g.add_node("create_events", create_insight_events)

    g.set_entry_point("activate")

    g.add_edge("activate", "fetch_news")

    g.add_conditional_edges(
        "fetch_news",
        has_news_doc,
        {"score": "score", END: END},
    )

    g.add_edge("score", "filter")
    g.add_edge("filter", "ground")
    g.add_edge("ground", "create_events")
    g.add_edge("create_events", END)

    return g.compile()
