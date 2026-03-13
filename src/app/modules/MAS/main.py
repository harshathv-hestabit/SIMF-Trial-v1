import os
import json
import asyncio
from dotenv import load_dotenv
from azure.storage.blob.aio import BlobServiceClient
from azure.eventhub import EventData
from .config import EventConsumer

from .workflow.hnw import build_hnw_graph, HNWState
from .workflow.standard import build_standard_graph, StandardState
from .workflow.generate_insight import build_insight_graph, InsightState

load_dotenv()

CHECKPOINT_CONTAINER = "eventhub-checkpoints"

hnw_graph     = build_hnw_graph()
standard_graph = build_standard_graph()
insight_graph  = build_insight_graph()

async def ensure_checkpoint_container():
    async with BlobServiceClient.from_connection_string(
        os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    ) as client:
        container = client.get_container_client(CHECKPOINT_CONTAINER)
        try:
            await container.create_container()
            print(f"Checkpoint container created: {CHECKPOINT_CONTAINER}")
        except Exception:
            print(f"Checkpoint container exists: {CHECKPOINT_CONTAINER}")

async def run_hnw_workflow(event_type,event_body: dict) -> dict:
    print("[Orchestrator] Starting HNW Client Workflow")
    initial_state: HNWState = {
        "event_data": event_body,           
        "news_doc": None,                   
        "relevance_results": {},            
        "candidate_clients": [],
        "generate_insight_events": [],
    }
    print(f"\n Initial State: {initial_state}\n")
    result = await asyncio.to_thread(hnw_graph.invoke, initial_state)
    print(f"[Orchestrator] HNW complete — {len(result['generate_insight_events'])} insight events queued")
    return result

async def run_standard_workflow(event_body: dict):
    print("[Orchestrator] Starting Standard Client Workflow")
    initial_state: StandardState = {
        "trigger_event": event_body,
        "news_batch": [],
        "client_portfolios": [],
        "relevance_map": [],
        "generate_insight_events": [],
    }
    result = await asyncio.to_thread(standard_graph.invoke, initial_state)
    print(f"[Orchestrator] Standard complete — {len(result['generate_insight_events'])} insight events queued")
    return result

async def run_generate_insight_workflow(event_body: dict):
    print(f"[Orchestrator] Starting Generate Insight Workflow for client {event_body.get('client_id')}")
    initial_state: InsightState = {
        "client_id": event_body.get("client_id", "unknown"),
        "news_event": event_body.get("news_event", {}),
        "client_portfolio": event_body.get("client_portfolio", {}),
        "insight_draft": "",
        "verification_score": 0.0,
        "verification_feedback": "",
        "iterations": 0,
        "status": "pending",
    }
    result = await asyncio.to_thread(insight_graph.invoke, initial_state)
    print(f"[Orchestrator] Insight complete — status={result['status']} score={result['verification_score']}")
    return result

EVENT_TYPE_HANDLERS = {
    "realtime_news":    run_hnw_workflow,
    "delayed_news":     run_standard_workflow,
    "generate_insight": run_generate_insight_workflow,
}

def route_event(event_type: str, event_body: dict):
    handler = EVENT_TYPE_HANDLERS.get(event_type)
    if not handler:
        print(f"[Orchestrator] Unknown event_type '{event_type}' — skipping")
        return

    task = asyncio.create_task(handler(event_type,event_body))
    task.add_done_callback(
        lambda t: print(f"[Orchestrator] Task error: {t.exception()}")
        if not t.cancelled() and t.exception()
        else None
    )

async def process_event(partition_context, event: EventData):
    try:
        print(event)
        properties = event.properties or {}
        raw = (
            properties.get(b"event_type")
            or properties.get("event_type")
            or b"unknown"
        )
        event_type = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        body_bytes = event.body_as_str(encoding="utf-8")
        event_body = json.loads(body_bytes) if body_bytes else {}
        print(
            f"[EventHub] partition={partition_context.partition_id} "
            f"| event_type={event_type} | offset={event.offset}"
            f"| event_body={event_body}"
        )
        
        route_event(event_type, event_body)
        await partition_context.update_checkpoint(event)

    except Exception as exc:
        print(f"[EventHub] Error processing event: {exc}")

async def main():
    print("[Orchestrator] Initializing EventHub consumer...")
    await ensure_checkpoint_container()

    consumer = EventConsumer()
    client = consumer.client()
    async with client:
        await client.receive(
            on_event=process_event,
            on_partition_initialize=None,
            on_partition_close=None,
            on_error=None,
            starting_position="-1",
        )

if __name__ == "__main__":
    asyncio.run(main())