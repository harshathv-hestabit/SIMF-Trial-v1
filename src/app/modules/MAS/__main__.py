import asyncio
import logging

from azure.servicebus.aio import AutoLockRenewer
from azure.servicebus.exceptions import ServiceBusConnectionError, ServiceBusError
from azure.servicebus.exceptions import MessageLockLostError

from app.common.news_monitor import AsyncNewsMonitor
from .config import AsyncServiceBusPublisher, decode_message_body, settings
from .util.insight_logging import append_insight_log, initialize_insight_log
from .util.insight_job_state import (
    build_job_key,
    claim_job_for_processing,
    mark_job_completed,
    mark_job_failed,
)
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


SERVICEBUS_RECONNECT_DELAY_SECONDS = 5
SERVICEBUS_MAX_RECONNECT_DELAY_SECONDS = 30


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
        "workflow_started workflow=standard job_id=%s requested_at=%s eligible_before=%s",
        event_body.get("job_id"),
        event_body.get("requested_at"),
        event_body.get("checkpoint_end"),
    )
    initial_state: StandardState = {
        "trigger_event": event_body,
        "news_batch": [],
        "relevance_results": {},
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
    news_doc_id = event_body.get("news_doc_id")
    client_id = str(event_body.get("client_id", "unknown"))
    job_key = str(event_body.get("job_key") or build_job_key(client_id, str(news_doc_id)))
    partition_key = event_body.get("partition_key", news_doc_id)
    news_monitor = AsyncNewsMonitor(
        cosmos_url=settings.COSMOS_URL,
        cosmos_key=settings.COSMOS_KEY,
        cosmos_db=settings.COSMOS_DB,
        news_container=settings.NEWS_CONTAINER,
    )
    logger.info(
        "workflow_started workflow=generate_insight client_id=%s news_doc_id=%s job_key=%s",
        client_id,
        news_doc_id,
        job_key,
    )
    log_file_path = initialize_insight_log(
        client_id=client_id,
        news_doc_id=news_doc_id,
    )
    if news_doc_id:
        await news_monitor.record(
            news_id=news_doc_id,
            partition_key=partition_key,
            stage="generate_insight",
            status="processing",
            details={"client_id": client_id, "job_key": job_key},
        )
    initial_state: InsightState = {
        "client_id": client_id,
        "news_document": event_body.get("news_document", {}),
        "client_portfolio_document": event_body.get("client_portfolio_document", {}),
        "job_key": job_key,
        "log_file_path": log_file_path,
        "insight_draft": "",
        "verification_score": 0.0,
        "verification_feedback": "",
        "iterations": 0,
        "status": "pending",
        "token_usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "calls": [],
        },
    }
    try:
        result = await insight_graph.ainvoke(initial_state)
        append_insight_log(
            log_file_path,
            event="workflow_completed",
            payload={
                "status": result["status"],
                "verification_score": result["verification_score"],
                "iterations": result["iterations"],
                "token_usage": result.get("token_usage", {}),
            },
        )
        logger.info(
            "workflow_completed workflow=generate_insight client_id=%s news_doc_id=%s job_key=%s status=%s score=%s total_tokens=%s",
            client_id,
            news_doc_id,
            job_key,
            result["status"],
            result["verification_score"],
            result.get("token_usage", {}).get("total_tokens", 0),
        )
        if news_doc_id:
            await news_monitor.record(
                news_id=news_doc_id,
                partition_key=partition_key,
                stage="generate_insight",
                status=result["status"],
                details={
                    "client_id": client_id,
                    "job_key": job_key,
                    "verification_score": result["verification_score"],
                    "iterations": result["iterations"],
                    "token_usage": result.get("token_usage", {}),
                },
            )
        return result
    except Exception as exc:
        append_insight_log(
            log_file_path,
            event="workflow_exception",
            payload={"error": str(exc)},
        )
        if news_doc_id:
            await news_monitor.record(
                news_id=news_doc_id,
                partition_key=partition_key,
                stage="generate_insight",
                status="failed",
                details={"client_id": client_id, "job_key": job_key},
            )
        raise
    finally:
        await news_monitor.close()


