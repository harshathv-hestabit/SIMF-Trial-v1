from langchain_core.messages import HumanMessage
from ..config import get_llm

llm = get_llm()

async def generate_insight_agent(state: dict) -> str:
    news = state["news_document"]
    portfolio = state["client_portfolio_document"]
    feedback = state.get("verification_feedback", "")

    prompt = f"""
You are a financial insights assistant.

NEWS EVENT
Title: {news.get("title")}
Content: {news.get("content")}

CLIENT PORTFOLIO
Holdings: {portfolio}

PREVIOUS VERIFICATION FEEDBACK
{feedback}

TASK
Generate a concise personalized investment insight explaining:
1. Why this news matters to the client's holdings
2. Potential impact
3. A possible action or monitoring suggestion

Keep it under 120 words.
"""

    text = await llm.call_text([
        HumanMessage(content=prompt)
    ])

    return text
