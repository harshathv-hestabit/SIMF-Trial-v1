from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END

from ..agents.insight_generator import generate_insight_agent
from ..agents.verifier import verify_insight_agent
from ..util.update_db import update_db

class InsightState(TypedDict):
    client_id: str
    news_document: dict
    client_portfolio_document: dict     
    insight_draft: str         
    verification_score: float  
    verification_feedback: str # feedback for next iteration
    iterations: int
    status: str                # "pending" | "verified" | "failed"

SCORE_THRESHOLD = 75.0
MAX_ITERATIONS = 4

async def generate_insight(state):
    insight = await generate_insight_agent(state)
    state["insight_draft"] = insight
    state["iterations"] += 1
    return state

async def verify_insight(state):
    result = await verify_insight_agent(state)
    state["verification_score"] = result["score"]
    state["verification_feedback"] = result["feedback"]
    return state

async def save_insight(state):
    await update_db(state)
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