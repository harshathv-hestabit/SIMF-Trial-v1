from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOGS_DIR = Path(__file__).resolve().parents[1] / "logs" / "generate_insight"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: object | None) -> str:
    text = str(value or "unknown").strip()
    if not text:
        text = "unknown"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text)


def initialize_insight_log(*, client_id: str, news_doc_id: str | None) -> str:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    file_name = (
        f"{timestamp}_{_safe_name(client_id)}_{_safe_name(news_doc_id)}.log"
    )
    log_path = LOGS_DIR / file_name
    append_insight_log(
        str(log_path),
        event="workflow_started",
        payload={"client_id": client_id, "news_doc_id": news_doc_id},
    )
    return str(log_path)


def append_insight_log(
    log_file_path: str | None,
    *,
    event: str,
    payload: dict[str, Any] | None = None,
) -> None:
    if not log_file_path:
        return
    log_path = Path(log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": _utc_timestamp(),
        "event": event,
        "payload": payload or {},
    }
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False))
        log_file.write("\n")
