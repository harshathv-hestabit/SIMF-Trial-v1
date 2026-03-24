import json
import time
import logging
from datetime import datetime
from pathlib import Path
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
    # api_key = os.environ.get("EODHD_API_KEY", "demo")
    api_key = ""
    output_dir = Path(SAVE_PATH)
    output_dir.mkdir(parents=True, exist_ok=True)
    log.info("Output directory: %s", output_dir.resolve())
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