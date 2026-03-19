# from typing import TypedDict, Optional
# from langgraph.graph import StateGraph, END
# from azure.cosmos import CosmosClient
# from elasticsearch import Elasticsearch
# from ..config import process_news_stream
# from ..util import EventExecutor
# import os
# from dotenv import load_dotenv
# load_dotenv()

# COSMOSDB_CONFIG = {
#     "database_name": "SMIF",
#     "containers": {
#         "news": {
#             "name": "news",
#             "partition_key": "/id"
#         }
#     }
# }

# database_name = COSMOSDB_CONFIG["database_name"]
# container_name = COSMOSDB_CONFIG["containers"]["news"]["name"]

# cosmos_client = CosmosClient(
#     url=os.getenv("COSMOS_URL"),
#     credential=os.getenv("COSMOS_KEY"),
#     connection_verify=False
# )
# cosmos_container = (
#     cosmos_client
#     .get_database_client(database_name)
#     .get_container_client(container_name)
# )

# es_client = Elasticsearch("http://localhost:9200", verify_certs=False)

# class HNWState(TypedDict):
#     event_data: dict                        # raw trigger event (contains news_doc_id)
#     news_doc: Optional[dict]                # full news document fetched from CosmosDB
#     relevance_results: dict[str, list[dict]]  # { news_id -> [matched clients] }
#     candidate_clients: list[dict]           # matched clients above threshold
#     generate_insight_events: list[dict]     # output events

# RELEVANCE_THRESHOLD = 0.6

# def hnw_agent_activation(state: HNWState) -> HNWState:
#     print(f"[HNW] Activated with event: {state['event_data']}")
#     return state


# def fetch_news_document(state: HNWState) -> HNWState:
#     news_doc_id = state["event_data"]["news_doc_id"]
#     partition_key = state["event_data"].get("partition_key", news_doc_id)
#     doc = cosmos_container.read_item(item=news_doc_id, partition_key=partition_key)
#     state["news_doc"] = doc
#     print(f"[HNW] Fetched news doc '{news_doc_id}' from CosmosDB: {doc.get('title', '')[:60]}")
#     return state


# def score_relevance(state: HNWState) -> HNWState:
#     news_doc = state["news_doc"]
#     relevance_results = process_news_stream(
#         news_docs=[news_doc],
#         top_k=20,
#         min_score=RELEVANCE_THRESHOLD,
#     )

#     state["relevance_results"] = relevance_results
#     print(f"[HNW] Relevance results for {len(relevance_results)} news item(s)")
#     return state


# def filter_candidates(state: HNWState) -> HNWState:
#     seen: set[str] = set()
#     candidates: list[dict] = []

#     for matched_clients in state["relevance_results"].values():
#         for client in matched_clients:
#             cid = client["client_id"]
#             if cid not in seen and client["relevance_score"] >= RELEVANCE_THRESHOLD:
#                 seen.add(cid)
#                 candidates.append(client)

#     state["candidate_clients"] = candidates
#     print(f"[HNW] Candidates above threshold ({RELEVANCE_THRESHOLD}): "
#           f"{[c['client_id'] for c in candidates]}")
#     return state

# def create_insight_events(state: HNWState) -> HNWState:
#     news_doc = state["news_doc"]
#     state["generate_insight_events"] = [
#         {
#             "client_id":       client["client_id"],
#             "client_name":     client.get("client_name"),
#             "news_doc_id":     news_doc["id"],
#             "news_title":      news_doc.get("title"),
#             "relevance_score": client["relevance_score"],
#             "matched_isins":   client.get("matched_isins", []),
#             "matched_tags":    client.get("matched_tags", []),
#             "priority":        "realtime",
#         }
#         for client in state["candidate_clients"]
#     ]

#     print(f"[HNW] Created {len(state['generate_insight_events'])} insight event(s)")
#     with EventExecutor() as event_executor:
#         event_executor.publish_insight_events(state["generate_insight_events"])

#     return state

# def has_news_doc(state: HNWState) -> str:
#     return "score" if state.get("news_doc") else END

# def build_hnw_graph() -> StateGraph:
#     g = StateGraph(HNWState)

#     g.add_node("activate",       hnw_agent_activation)
#     g.add_node("fetch_news",     fetch_news_document)
#     g.add_node("score",          score_relevance)
#     g.add_node("filter",         filter_candidates)
#     g.add_node("create_events",  create_insight_events)

