from typing import TypedDict
from langgraph.graph import StateGraph, END

from ..agents.insight_generator import generate_insight_agent
from ..agents.verifier import verify_insight_agent
from ..util.insight_logging import append_insight_log
from ..util.update_db import update_db


class InsightState(TypedDict):
    client_id: str
    news_document: dict
    client_portfolio_document: dict
    job_key: str
    log_file_path: str
    insight_draft: str
    verification_score: float
    verification_feedback: str
    iterations: int
    status: str
    token_usage: dict


SCORE_THRESHOLD = 75.0
MAX_ITERATIONS = 3


async def generate_insight(state):
    append_insight_log(
        state.get("log_file_path"),
        event="agent_invoked",
        payload={
            "agent": "insight_generator",
            "next_iteration": state.get("iterations", 0) + 1,
        },
    )
    insight = await generate_insight_agent(state)
    state["insight_draft"] = insight
    state["iterations"] += 1
    append_insight_log(
        state.get("log_file_path"),
        event="agent_completed",
        payload={
            "agent": "insight_generator",
            "iteration": state["iterations"],
            "insight_draft": insight,
        },
    )
    return state


async def verify_insight(state):
    append_insight_log(
        state.get("log_file_path"),
        event="agent_invoked",
        payload={
            "agent": "verifier",
            "iteration": state.get("iterations", 0),
        },
    )
    result = await verify_insight_agent(state)
    state["verification_score"] = result["score"]
    state["verification_feedback"] = result["feedback"]
    append_insight_log(
        state.get("log_file_path"),
        event="agent_completed",
        payload={
            "agent": "verifier",
            "iteration": state.get("iterations", 0),
            "score": result["score"],
            "feedback": result["feedback"],
        },
    )
    return state


async def save_insight(state):
    state["status"] = "verified"
    append_insight_log(
        state.get("log_file_path"),
        event="insight_persist_started",
        payload={
            "iteration": state.get("iterations", 0),
            "status": state["status"],
            "token_usage": state.get("token_usage", {}),
        },
    )
    await update_db(state)
    append_insight_log(
        state.get("log_file_path"),
        event="insight_persist_completed",
        payload={
            "iteration": state.get("iterations", 0),
            "status": state["status"],
            "token_usage": state.get("token_usage", {}),
        },
    )
    return state


def log_failure(state: InsightState) -> InsightState:
    print(f"[Monitor] FAILED - max iterations reached for client {state['client_id']}. Feedback: {state['verification_feedback']}")
    state["status"] = "failed"
    append_insight_log(
        state.get("log_file_path"),
        event="workflow_failed",
        payload={
            "iteration": state.get("iterations", 0),
            "feedback": state.get("verification_feedback", ""),
            "token_usage": state.get("token_usage", {}),
        },
    )
    return state


def route_after_verification(state: InsightState) -> str:
    if state["verification_score"] >= SCORE_THRESHOLD:
        append_insight_log(
            state.get("log_file_path"),
            event="verification_routed",
            payload={
                "decision": "save",
                "score": state["verification_score"],
                "threshold": SCORE_THRESHOLD,
            },
        )
        return "save"
    if state["iterations"] >= MAX_ITERATIONS:
        append_insight_log(
            state.get("log_file_path"),
            event="verification_routed",
            payload={
                "decision": "fail",
                "score": state["verification_score"],
                "threshold": SCORE_THRESHOLD,
                "iterations": state["iterations"],
            },
        )
        return "fail"
    append_insight_log(
        state.get("log_file_path"),
        event="verification_routed",
        payload={
            "decision": "regenerate",
            "score": state["verification_score"],
            "threshold": SCORE_THRESHOLD,
            "iterations": state["iterations"],
            "feedback": state.get("verification_feedback", ""),
        },
    )
    return "regenerate"


def build_insight_graph() -> StateGraph:
    g = StateGraph(InsightState)
    g.add_node("generate", generate_insight)
    g.add_node("verify", verify_insight)
    g.add_node("save", save_insight)
    g.add_node("fail", log_failure)

    g.set_entry_point("generate")
    g.add_edge("generate", "verify")
    g.add_conditional_edges(
        "verify",
        route_after_verification,
        {
            "save": "save",
            "fail": "fail",
            "regenerate": "generate",
        },
    )
    g.add_edge("save", END)
    g.add_edge("fail", END)
    return g.compile()
