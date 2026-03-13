from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

class InsightState(TypedDict):
    client_id: str
    news_event: dict
    client_portfolio: dict     # fetched from context
    insight_draft: str         # current draft
    verification_score: float  # 0–100
    verification_feedback: str # feedback for next iteration
    iterations: int
    status: str                # "pending" | "verified" | "failed"

SCORE_THRESHOLD = 75.0
MAX_ITERATIONS = 3

def generate_insight(state: InsightState) -> InsightState:
    feedback_clause = (
        f" Previous feedback: {state['verification_feedback']}"
        if state["verification_feedback"] else ""
    )
    state["insight_draft"] = (
        f"[Draft v{state['iterations'] + 1}] Based on '{state['news_event'].get('title')}', "
        f"your portfolio may be impacted.{feedback_clause}"
    )
    state["iterations"] += 1
    print(f"[Insight] Iteration {state['iterations']} — draft generated")
    return state

def verify_insight(state: InsightState) -> InsightState:
    state["verification_score"] = min(60.0 + state["iterations"] * 15, 100.0)
    state["verification_feedback"] = (
        "" if state["verification_score"] >= SCORE_THRESHOLD
        else "Improve actionability and personalise holdings reference."
    )
    print(f"[Verifier] Score: {state['verification_score']} (threshold: {SCORE_THRESHOLD})")
    return state

def save_insight(state: InsightState) -> InsightState:
    print(f"[DB] Insight saved for client {state['client_id']}: {state['insight_draft']}")
    state["status"] = "verified"
    return state

def log_failure(state: InsightState) -> InsightState:
    print(f"[Monitor] FAILED — max iterations reached for client {state['client_id']}")
    state["status"] = "failed"
    return state

def route_after_verification(state: InsightState) -> str:
    if state["verification_score"] >= SCORE_THRESHOLD:
        return "save"
    if state["iterations"] >= MAX_ITERATIONS:
        return "fail"
    return "regenerate"

def build_insight_graph() -> StateGraph:
    g = StateGraph(InsightState)
    g.add_node("generate", generate_insight)
    g.add_node("verify",   verify_insight)
    g.add_node("save",     save_insight)
    g.add_node("fail",     log_failure)

    g.set_entry_point("generate")
    g.add_edge("generate", "verify")
    g.add_conditional_edges(
        "verify",
        route_after_verification,
        {
            "save":       "save",
            "fail":       "fail",
            "regenerate": "generate",
        },
    )
    g.add_edge("save", END)
    g.add_edge("fail", END)
    return g.compile()

if __name__ == "__main__":
    graph = build_insight_graph()
    result = graph.invoke({
        "client_id": "hnw_001",
        "news_event": {"title": "Apple earnings beat expectations", "tickers": ["AAPL"]},
        "client_portfolio": {"holdings": ["AAPL", "MSFT"]},
        "insight_draft": "",
        "verification_score": 0.0,
        "verification_feedback": "",
        "iterations": 0,
        "status": "pending",
    })
    print(f"\nFinal status : {result['status']}")
    print(f"Final insight: {result['insight_draft']}")
    print(f"Final score  : {result['verification_score']}")