#     g.set_entry_point("activate")
#     g.add_edge("activate",      "fetch_news")

#     g.add_conditional_edges("fetch_news", has_news_doc, {"score": "score", END: END})

#     g.add_edge("score",          "filter")
#     g.add_edge("filter",         "create_events")
#     g.add_edge("create_events",  END)

#     return g.compile()

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from azure.cosmos import CosmosClient
from elasticsearch import Elasticsearch
from ..config import process_news_stream, settings
from ..util import EventExecutor

cosmos_client = CosmosClient(
    url=settings.COSMOS_URL,
    credential=settings.COSMOS_KEY,
    connection_verify=False,
    enable_endpoint_discovery=False,
    connection_timeout=5,
)

news_container = (
    cosmos_client
    .get_database_client(settings.COSMOS_DB)
    .get_container_client(settings.NEWS_CONTAINER)
)

client_container = (
    cosmos_client
    .get_database_client(settings.COSMOS_DB)
    .get_container_client(settings.CLIENT_PORTFOLIO_CONTAINER)
)

es_client = Elasticsearch("http://localhost:9200", verify_certs=False)

class HNWState(TypedDict):
    event_data: dict
    news_doc: Optional[dict]
    relevance_results: dict[str, list[dict]]
    candidate_clients: list[dict]
    client_documents: dict[str, dict]
    generate_insight_events: list[dict]

RELEVANCE_THRESHOLD = 0.7

def hnw_agent_activation(state: HNWState) -> HNWState:
    print(f"[HNW] Activated with event: {state['event_data']}")
    return state

def fetch_news_document(state: HNWState) -> HNWState:
    news_doc_id = state["event_data"]["news_doc_id"]
    partition_key = state["event_data"].get("partition_key", news_doc_id)
    print("I AM HERE")
    doc = news_container.read_item(item=news_doc_id, partition_key=partition_key)
    state["news_doc"] = doc

    print(f"[HNW] Fetched news doc '{news_doc_id}': {doc.get('title', '')[:60]}")
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

    print(f"[HNW] Candidates: {[c['client_id'] for c in candidates]}")
    return state

def fetch_client_documents(state: HNWState) -> HNWState:
    client_docs: dict[str, dict] = {}
    for client in state["candidate_clients"]:
        cid = client["client_id"]
        try:
            doc = client_container.read_item(item=cid, partition_key=cid)
            client_docs[cid] = doc
        except Exception as e:
            print(f"[HNW] Failed to fetch client {cid}: {e}")
    state["client_documents"] = client_docs

    print(f"[HNW] Fetched {len(client_docs)} client documents")
    return state

def create_insight_events(state: HNWState) -> HNWState:
    news_doc = state["news_doc"]
    client_docs = state["client_documents"]
    events = []
    for client in state["candidate_clients"]:
        cid = client["client_id"]
        client_doc = client_docs.get(cid, {})
        events.append({
            "client_id": cid,
            "client_name": client.get("client_name"),

            "news_doc_id": news_doc["id"],
            "news_title": news_doc.get("title"),
            "news_document": news_doc,                 # FULL DOC (your choice… brave)

            "client_portfolio_document": client_doc,             # FULL CLIENT DOC

            "relevance_score": client["relevance_score"],
            "matched_isins": client.get("matched_isins", []),
            "matched_tags": client.get("matched_tags", []),

            "priority": "realtime",
        })
    state["generate_insight_events"] = events

    print(f"[HNW] Created {len(events)} insight events")

    with EventExecutor() as executor:
        executor.publish_insight_events(events)

    return state

def has_news_doc(state: HNWState) -> str:
    print(state.get("news_doc"))
    return "score" if state.get("news_doc") else END

def build_hnw_graph() -> StateGraph:
    g = StateGraph(HNWState)

    g.add_node("activate", hnw_agent_activation)
    g.add_node("fetch_news", fetch_news_document)
    g.add_node("score", score_relevance)
    g.add_node("filter", filter_candidates)
    g.add_node("fetch_clients", fetch_client_documents)   
    g.add_node("create_events", create_insight_events)

    g.set_entry_point("activate")

    g.add_edge("activate", "fetch_news")

    g.add_conditional_edges(
        "fetch_news",
        has_news_doc,
        {"score": "score", END: END}
    )

    g.add_edge("score", "filter")
    g.add_edge("filter", "fetch_clients")    
    g.add_edge("fetch_clients", "create_events")
    g.add_edge("create_events", END)

    return g.compile()