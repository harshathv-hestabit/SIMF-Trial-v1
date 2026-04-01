from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.common.azure_services.cosmos import (
    build_async_cosmos_client,
    ensure_async_container,
)
from ..config import settings


WORKFLOW_TYPE = "generate_insight"
ACTIVE_STATUSES = {"queued", "processing", "completed"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_timestamp(value: object | None) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_job_key(client_id: str, news_doc_id: str) -> str:
    return f"{WORKFLOW_TYPE}:{client_id}:{news_doc_id}"


def build_insight_document_id(client_id: str, news_doc_id: str) -> str:
    return f"insight:{client_id}:{news_doc_id}"


def build_job_document_id(job_key: str) -> str:
    return f"job:{job_key}"


async def _ensure_container():
    client = build_async_cosmos_client(settings.COSMOS_URL, settings.COSMOS_KEY)
    container = await ensure_async_container(
        client,
        database_name=settings.COSMOS_DB,
        container_name=settings.INSIGHTS_CONTAINER,
        partition_key_path=settings.INSIGHTS_CONTAINER_PARTITION_ID,
    )
    return client, container


def _active_processing_is_fresh(existing: dict[str, Any], now: datetime) -> bool:
    started_at = parse_iso_timestamp(existing.get("started_at"))
    if started_at is None:
        return False
    age_seconds = (now - started_at).total_seconds()
    return age_seconds < settings.INSIGHT_JOB_PROCESSING_STALE_AFTER_SECONDS


async def mark_job_queued(event_payload: dict[str, Any]) -> bool:
    client_id = str(event_payload.get("client_id", "")).strip()
    news_doc_id = str(event_payload.get("news_doc_id", "")).strip()
    if not client_id or not news_doc_id:
        return True

    job_key = build_job_key(client_id, news_doc_id)
    job_id = build_job_document_id(job_key)
    now_iso = utc_now_iso()
    workflow_type = str(event_payload.get("workflow_type") or WORKFLOW_TYPE)

    client, container = await _ensure_container()
    try:
        try:
            existing = await container.read_item(item=job_id, partition_key=client_id)
        except CosmosResourceNotFoundError:
            existing = None

        if existing and str(existing.get("status", "")).lower() in ACTIVE_STATUSES:
            return False

        attempt_count = int((existing or {}).get("attempt_count", 0))
        document = dict(existing or {})
        document.update(
            {
                "id": job_id,
                "type": "insight_job_state",
                "workflow_type": workflow_type,
                "job_key": job_key,
                "client_id": client_id,
                "news_doc_id": news_doc_id,
                "status": "queued",
                "queued_at": now_iso,
                "updated_at": now_iso,
                "attempt_count": attempt_count,
                "message_id": event_payload.get("message_id"),
                "delivery_count": 0,
                "last_error": None,
            }
        )
        await container.upsert_item(document)
        return True
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            await close()


async def claim_job_for_processing(
    *,
    event_body: dict[str, Any],
    message_id: str | None,
    delivery_count: int,
    locked_until_utc: object | None,
) -> dict[str, Any]:
    client_id = str(event_body.get("client_id", "")).strip()
    news_doc_id = str(event_body.get("news_doc_id", "")).strip()
    if not client_id or not news_doc_id:
        raise ValueError("generate_insight message is missing client_id or news_doc_id")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    job_key = str(event_body.get("job_key") or build_job_key(client_id, news_doc_id))
    job_id = build_job_document_id(job_key)
    locked_until_text = (
        locked_until_utc.isoformat()
        if hasattr(locked_until_utc, "isoformat")
        else str(locked_until_utc or "")
    )
    workflow_type = str(event_body.get("workflow_type") or WORKFLOW_TYPE)

    client, container = await _ensure_container()
    try:
        try:
            existing = await container.read_item(item=job_id, partition_key=client_id)
        except CosmosResourceNotFoundError:
            existing = None

        existing_status = str((existing or {}).get("status", "")).lower()
        if existing_status == "completed":
            return {"decision": "skip_completed", "job_key": job_key}

        if existing_status == "processing" and _active_processing_is_fresh(existing, now):
            return {"decision": "skip_processing", "job_key": job_key}

        attempt_count = int((existing or {}).get("attempt_count", 0)) + 1
        document = dict(existing or {})
        document.update(
            {
                "id": job_id,
                "type": "insight_job_state",
                "workflow_type": workflow_type,
                "job_key": job_key,
                "client_id": client_id,
                "news_doc_id": news_doc_id,
                "status": "processing",
                "started_at": now_iso,
                "updated_at": now_iso,
                "completed_at": None,
                "message_id": message_id,
                "delivery_count": delivery_count,
                "locked_until_utc": locked_until_text,
                "attempt_count": attempt_count,
                "last_error": None,
            }
        )
        await container.upsert_item(document)
        return {"decision": "process", "job_key": job_key}
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            await close()


async def mark_job_completed(
    *,
    event_body: dict[str, Any],
    message_id: str | None,
    delivery_count: int,
    result: dict[str, Any],
) -> None:
    client_id = str(event_body.get("client_id", "")).strip()
    news_doc_id = str(event_body.get("news_doc_id", "")).strip()
    if not client_id or not news_doc_id:
        return

    job_key = str(event_body.get("job_key") or build_job_key(client_id, news_doc_id))
    job_id = build_job_document_id(job_key)
    now_iso = utc_now_iso()

    client, container = await _ensure_container()
    try:
        try:
            existing = await container.read_item(item=job_id, partition_key=client_id)
        except CosmosResourceNotFoundError:
            existing = {}

        document = dict(existing)
        document.update(
            {
                "id": job_id,
                "type": "insight_job_state",
                "workflow_type": WORKFLOW_TYPE,
                "job_key": job_key,
                "client_id": client_id,
                "news_doc_id": news_doc_id,
                "status": "completed",
                "updated_at": now_iso,
                "completed_at": now_iso,
                "message_id": message_id,
                "delivery_count": delivery_count,
                "result_status": result.get("status"),
                "verification_score": result.get("verification_score"),
                "iterations": result.get("iterations"),
                "last_error": None,
            }
        )
        await container.upsert_item(document)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            await close()


async def mark_job_failed(
    *,
    event_body: dict[str, Any],
    message_id: str | None,
    delivery_count: int,
    error: Exception,
) -> None:
    client_id = str(event_body.get("client_id", "")).strip()
    news_doc_id = str(event_body.get("news_doc_id", "")).strip()
    if not client_id or not news_doc_id:
        return

    job_key = str(event_body.get("job_key") or build_job_key(client_id, news_doc_id))
    job_id = build_job_document_id(job_key)
    now_iso = utc_now_iso()

    client, container = await _ensure_container()
    try:
        try:
            existing = await container.read_item(item=job_id, partition_key=client_id)
        except CosmosResourceNotFoundError:
            existing = {}

        document = dict(existing)
        document.update(
            {
                "id": job_id,
                "type": "insight_job_state",
                "workflow_type": WORKFLOW_TYPE,
                "job_key": job_key,
                "client_id": client_id,
                "news_doc_id": news_doc_id,
                "status": "failed",
                "updated_at": now_iso,
                "message_id": message_id,
                "delivery_count": delivery_count,
                "last_error": str(error)[:1024],
            }
        )
        await container.upsert_item(document)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            await close()