QUEUE_WORKFLOWS = {
    settings.QUEUE_REALTIME_NEWS: {
        "workflow_name": "hnw",
        "expected_event_type": "realtime_news",
        "handler": run_hnw_workflow,
        "concurrency": settings.REALTIME_WORKFLOW_CONCURRENCY,
    },
    settings.QUEUE_DELAYED_NEWS: {
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


async def _safe_complete_message(receiver, message, *, queue_name: str, workflow_name: str) -> bool:
    try:
        await receiver.complete_message(message)
        return True
    except MessageLockLostError as exc:
        logger.warning(
            "message_complete_lock_lost queue=%s workflow=%s message_id=%s error=%s",
            queue_name,
            workflow_name,
            message.message_id,
            exc,
        )
        return False


async def _safe_abandon_message(receiver, message, *, queue_name: str, workflow_name: str) -> bool:
    try:
        await receiver.abandon_message(message)
        return True
    except MessageLockLostError as exc:
        logger.warning(
            "message_abandon_lock_lost queue=%s workflow=%s message_id=%s error=%s",
            queue_name,
            workflow_name,
            message.message_id,
            exc,
        )
        return False


async def _safe_dead_letter_message(
    receiver,
    message,
    *,
    queue_name: str,
    workflow_name: str,
    reason: str,
    error_description: str,
) -> bool:
    try:
        await receiver.dead_letter_message(
            message,
            reason=reason,
            error_description=error_description,
        )
        return True
    except MessageLockLostError as exc:
        logger.warning(
            "message_dead_letter_lock_lost queue=%s workflow=%s message_id=%s error=%s",
            queue_name,
            workflow_name,
            message.message_id,
            exc,
        )
        return False


async def handle_queue_message(
    queue_name: str,
    receiver,
    message,
    semaphore: asyncio.Semaphore,
) -> None:
    config = QUEUE_WORKFLOWS[queue_name]
    workflow_name = str(config["workflow_name"])
    message_id = str(getattr(message, "message_id", ""))
    delivery_count = int(getattr(message, "delivery_count", 1))
    locked_until_utc = getattr(message, "locked_until_utc", None)
    lock_renewer: AutoLockRenewer | None = None

    try:
        event_body = decode_message_body(message)
        event_type = normalize_event_type(queue_name, event_body)
        client_id = str(event_body.get("client_id", ""))
        news_doc_id = str(event_body.get("news_doc_id", ""))
        job_key = str(
            event_body.get("job_key")
            or (
                build_job_key(client_id, news_doc_id)
                if workflow_name == "generate_insight" and client_id and news_doc_id
                else ""
            )
        )

        if event_type != config["expected_event_type"]:
            raise ValueError(
                f"queue={queue_name} expected event_type="
                f"{config['expected_event_type']} but received {event_type}"
            )

        logger.info(
            "message_received queue=%s workflow=%s message_id=%s delivery_count=%s locked_until_utc=%s client_id=%s news_doc_id=%s job_key=%s",
            queue_name,
            workflow_name,
            message_id,
            delivery_count,
            locked_until_utc,
            client_id,
            news_doc_id,
            job_key,
        )

        if workflow_name == "generate_insight":
            claim = await claim_job_for_processing(
                event_body=event_body,
                message_id=message_id,
                delivery_count=delivery_count,
                locked_until_utc=locked_until_utc,
            )
            decision = claim["decision"]
            event_body["job_key"] = claim["job_key"]
            job_key = claim["job_key"]
            if decision != "process":
                logger.info(
                    "message_duplicate_skip queue=%s workflow=%s message_id=%s delivery_count=%s client_id=%s news_doc_id=%s job_key=%s decision=%s",
                    queue_name,
                    workflow_name,
                    message_id,
                    delivery_count,
                    client_id,
                    news_doc_id,
                    job_key,
                    decision,
                )
                await _safe_complete_message(
                    receiver,
                    message,
                    queue_name=queue_name,
                    workflow_name=workflow_name,
                )
                return

            lock_renewer = AutoLockRenewer()
            lock_renewer.register(
                receiver=receiver,
                renewable=message,
                max_lock_renewal_duration=settings.SERVICEBUS_MAX_LOCK_RENEWAL_SECONDS,
            )

        result = await config["handler"](event_body)

        if workflow_name == "generate_insight":
            await mark_job_completed(
                event_body=event_body,
                message_id=message_id,
                delivery_count=delivery_count,
                result=result,
            )
        await _safe_complete_message(
            receiver,
            message,
            queue_name=queue_name,
            workflow_name=workflow_name,
        )
    except Exception as exc:
        event_body = locals().get("event_body", {})
        workflow_name = str(config["workflow_name"])
        if workflow_name == "generate_insight" and isinstance(event_body, dict):
            await mark_job_failed(
                event_body=event_body,
                message_id=message_id,
                delivery_count=delivery_count,
                error=exc,
            )
        if delivery_count >= settings.SERVICEBUS_MAX_DELIVERY_ATTEMPTS:
            await _safe_dead_letter_message(
                receiver,
                message,
                queue_name=queue_name,
                workflow_name=workflow_name,
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
            await _safe_abandon_message(
                receiver,
                message,
                queue_name=queue_name,
                workflow_name=workflow_name,
            )
            logger.exception(
                "message_abandoned queue=%s workflow=%s message_id=%s delivery_count=%s error=%s",
                queue_name,
                workflow_name,
                message.message_id,
                delivery_count,
                exc,
            )
    finally:
        if lock_renewer is not None:
            close = getattr(lock_renewer, "close", None)
            if callable(close):
                await close()
        semaphore.release()


async def consume_queue(
    queue_name: str,
    semaphore: asyncio.Semaphore,
) -> None:
    in_flight: set[asyncio.Task] = set()
    reconnect_delay = SERVICEBUS_RECONNECT_DELAY_SECONDS

    while True:
        try:
            async with AsyncServiceBusPublisher(settings.SERVICEBUS_CONNECTION_STRING) as bus_client:
                async with bus_client.get_queue_receiver(queue_name=queue_name) as receiver:
                    logger.info("queue_consumer_connected queue=%s", queue_name)
                    reconnect_delay = SERVICEBUS_RECONNECT_DELAY_SECONDS

                    while True:
                        await semaphore.acquire()

                        try:
                            messages = await receiver.receive_messages(
                                max_message_count=1,
                                max_wait_time=5,
                            )
                        except (ServiceBusConnectionError, ServiceBusError):
                            semaphore.release()
                            raise

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
        except asyncio.CancelledError:
            raise
        except (ServiceBusConnectionError, ServiceBusError) as exc:
            logger.warning(
                "queue_consumer_reconnecting queue=%s delay_seconds=%s error=%s",
                queue_name,
                reconnect_delay,
                exc,
            )
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(
                reconnect_delay * 2,
                SERVICEBUS_MAX_RECONNECT_DELAY_SECONDS,
            )
        except Exception:
            logger.exception("queue_consumer_unexpected_error queue=%s", queue_name)
            await asyncio.sleep(reconnect_delay)
            reconnect_delay = min(
                reconnect_delay * 2,
                SERVICEBUS_MAX_RECONNECT_DELAY_SECONDS,
            )
        finally:
            if in_flight:
                await asyncio.gather(*in_flight, return_exceptions=True)
                in_flight.clear()


async def main() -> None:
    logger.info("mas_startup queues=%s", list(QUEUE_WORKFLOWS.keys()))
    semaphores = {
        queue_name: asyncio.Semaphore(int(config["concurrency"]))
        for queue_name, config in QUEUE_WORKFLOWS.items()
    }
    await asyncio.gather(
        *[
            consume_queue(queue_name, semaphores[queue_name])
            for queue_name in QUEUE_WORKFLOWS
        ]
    )


if __name__ == "__main__":
    asyncio.run(main())
