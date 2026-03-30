import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import aiohttp

from app.common.settings import settings
from .publisher import EventHubPublisher

logger = logging.getLogger(__name__)

BENZINGA_NEWS_URL = "https://api.benzinga.com/api/v2/news"
POLL_INTERVAL_SECONDS = 10
POLL_OVERLAP_SECONDS = 60
PAGE_SIZE = 2
REQUEST_TIMEOUT_SECONDS = 30


@dataclass
class ListenerStats:
    messages_received: int = 0
    messages_published: int = 0
    reconnect_count: int = 0
    last_event_time: str | None = None
    websocket_connected: bool = False
    invalid_json_count: int = 0
    publish_error_count: int = 0
    polls_attempted: int = 0
    polls_succeeded: int = 0
    last_poll_time: str | None = None
    last_successful_poll_time: str | None = None
    last_error: str | None = None
    last_batch_size: int = 0
    next_updated_since: int | None = None
    poller_running: bool = False


@dataclass
class NewsStreamListener:
    publisher: EventHubPublisher
    benzinga_api_key: str
    stats: ListenerStats = field(default_factory=ListenerStats)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _updated_since_cursor: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.stats.next_updated_since = self._updated_since_cursor

    def stop(self) -> None:
        self._stop_event.set()

    async def run_forever(self) -> None:
        self.stats.poller_running = True
        self.stats.websocket_connected = False

        try:
            while not self._stop_event.is_set():
                try:
                    await self._poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.stats.reconnect_count += 1
                    self.stats.last_error = f"{type(exc).__name__}: {exc}"
                    logger.exception(
                        "news_poll_failed poll_count=%s error=%s",
                        self.stats.polls_attempted,
                        type(exc).__name__,
                    )

                if self._stop_event.is_set():
                    break

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=POLL_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    continue
        finally:
            self.stats.poller_running = False

    async def _poll_once(self) -> None:
        poll_started_at = datetime.now(timezone.utc)
        self.stats.polls_attempted += 1
        self.stats.last_poll_time = poll_started_at.isoformat()

        params = {
            "token": self.benzinga_api_key,
            "pageSize": str(PAGE_SIZE),
            "displayOutput": "full",
            "sort": "updated:asc",
        }
        if self._updated_since_cursor is not None:
            params["updatedSince"] = str(self._updated_since_cursor)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)

        logger.info(
            "news_poll_started updated_since=%s page_size=%s",
            self._updated_since_cursor,
            PAGE_SIZE,
        )

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                BENZINGA_NEWS_URL,
                params=params,
                headers={"accept": "application/json"},
            ) as response:
                response.raise_for_status()
                payload = await response.json()

        if not isinstance(payload, list):
            raise ValueError(f"Unexpected Benzinga response type: {type(payload).__name__}")

        self.stats.polls_succeeded += 1
        self.stats.last_successful_poll_time = poll_started_at.isoformat()
        self.stats.last_batch_size = len(payload)
        self.stats.last_error = None

        next_cursor = max(
            int(poll_started_at.timestamp()) - POLL_OVERLAP_SECONDS,
            0,
        )

        published = 0
        for item in payload:
            print(f"ITEM: \n{item}\n")
            if not isinstance(item, dict):
                self.stats.invalid_json_count += 1
                logger.warning(
                    "news_poll_item_skipped reason=non_object payload_type=%s",
                    type(item).__name__,
                )
                continue

            enriched_payload: dict[str, Any] = {
                **item,
                "event_type": "news_stream",
                "source": "benzinga_rest",
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "trace_id": str(uuid4()),
                "_fetched_at": poll_started_at.isoformat(),
                "_poll_updated_since": self._updated_since_cursor,
            }

            self.stats.messages_received += 1
            self.stats.last_event_time = enriched_payload["ingested_at"]

            try:
                await self.publisher.publish(
                    enriched_payload,
                    properties={"event_type": "news_stream"},
                )
                self.stats.messages_published += 1
                published += 1
            except Exception:
                self.stats.publish_error_count += 1
                logger.exception(
                    "event_publish_failed article_id=%s",
                    item.get("id"),
                )

        self._updated_since_cursor = next_cursor
        self.stats.next_updated_since = self._updated_since_cursor

        logger.info(
            "news_poll_completed batch_size=%s published=%s next_updated_since=%s",
            len(payload),
            published,
            self._updated_since_cursor,
        )


async def create_listener(publisher: EventHubPublisher) -> NewsStreamListener:
    return NewsStreamListener(
        publisher=publisher,
        benzinga_api_key=settings.BENZINGA_API_KEY,
    )
