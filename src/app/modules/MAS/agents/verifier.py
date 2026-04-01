import json
from langchain_core.messages import HumanMessage
from ..config import get_llm
from ..util.insight_logging import append_insight_log

llm = get_llm()


def _record_token_usage(state: dict, *, agent: str, usage: dict) -> None:
    token_usage = state.setdefault(
        "token_usage",
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": [],
        },
    )
    token_usage["prompt_tokens"] = int(token_usage.get("prompt_tokens", 0)) + int(
        usage.get("prompt_tokens", 0)
    )
    token_usage["completion_tokens"] = int(token_usage.get("completion_tokens", 0)) + int(
        usage.get("completion_tokens", 0)
    )
    token_usage["total_tokens"] = int(token_usage.get("total_tokens", 0)) + int(
        usage.get("total_tokens", 0)
    )
    token_usage.setdefault("calls", []).append(
        {
            "agent": agent,
            "iteration": state.get("iterations", 0),
            **usage,
        }
    )


async def verify_insight_agent(state: dict) -> dict:
    news = state["news_document"]
    portfolio = state["client_portfolio_document"]
    insight = state["insight_draft"]

    prompt = f"""
        You are a financial insight quality evaluator.

        NEWS DOCUMENT
            Title: {news.get("title")}
            Teaser: {news.get("teaser")}
            Symbols: {news.get("symbols")}
            Tags: {news.get("tags")}
            Published At: {news.get("published_at")}
            Updated At: {news.get("updated_at")}
                
        CLIENT PORTFOLIO PROFILE
            Client Type: {portfolio.get("client_type")}
            Mandate: {portfolio.get("mandate")}
            Total AUM (aed): {portfolio.get("total_aum_aed")}
            Asset Types: {portfolio.get("asset_types")}
            Asset Subtypes: {portfolio.get("asset_subtypes")}
            Asset Classifications: {portfolio.get("asset_classifications")}
            Currencies: {portfolio.get("currencies")}
            ISINS: {portfolio.get("isins")}
            Tickers: {portfolio.get("ticker_symbols")}
            Asset Descriptions: {portfolio.get("asset_descriptions")}
            Clasification Weights: {portfolio.get("classification_weights")}
            Asset Type Weights: {portfolio.get("asset_type_weights")}

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
    append_insight_log(
        state.get("log_file_path"),
        event="agent_prompt_saved",
        payload={
            "agent": "verifier",
            "iteration": state.get("iterations", 0),
            "prompt": prompt,
        },
    )

    result = await llm.call_text_with_usage([
        HumanMessage(content=prompt)
    ])

    usage = {
        "backend": result.backend_name,
        "provider": result.backend_provider,
        "model": result.backend_model,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "raw_usage": result.raw_usage,
    }
    _record_token_usage(state, agent="verifier", usage=usage)
    append_insight_log(
        state.get("log_file_path"),
        event="agent_token_usage",
        payload={
            "agent": "verifier",
            "iteration": state.get("iterations", 0),
            **usage,
        },
    )

    response_text = result.text

    try:
        parsed = json.loads(response_text)
    except Exception:
        parsed = {
            "score": 0,
            "feedback": "Verifier output parsing failed"
        }

    return parsed
