import asyncio
import logging

from ..config import ServiceBusPublisher, build_event_payload, settings
from .insight_job_state import build_job_key, mark_job_queued


logger = logging.getLogger(__name__)


class EventExecutor:
    def __init__(self):
        self.publisher = ServiceBusPublisher(settings.SERVICEBUS_CONNECTION_STRING)
        
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc, tb):
        self.publisher.close()
        return False

    def publish_insight_events(self, insight_events: list[dict]) -> None:
        seen_job_keys: set[str] = set()
        for event_payload in insight_events:
            client_id = str(event_payload.get("client_id", "")).strip()
            news_doc_id = str(event_payload.get("news_doc_id", "")).strip()
            if not client_id or not news_doc_id:
                logger.warning("insight_event_skip_missing_identifiers payload=%s", event_payload)
                continue

            job_key = build_job_key(client_id, news_doc_id)
            if job_key in seen_job_keys:
                logger.info("insight_event_skip_duplicate_in_batch job_key=%s", job_key)
                continue
            seen_job_keys.add(job_key)

            event_payload = dict(event_payload)
            event_payload.setdefault("workflow_type", "generate_insight")
            event_payload["job_key"] = job_key
            message_id = (
                f"insight-{client_id}-{news_doc_id}"
            )
            event_payload["message_id"] = message_id

            should_enqueue = asyncio.run(mark_job_queued(event_payload))
            if not should_enqueue:
                logger.info("insight_event_skip_duplicate_job_state job_key=%s", job_key)
                continue

            payload = build_event_payload(
                "generate_insight",
                event_payload,
                source=event_payload.get("source", "mas.workflow"),
                queue_name=settings.QUEUE_GENERATE_INSIGHT,
            )
            self.publisher.publish_json(
                settings.QUEUE_GENERATE_INSIGHT,
                payload,
                application_properties={
                    "event_type": "generate_insight",
                    "client_id": client_id,
                    "news_doc_id": news_doc_id,
                    "job_key": job_key,
                    "source": payload["source"],
                },
                correlation_id=client_id,
                message_id=message_id,
                subject="generate_insight",
            )
