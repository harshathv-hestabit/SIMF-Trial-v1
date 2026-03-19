import json
import os
import time
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

NEWS_URL = "https://eodhd.com/api/news"
SENTIMENT_URL = "https://eodhd.com/api/sentiments"
WORD_WEIGHTS_URL = "https://eodhd.com/api/news-word-weights"
SAVE_PATH="src/app/modules/DPS/news_raw"

def fetch_news(
    api_key: str,
    symbol: str | None = None,
    tag: str | None = None,
    limit: int = 50,
    offset: int = 0,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """
    Fetch news articles from the EODHD /api/news endpoint.

    Either `symbol` (e.g. "AAPL.US") or `tag` (e.g. "earnings report") is required.
    Symbols must include the exchange suffix: AAPL.US, BTC-USD.CC, EURUSD.FOREX, etc.

    Returns a list of article dicts on success, raises on HTTP / API errors.
    """
    if not symbol and not tag:
        raise ValueError("At least one of `symbol` (s) or `tag` (t) must be provided.")

    params: dict = {
        "api_token": api_key,
        "fmt": "json",
        "limit": min(max(1, limit), 1000),
        "offset": offset,
    }

    if symbol:
        params["s"] = symbol  # e.g. "AAPL.US", "BTC-USD.CC"
    if tag:
        params["t"] = tag    # e.g. "earnings report", "ARTIFICIAL INTELLIGENCE"
    if from_date:
        params["from"] = from_date  # YYYY-MM-DD
    if to_date:
        params["to"] = to_date      # YYYY-MM-DD

    log.info(
        "GET %s  params=%s",
        NEWS_URL,
        {k: v for k, v in params.items() if k != "api_token"},
    )

    response = requests.get(NEWS_URL, params=params, timeout=30)

    if response.status_code == 401:
        raise ValueError("Invalid API key — check your EODHD_API_KEY.")
    if response.status_code == 429:
        raise RuntimeError("Rate limit exceeded. Wait and retry.")
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected response format: {type(data)}")

    return data


def fetch_sentiment(
    api_key: str,
    symbols: list[str],
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """
    Fetch daily sentiment scores for one or more tickers.

    `symbols` — list of tickers with exchange suffix, e.g. ["AAPL.US", "BTC-USD.CC"]
    Returns a dict keyed by ticker symbol.
    """
    if not symbols:
        raise ValueError("`symbols` must not be empty.")

    params: dict = {
        "api_token": api_key,
        "fmt": "json",
        "s": ",".join(symbols),
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    log.info(
        "GET %s  params=%s",
        SENTIMENT_URL,
        {k: v for k, v in params.items() if k != "api_token"},
    )

    response = requests.get(SENTIMENT_URL, params=params, timeout=30)

    if response.status_code == 401:
        raise ValueError("Invalid API key — check your EODHD_API_KEY.")
    response.raise_for_status()

    return response.json()


def fetch_word_weights(
    api_key: str,
    symbol: str,
    from_date: str | None = None,
    to_date: str | None = None,
    page_limit: int = 20,
) -> dict:
    """
    Fetch weighted keywords from news articles for a given ticker.

    `symbol` — ticker with exchange suffix, e.g. "AAPL.US"
    Returns a dict with 'data' (word weights), 'meta', and 'links'.
    """
    params: dict = {
        "api_token": api_key,
        "fmt": "json",
        "s": symbol,
        "page[limit]": page_limit,
    }
    if from_date:
        params["filter[date_from]"] = from_date
    if to_date:
        params["filter[date_to]"] = to_date

    log.info(
        "GET %s  params=%s",
        WORD_WEIGHTS_URL,
        {k: v for k, v in params.items() if k != "api_token"},
    )

    response = requests.get(WORD_WEIGHTS_URL, params=params, timeout=60)

    if response.status_code == 401:
        raise ValueError("Invalid API key — check your EODHD_API_KEY.")
    response.raise_for_status()

    return response.json()


def sanitize_filename(text: str, max_len: int = 80) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in text)
    return safe[:max_len].strip("_")


def save_article(article: dict, output_dir: Path, index: int) -> Path:
    """
    Save a single news article dict as a pretty-printed JSON file.

    Naming: {index:04d}_{date}_{sanitized_title}.json
    Each article contains: date, title, content, link, symbols, tags, sentiment
    """
    date_str = ""
    if raw_date := article.get("date", ""):
        try:
            dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y%m%d_%H%M%S")
        except ValueError:
            date_str = sanitize_filename(raw_date, 20)

    title_slug = sanitize_filename(article.get("title", "no_title"), 60)
    filename = f"{index:04d}_{date_str}_{title_slug}.json"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(article, f, indent=2, ensure_ascii=False)

    return filepath

def run() -> None:
    api_key = os.environ.get("EODHD_API_KEY", "demo")
    output_dir = Path(SAVE_PATH)
    output_dir.mkdir(parents=True, exist_ok=True)
    log.info("Output directory: %s", output_dir.resolve())

    # --- Configuration ---
    tags = [
        "finance",
        "banking",
        "investment",
        "portfolio",
        "equities",
        "bonds",
        "ETF",
        "earnings",
        "inflation",
        "interest rates",
        "personal finance",
        "asset management",
    ]

    total_saved = 0
    global_index = 1

    # ── Fetch news by tag ─────────────────────────────────────────────────────
    for tag in tags:
        log.info("─── Fetching news for tag: %s ───", tag)

        articles = fetch_news(
            api_key=api_key,
            tag=tag,
            limit=50,
            offset=0,
            from_date="2026-03-19",
            to_date="2026-03-19",
        )

        if not articles:
            log.warning("No articles returned for tag: %s", tag)
            continue

        log.info("  Received %d articles", len(articles))

        for article in articles:
            article["_fetched_at"] = datetime.now().isoformat() + "Z"
            article["_query_tag"] = tag  # changed from _query_symbol

            filepath = save_article(article, output_dir, global_index)
            log.info("  [%04d] Saved → %s", global_index, filepath.name)
            global_index += 1
            total_saved += 1

        time.sleep(0.5)

    log.info("═══ Done. %d articles saved to %s ═══", total_saved, output_dir.resolve())

if __name__ == "__main__":
    run()


# from elasticsearch import Elasticsearch
# import json

# es = Elasticsearch("http://localhost:9200")
# index_name = "clients"

# # Fetch all documents using scroll
# result = es.search(
#     index=index_name,
#     body={"query": {"match_all": {}}},
#     scroll="2m",
#     size=1000
# )

# scroll_id = result["_scroll_id"]
# documents = [hit["_source"] for hit in result["hits"]["hits"]]

# # Keep scrolling until all docs are fetched
# while True:
#     result = es.scroll(scroll_id=scroll_id, scroll="2m")
#     hits = result["hits"]["hits"]
#     if not hits:
#         break
#     documents.extend(hit["_source"] for hit in hits)

# es.clear_scroll(scroll_id=scroll_id)

# # Write to JSON file
# output_path = "index_dump.json"
# with open(output_path, "w", encoding="utf-8") as f:
#     json.dump(documents, f, indent=2)

# print(f"Exported {len(documents)} documents → {output_path}")


# save as src/app/inspect_index.py and run with python3 -m src.app.inspect_index

# from elasticsearch import Elasticsearch
# es = Elasticsearch("http://localhost:9200", verify_certs=False)

# # 1. Check clients 24 and 26 — they scored 1.0 on BYD/Tesla news
# for client_id in ["8255", "8917"]:
#     doc = es.get(index="clients", id=client_id)["_source"]
#     print(f"\n{'='*60}")
#     print(f"Client: {doc['client_name']} (id={doc['client_id']})")
#     print(f"Type:         {doc['client_type']}")
#     print(f"Mandate:      {doc['mandate']}")
#     print(f"Classifications: {doc['asset_classifications']}")
#     print(f"Tickers:      {doc['ticker_symbols']}")
#     print(f"Tags:         {doc['tags_of_interest']}")
#     print(f"Query:        {doc['query']}")
#     print(f"Asset descriptions (first 5): {doc['asset_descriptions'][:5]}")

# # 2. Overall index stats
# stats = es.count(index="clients")
# print(f"\n{'='*60}")
# print(f"Total docs in index: {stats['count']}")

# # 3. Check how many clients have tickers vs none
# result = es.search(
#     index="clients",
#     size=0,
#     aggs={
#         "has_tickers": {
#             "filter": {"exists": {"field": "ticker_symbols"}},
#         }
#     }
# )
# print(f"Clients with ticker_symbols field: {result['aggregations']['has_tickers']['doc_count']}")

# # 4. Sample the query field across all clients — this drives semantic matching
# all_clients = es.search(index="clients", size=35, source=["client_id", "client_name", "query", "ticker_symbols", "asset_classifications"])
# print(f"\n{'='*60}")
# print("Query strings per client (drives semantic scoring):")
# for hit in all_clients["hits"]["hits"]:
#     s = hit["_source"]
#     print(f"  [{s['client_id']}] {s['client_name']}: tickers={len(s.get('ticker_symbols', []))} | query='{s.get('query', '')[:80]}'")