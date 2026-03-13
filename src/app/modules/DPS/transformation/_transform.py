import uuid
from datetime import datetime


def preprocess_news(raw_doc: dict) -> dict:
    """
    Preprocess a raw EODHD news document into the internal news model schema.

    Raw EODHD fields:
        date, title, content, link, symbols, tags, sentiment,
        _fetched_at, _query_symbol
    """
    # Derive source domain from the article link, e.g. "u.today"
    link = raw_doc.get("link", "")
    source = _extract_domain(link) if link else "unknown"

    processed_doc = {
        # Identity
        "id": str(uuid.uuid4()),
        "type": "news",

        # Content
        "title": raw_doc.get("title", ""),
        "content": raw_doc.get("content", ""),
        "link": link,

        # Classification
        "symbols": raw_doc.get("symbols", []),       # e.g. ["AAPL.US", "TSLA.US"]
        "tags": raw_doc.get("tags", []),              # e.g. ["BITCOIN", "EARNINGS"]

        # Sentiment scores (polarity, neg, neu, pos)
        "sentiment": raw_doc.get("sentiment", {
            "polarity": 0.0,
            "neg": 0.0,
            "neu": 1.0,
            "pos": 0.0,
        }),

        # Source & timestamps
        "source": source,
        "published_at": raw_doc.get("date"),          # ISO 8601 from EODHD
        "fetched_at": raw_doc.get("_fetched_at"),     # set during fetch
        "query_symbol": raw_doc.get("_query_symbol"), # which symbol triggered this fetch
        "processed_at": datetime.now().isoformat(),
    }

    return processed_doc


def _extract_domain(url: str) -> str:
    """Extract the domain from a URL to use as the news source label."""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc  # e.g. "u.today", "www.reuters.com"
    except Exception:
        return "unknown"