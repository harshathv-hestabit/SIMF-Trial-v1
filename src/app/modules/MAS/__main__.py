import asyncio
import logging

from .config import AsyncServiceBusPublisher, decode_message_body, run_indexing, settings
from .workflow.generate_insight import InsightState, build_insight_graph
from .workflow.hnw import HNWState, build_hnw_graph
from .workflow.standard import StandardState, build_standard_graph


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s %(message)s",
)
logging.getLogger("azure").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


hnw_graph = build_hnw_graph()
standard_graph = build_standard_graph()
insight_graph = build_insight_graph()


async def run_hnw_workflow(event_body: dict) -> dict:
    logger.info(
        "workflow_started workflow=hnw news_doc_id=%s partition_key=%s",
        event_body.get("news_doc_id"),
        event_body.get("partition_key"),
    )
    initial_state: HNWState = {
        "event_data": event_body,
        "news_doc": None,
        "relevance_results": {},
        "candidate_clients": [],
        "client_documents": {},
        "generate_insight_events": [],
    }
    result = await asyncio.to_thread(hnw_graph.invoke, initial_state)
    logger.info(
        "workflow_completed workflow=hnw news_doc_id=%s generated_events=%s",
        event_body.get("news_doc_id"),
        len(result["generate_insight_events"]),
    )
    return result


async def run_standard_workflow(event_body: dict) -> dict:
    logger.info(
        "workflow_started workflow=standard job_id=%s checkpoint_start=%s checkpoint_end=%s",
        event_body.get("job_id"),
        event_body.get("checkpoint_start"),
        event_body.get("checkpoint_end"),
    )
    initial_state: StandardState = {
        "trigger_event": event_body,
        "news_batch": [],
        "client_portfolios": [],
        "relevance_map": [],
        "generate_insight_events": [],
    }
    result = await asyncio.to_thread(standard_graph.invoke, initial_state)
    logger.info(
        "workflow_completed workflow=standard job_id=%s generated_events=%s",
        event_body.get("job_id"),
        len(result["generate_insight_events"]),
    )
    return result


async def run_generate_insight_workflow(event_body: dict) -> dict:
    logger.info(
        "workflow_started workflow=generate_insight client_id=%s news_doc_id=%s",
        event_body.get("client_id"),
        event_body.get("news_doc_id"),
    )
    initial_state: InsightState = {
        "client_id": event_body.get("client_id", "unknown"),
        "news_document": event_body.get("news_document", {}),
        "client_portfolio_document": event_body.get("client_portfolio_document", {}),
        "insight_draft": "",
        "verification_score": 0.0,
        "verification_feedback": "",
        "iterations": 0,
        "status": "pending",
    }
    result = await insight_graph.ainvoke(initial_state)
    logger.info(
        "workflow_completed workflow=generate_insight client_id=%s news_doc_id=%s status=%s score=%s",
        event_body.get("client_id"),
        event_body.get("news_doc_id"),
        result["status"],
        result["verification_score"],
    )
    return result


QUEUE_WORKFLOWS = {
    settings.QUEUE_REALTIME_NEWS: {
        "workflow_name": "hnw",
        "expected_event_type": "realtime_news",
        "handler": run_hnw_workflow,
        "concurrency": settings.REALTIME_WORKFLOW_CONCURRENCY,
    },
    settings.QUEUE_STANDARD_NEWS: {
        "workflow_name": "standard",
        "expected_event_type": "standard_news",
        "handler": run_standard_workflow,
        "concurrency": settings.STANDARD_WORKFLOW_CONCURRENCY,
    },
    settings.QUEUE_GENERATE_INSIGHT: {
        "workflow_name": "generate_insight",
        "expected_event_type": "generate_insight",
        "handler": run_generate_insight_workflow,
        "concurrency": settings.GENERATE_INSIGHT_CONCURRENCY,
    },
}


def normalize_event_type(queue_name: str, event_body: dict) -> str:
    raw_event_type = str(event_body.get("event_type", "")).strip().lower()
    if raw_event_type == "delayed_news":
        return "standard_news"
    if raw_event_type:
        return raw_event_type
    return str(QUEUE_WORKFLOWS[queue_name]["expected_event_type"])


async def handle_queue_message(
    queue_name: str,
    receiver,
    message,
    semaphore: asyncio.Semaphore,
) -> None:
    config = QUEUE_WORKFLOWS[queue_name]
    workflow_name = str(config["workflow_name"])

    try:
        event_body = decode_message_body(message)
        event_type = normalize_event_type(queue_name, event_body)

        if event_type != config["expected_event_type"]:
            raise ValueError(
                f"queue={queue_name} expected event_type="
                f"{config['expected_event_type']} but received {event_type}"
            )

        await config["handler"](event_body)
        await receiver.complete_message(message)
    except Exception as exc:
        delivery_count = int(getattr(message, "delivery_count", 1))
        if delivery_count >= settings.SERVICEBUS_MAX_DELIVERY_ATTEMPTS:
            await receiver.dead_letter_message(
                message,
                reason="workflow_failed",
                error_description=str(exc)[:1024],
            )
            logger.exception(
                "message_dead_lettered queue=%s workflow=%s message_id=%s delivery_count=%s error=%s",
                queue_name,
                workflow_name,
                message.message_id,
                delivery_count,
                exc,
            )
        else:
            await receiver.abandon_message(message)
            logger.exception(
                "message_abandoned queue=%s workflow=%s message_id=%s delivery_count=%s error=%s",
                queue_name,
                workflow_name,
                message.message_id,
                delivery_count,
                exc,
            )
    finally:
        semaphore.release()


async def consume_queue(
    bus_client: AsyncServiceBusPublisher,
    queue_name: str,
    semaphore: asyncio.Semaphore,
) -> None:
    in_flight: set[asyncio.Task] = set()

    async with bus_client.get_queue_receiver(queue_name=queue_name) as receiver:
        while True:
            await semaphore.acquire()

            messages = await receiver.receive_messages(
                max_message_count=1,
                max_wait_time=5,
            )
            if not messages:
                semaphore.release()
                continue

            task = asyncio.create_task(
                handle_queue_message(
                    queue_name=queue_name,
                    receiver=receiver,
                    message=messages[0],
                    semaphore=semaphore,
                )
            )
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)


async def main() -> None:
    logger.info("mas_startup queues=%s", list(QUEUE_WORKFLOWS.keys()))
    async with AsyncServiceBusPublisher(settings.SERVICEBUS_CONNECTION_STRING) as bus_client:
        semaphores = {
            queue_name: asyncio.Semaphore(int(config["concurrency"]))
            for queue_name, config in QUEUE_WORKFLOWS.items()
        }
        await asyncio.gather(
            *[
                consume_queue(bus_client, queue_name, semaphores[queue_name])
                for queue_name in QUEUE_WORKFLOWS
            ]
        )


if __name__ == "__main__":
    logger.info("mas_indexing_start")
    asyncio.run(run_indexing())
    logger.info("mas_indexing_complete")
    asyncio.run(main())
