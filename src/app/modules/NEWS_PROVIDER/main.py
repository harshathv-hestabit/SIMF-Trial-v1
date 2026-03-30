import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .listener import NewsStreamListener, create_listener
from .publisher import EventHubPublisher
from app.common.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("uamqp").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class ServiceContainer:
    def __init__(self) -> None:
        self.publisher = EventHubPublisher(
            connection_string=settings.EVENTHUB_CONNECTION_STRING,
            eventhub_name=settings.EVENTHUB_NAME,
        )
        self.listener: NewsStreamListener | None = None
        self.listener_task: asyncio.Task | None = None


container = ServiceContainer()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("news_provider_starting")

    await container.publisher.start()
    container.listener = await create_listener(container.publisher)
    container.listener_task = asyncio.create_task(container.listener.run_forever())

    try:
        yield
    finally:
        logger.info("news_provider_stopping")

        if container.listener is not None:
            container.listener.stop()

        if container.listener_task is not None:
            container.listener_task.cancel()
            try:
                await container.listener_task
            except asyncio.CancelledError:
                pass

        await container.publisher.close()


app = FastAPI(title="news-provider-service", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/ready")
async def ready() -> JSONResponse:
    listener = container.listener
    poller_running = bool(listener and listener.stats.poller_running)
    is_producer_ready = container.publisher.is_ready
    has_successful_poll = bool(listener and listener.stats.last_successful_poll_time)
    is_ready = poller_running and is_producer_ready and has_successful_poll

    payload = {
        "ready": is_ready,
        "poller_running": poller_running,
        "producer_ready": is_producer_ready,
        "has_successful_poll": has_successful_poll,
        "last_successful_poll_time": listener.stats.last_successful_poll_time if listener else None,
        "last_error": listener.stats.last_error if listener else None,
    }
    status_code = 200 if is_ready else 503
    return JSONResponse(content=payload, status_code=status_code)


@app.get("/stats")
async def stats() -> dict[str, Any]:
    listener = container.listener
    if listener is None:
        return {
            "messages_received": 0,
            "messages_published": 0,
            "reconnect_count": 0,
            "last_event_time": None,
            "polls_attempted": 0,
            "polls_succeeded": 0,
            "last_poll_time": None,
            "last_successful_poll_time": None,
            "last_batch_size": 0,
            "next_updated_since": None,
            "last_error": None,
        }

    return {
        "messages_received": listener.stats.messages_received,
        "messages_published": listener.stats.messages_published,
        "reconnect_count": listener.stats.reconnect_count,
        "last_event_time": listener.stats.last_event_time,
        "polls_attempted": listener.stats.polls_attempted,
        "polls_succeeded": listener.stats.polls_succeeded,
        "last_poll_time": listener.stats.last_poll_time,
        "last_successful_poll_time": listener.stats.last_successful_poll_time,
        "last_batch_size": listener.stats.last_batch_size,
        "next_updated_since": listener.stats.next_updated_since,
        "last_error": listener.stats.last_error,
    }
