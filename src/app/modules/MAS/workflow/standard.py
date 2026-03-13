from typing import TypedDict, List
from langgraph.graph import StateGraph, END

class StandardState(TypedDict):
    trigger_event: dict            # scheduled job metadata
    news_batch: List[dict]         # accumulated news from data lake
    client_portfolios: List[dict]  # retrieved via MCP
    relevance_map: List[dict]      # list of {client_id, news_item} pairs above threshold
    generate_insight_events: List[dict]

RELEVANCE_THRESHOLD = 0.5

def standard_agent_activation(state: StandardState) -> StandardState:
    print(f"[Standard] Activated by scheduled trigger: {state['trigger_event'].get('job_id', 'N/A')}")
    return state

def fetch_news_batch(state: StandardState) -> StandardState:
    state["news_batch"] = [
        {"id": "n1", "title": "Fed holds rates steady", "tickers": ["SPY"]},
        {"id": "n2", "title": "Tesla recall announced",  "tickers": ["TSLA"]},
    ]
    print(f"[Standard] Fetched {len(state['news_batch'])} news items")
    return state

def retrieve_portfolios(state: StandardState) -> StandardState:
    state["client_portfolios"] = [
        {"client_id": "std_001", "holdings": ["SPY", "BND"]},
        {"client_id": "std_002", "holdings": ["TSLA", "AMZN"]},
        {"client_id": "std_003", "holdings": ["AAPL", "GOOGL"]},
    ]
    print(f"[Standard] Retrieved {len(state['client_portfolios'])} portfolios")
    return state

def map_relevance(state: StandardState) -> StandardState:
    pairs = []
    for news in state["news_batch"]:
        for client in state["client_portfolios"]:
            overlap = set(news["tickers"]) & set(client["holdings"])
            score = 0.9 if overlap else 0.2
            if score >= RELEVANCE_THRESHOLD:
                pairs.append({"client_id": client["client_id"], "news_id": news["id"],
                               "news": news, "score": score})
    state["relevance_map"] = pairs
    print(f"[Standard] Relevance map: {len(pairs)} pairs above threshold")
    return state

def create_insight_events(state: StandardState) -> StandardState:
    state["generate_insight_events"] = [
        {"client_id": p["client_id"], "news_event": p["news"], "priority": "batch"}
        for p in state["relevance_map"]
    ]
    print(f"[Standard] Created {len(state['generate_insight_events'])} insight events")
    return state

def build_standard_graph() -> StateGraph:
    g = StateGraph(StandardState)
    g.add_node("activate",      standard_agent_activation)
    g.add_node("fetch_news",    fetch_news_batch)
    g.add_node("retrieve",      retrieve_portfolios)
    g.add_node("map_relevance", map_relevance)
    g.add_node("create_events", create_insight_events)

    g.set_entry_point("activate")
    g.add_edge("activate",      "fetch_news")
    g.add_edge("fetch_news",    "retrieve")
    g.add_edge("retrieve",      "map_relevance")
    g.add_edge("map_relevance", "create_events")
    g.add_edge("create_events", END)
    return g.compile()

if __name__ == "__main__":
    graph = build_standard_graph()
    result = graph.invoke({
        "trigger_event": {"job_id": "sched_20240315_0900"},
        "news_batch": [],
        "client_portfolios": [],
        "relevance_map": [],
        "generate_insight_events": [],
    })
    print("\nFinal insight events:", result["generate_insight_events"])