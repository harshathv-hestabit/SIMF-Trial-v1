import json
import logging
import os
import sys
from pathlib import Path
from typing import Iterable

import azure.functions as func


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.common import ServiceBusPublisher, build_event_payload  # noqa: E402


logger = logging.getLogger("dispatch.bridge")
logger.setLevel(logging.INFO)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.ERROR)
logging.getLogger("azure.eventhub").setLevel(logging.WARNING)
logging.getLogger("azure.servicebus").setLevel(logging.WARNING)
logging.getLogger("uamqp").setLevel(logging.WARNING)


REALTIME_EVENT_TYPE = "realtime_news"
MAX_BRIDGE_ATTEMPTS = 2


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _decode_event(event: func.EventHubEvent) -> dict:
    body = event.get_body()
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Event Hub message body must be valid UTF-8 JSON") from exc


def _target_queue(event_type: str) -> str:
    route_map = {
        "realtime_news": "QUEUE_REALTIME_NEWS",
        "standard_news": "QUEUE_STANDARD_NEWS",
        "generate_insight": "QUEUE_GENERATE_INSIGHT",
    }
    queue_env_name = route_map.get(event_type)
    if queue_env_name is None:
        raise ValueError(f"Unsupported event_type for dispatch bridge: {event_type}")
    return _require_env(queue_env_name)


def _publish_with_retry(queue_name: str, payload: dict) -> None:
    last_error: Exception | None = None
    connection_string = _require_env("SERVICEBUS_CONNECTION_STRING")
    for attempt in range(1, MAX_BRIDGE_ATTEMPTS + 1):
        try:
            with ServiceBusPublisher(connection_string) as publisher:
                publisher.publish_json(
                    queue_name,
                    payload,
                    application_properties={
                        "event_type": payload["event_type"],
                        "source": payload["source"],
                    },
                    correlation_id=payload.get("news_doc_id"),
                    message_id=f"{payload['event_type']}-{payload.get('news_doc_id', 'unknown')}",
                    subject=payload["event_type"],
                )
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "dispatch_retry attempt=%s queue=%s event_type=%s news_doc_id=%s error=%s",
                attempt,
                queue_name,
                payload.get("event_type"),
                payload.get("news_doc_id"),
                exc,
            )
    raise RuntimeError(
        f"Failed to publish event to queue {queue_name} after {MAX_BRIDGE_ATTEMPTS} attempts"
    ) from last_error


def main(events: Iterable[func.EventHubEvent]) -> None:
    batch = list(events)
    logger.info("dispatch_batch_received event_count=%s", len(batch))

    for event in batch:
        event_body = _decode_event(event)
        event_type = str(event_body.get("event_type", REALTIME_EVENT_TYPE))
        queue_name = _target_queue(event_type)

        payload = build_event_payload(
            event_type,
            event_body,
            source="dispatch.eventhub_bridge",
            queue_name=queue_name,
        )

        logger.info(
            "dispatch_event_received event_type=%s queue=%s news_doc_id=%s partition_key=%s sequence_number=%s",
            event_type,
            queue_name,
            payload.get("news_doc_id"),
            payload.get("partition_key"),
            getattr(event, "sequence_number", None),
        )
        _publish_with_retry(queue_name, payload)
        logger.info(
            "dispatch_event_enqueued event_type=%s queue=%s news_doc_id=%s",
            event_type,
            queue_name,
            payload.get("news_doc_id"),
        )
