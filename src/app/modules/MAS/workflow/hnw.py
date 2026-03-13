from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from azure.cosmos import CosmosClient
from elasticsearch import Elasticsearch
from ..config import process_news_stream
import os
from dotenv import load_dotenv
load_dotenv()

COSMOSDB_CONFIG = {
    "database_name": "SIMF",
    "containers": {
        "news": {
            "name": "news",
            "partition_key": "/id"
        }
    }
}

database_name = COSMOSDB_CONFIG["database_name"]
container_name = COSMOSDB_CONFIG["containers"]["news"]["name"]

cosmos_client = CosmosClient(
    url=os.getenv("COSMOS_URL"),
    credential=os.getenv("COSMOS_KEY"),
    connection_verify=False
)
cosmos_container = (
    cosmos_client
    .get_database_client(database_name)
    .get_container_client(container_name)
)

es_client = Elasticsearch("http://localhost:9200", verify_certs=False)

class HNWState(TypedDict):
    event_data: dict                        # raw trigger event (contains news_doc_id)
    news_doc: Optional[dict]                # full news document fetched from CosmosDB
    relevance_results: dict[str, list[dict]]  # { news_id -> [matched clients] }
    candidate_clients: list[dict]           # matched clients above threshold
    generate_insight_events: list[dict]     # output events

RELEVANCE_THRESHOLD = 0.6

def hnw_agent_activation(state: HNWState) -> HNWState:
    print(f"[HNW] Activated with event: {state['event_data']}")
    return state


def fetch_news_document(state: HNWState) -> HNWState:
    news_doc_id = state["event_data"]["news_doc_id"]
    partition_key = state["event_data"].get("partition_key", news_doc_id)
    doc = cosmos_container.read_item(item=news_doc_id, partition_key=partition_key)
    state["news_doc"] = doc
    print(f"[HNW] Fetched news doc '{news_doc_id}' from CosmosDB: {doc.get('title', '')[:60]}")
    return state


def score_relevance(state: HNWState) -> HNWState:
    news_doc = state["news_doc"]
    relevance_results = process_news_stream(
        news_docs=[news_doc],
        top_k=20,
        min_score=RELEVANCE_THRESHOLD,
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
            if cid not in seen and client["relevance_score"] >= RELEVANCE_THRESHOLD:
                seen.add(cid)
                candidates.append(client)

    state["candidate_clients"] = candidates
    print(f"[HNW] Candidates above threshold ({RELEVANCE_THRESHOLD}): "
          f"{[c['client_id'] for c in candidates]}")
    return state


def create_insight_events(state: HNWState) -> HNWState:
    """
    Emit one insight event per candidate client, enriched with the
    matched ISINs / tags returned by the scoring step.
    """
    news_doc = state["news_doc"]
    state["generate_insight_events"] = [
        {
            "client_id":      client["client_id"],
            "client_name":    client.get("client_name"),
            "news_doc_id":    news_doc["id"],
            "news_title":     news_doc.get("title"),
            "relevance_score": client["relevance_score"],
            "matched_isins":  client.get("matched_isins", []),
            "matched_tags":   client.get("matched_tags", []),
            "priority":       "realtime",
        }
        for client in state["candidate_clients"]
    ]

    print(f"[HNW] Created {len(state['generate_insight_events'])} insight event(s)")
    return state

def has_news_doc(state: HNWState) -> str:
    return "score" if state.get("news_doc") else END

def build_hnw_graph() -> StateGraph:
    g = StateGraph(HNWState)

    g.add_node("activate",       hnw_agent_activation)
    g.add_node("fetch_news",     fetch_news_document)
    g.add_node("score",          score_relevance)
    g.add_node("filter",         filter_candidates)
    g.add_node("create_events",  create_insight_events)

    g.set_entry_point("activate")
    g.add_edge("activate",      "fetch_news")

    g.add_conditional_edges("fetch_news", has_news_doc, {"score": "score", END: END})

    g.add_edge("score",          "filter")
    g.add_edge("filter",         "create_events")
    g.add_edge("create_events",  END)

    return g.compile()


def run_hnw_workflow(event_data: dict) -> list[dict]:
    """
    Invoke the compiled graph with a trigger event.

    event_data must contain at minimum:
        {
            "news_doc_id":   "<CosmosDB document id>",
            "partition_key": "<partition key>"   # optional, defaults to news_doc_id
        }
    """
    graph = build_hnw_graph()
    initial_state: HNWState = {
        "event_data":             event_data,
        "news_doc":               None,
        "relevance_results":      {},
        "candidate_clients":      [],
        "generate_insight_events": [],
    }

    final_state = graph.invoke(initial_state)
    return final_state["generate_insight_events"]