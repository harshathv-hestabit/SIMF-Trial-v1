from urllib.parse import urlparse


def normalize_news_document(raw_doc: dict) -> dict:
    if not isinstance(raw_doc, dict):
        raise ValueError("Incoming Event Hub payload must be a JSON object")

    data = _get_nested_dict(raw_doc, "data")
    content = _get_nested_dict(data, "content") or raw_doc

    article_id = _require_article_id(raw_doc, data, content)
    event_id = _first_non_empty(data, "id", "event_id")
    link = _normalize_url(_first_non_empty(content, "url", "link", "canonical_url"))
    image_url = _normalize_image_url(content)
    authors = _normalize_authors(content)
    normalized = {
        "id": article_id,
        "event_id": str(event_id) if event_id is not None else None,
        "revision_id": _string_or_none(_first_non_empty(content, "revision_id")),
        "type": _string_or_none(_first_non_empty(content, "type")),
        "title": _string_or_none(_first_non_empty(content, "title", "headline", "name")),
        "content": _string_or_none(
            _first_non_empty(content, "body", "content", "teaser", "summary", "description")
        ),
        "teaser": _string_or_none(_first_non_empty(content, "teaser", "summary", "description")),
        "link": link,
        "image_url": image_url,
        "authors": authors or None,
        "symbols": _normalize_symbols(content),
        "tags": _normalize_tags(content),
        "source": _normalize_source(raw_doc, content),
        "api_version": _string_or_none(_first_non_empty(raw_doc, "api_version")),
        "kind": _string_or_none(_first_non_empty(raw_doc, "kind")),
        "event_type": _string_or_none(_first_non_empty(raw_doc, "event_type")),
        "event_action": _string_or_none(_first_non_empty(data, "action")),
        "trace_id": _string_or_none(_first_non_empty(raw_doc, "trace_id")),
        "published_at": _first_non_empty(
            content,
            "created_at",
            "published_at",
            "published",
            "created",
            "date",
        ),
        "updated_at": _first_non_empty(content, "updated_at", "updated"),
        "event_timestamp": _first_non_empty(data, "timestamp", "created_at", "updated_at"),
        "fetched_at": _first_non_empty(raw_doc, "ingested_at", "_fetched_at", "fetched_at"),
    }
    return {key: value for key, value in normalized.items() if value not in (None, "", [], {})}


def preprocess_news(raw_doc: dict) -> dict:
    return normalize_news_document(raw_doc)


def _require_article_id(raw_doc: dict, data: dict, content: dict) -> str:
    article_id = _first_non_empty(content, "id", "original_id")
    if article_id is None:
        article_id = _first_non_empty(data, "id")
    if article_id is None:
        article_id = _first_non_empty(raw_doc, "id", "article_id", "news_id")
    if article_id is None:
        raise ValueError("Missing article id in incoming news payload")
    return str(article_id)


def _normalize_symbols(raw_doc: dict) -> list[str]:
    values = raw_doc.get("symbols")
    if isinstance(values, list):
        return [str(item) for item in values if item]

    securities = raw_doc.get("securities")
    if isinstance(securities, list):
        symbols: list[str] = []
        for item in securities:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            if symbol:
                symbols.append(str(symbol))
        return symbols

    stocks = raw_doc.get("stocks")
    if isinstance(stocks, list):
        symbols: list[str] = []
        for item in stocks:
            if isinstance(item, dict):
                symbol = _first_non_empty(item, "symbol", "ticker", "name")
            else:
                symbol = item
            if symbol:
                symbols.append(str(symbol))
        return symbols

    return []


def _normalize_tags(raw_doc: dict) -> list[str]:
    tags: list[str] = []
    for key in ("tags", "channels", "categories"):
        values = raw_doc.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict):
                value = _first_non_empty(item, "name", "slug", "label")
            else:
                value = item
            if value:
                tags.append(str(value))
    return tags


def _normalize_authors(content: dict) -> list[str]:
    authors = content.get("authors")
    if isinstance(authors, list):
        return [str(author).strip() for author in authors if str(author).strip()]
    if isinstance(authors, str) and authors.strip():
        return [authors.strip()]
    author = content.get("author")
    if isinstance(author, str) and author.strip():
        return [author.strip()]
    return []


def _normalize_source(raw_doc: dict, content: dict) -> str | None:
    source = _first_non_empty(content, "source", "provider", "publisher")
    if source:
        return str(source)
    source = _first_non_empty(raw_doc, "source", "author")
    if source:
        return str(source)
    return None


def _normalize_image_url(content: dict) -> str:
    image = content.get("image")
    if isinstance(image, list):
        for item in image:
            if isinstance(item, dict):
                value = _first_non_empty(item, "url")
            else:
                value = item
            normalized = _normalize_url(value)
            if normalized:
                return normalized
        return ""

    return _normalize_url(
        _first_non_empty(content, "image", "image_url", "thumbnail", "thumbnail_url")
    )


def _normalize_url(value: object | None) -> str:
    if not isinstance(value, str):
        return ""

    url = value.strip()
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return f"https:{url}"

    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        return url
    if "." in parsed.path.split("/")[0]:
        return f"https://{url}"
    return url


def _string_or_none(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_non_empty(raw_doc: dict, *keys: str) -> object | None:
    for key in keys:
        value = raw_doc.get(key)
        if isinstance(value, str):
            value = value.strip()
        if value not in (None, "", [], {}):
            return value
    return None


def _get_nested_dict(raw_doc: dict, key: str) -> dict:
    value = raw_doc.get(key)
    if isinstance(value, dict):
        return value
    return {}
