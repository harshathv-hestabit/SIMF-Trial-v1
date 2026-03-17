import os
import json
from azure.eventhub import EventData, EventHubProducerClient
from ..config import EventConsumer

class EventExecutor(EventConsumer):
    def __init__(self):
        super().__init__()
        self.producer = EventHubProducerClient.from_connection_string(
            conn_str=self.conn,
            eventhub_name=self.hub,
        )
        
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc, tb):
        self.producer.close()
        return False

    def publish_insight_events(self, insight_events: list[dict]) -> None:
        for event_payload in insight_events:
            payload = json.dumps(event_payload).encode("utf-8")

            event = EventData(payload)
            event.properties = {
                "event_type": "generate_insight",
                "client_id":  event_payload["client_id"],
                "news_doc_id": event_payload["news_doc_id"],
            }

            self.producer.send_event(
                event,
                partition_key=event_payload["client_id"],
            )