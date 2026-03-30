import json
from langchain_core.messages import HumanMessage
from ..config import get_llm

llm = get_llm()

async def verify_insight_agent(state: dict) -> dict:
    news = state["news_document"]
    portfolio = state["client_portfolio_document"]
    insight = state["insight_draft"]

    prompt = f"""
You are a financial insight quality evaluator.

NEWS EVENT
Title: {news.get("title")}
Content: {news.get("content")}

CLIENT PORTFOLIO
Holdings: {portfolio}

GENERATED INSIGHT
{insight}

TASK
Evaluate the insight using these criteria:

1. Relevance to client's holdings
2. Accuracy of reasoning
3. Clarity and usefulness
4. Actionability

Return ONLY JSON in this format:

{{
 "score": number between 0 and 100,
 "feedback": "specific improvement suggestions"
}}
"""

    response_text = await llm.call_text([
        HumanMessage(content=prompt)
    ])

    try:
        result = json.loads(response_text)
    except Exception:
        result = {
            "score": 0,
            "feedback": "Verifier output parsing failed"
        }

    return result
