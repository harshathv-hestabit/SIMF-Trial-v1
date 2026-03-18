from azure.eventhub import EventData
from azure.eventhub.aio import EventHubProducerClient
from .settings import settings

import json

class EventProducer:
    def __init__(self):        
        self.producer = EventHubProducerClient.from_connection_string(
            conn_str=settings.EVENTHUB_CONNECTION_STRING,
            eventhub_name=settings.EVENTHUB_NAME
        )

    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        await self.producer.close()
        return False
    
    async def publish(self, news_id: str):
        print(f"Change detected: {news_id}")
        payload = json.dumps({
            "news_doc_id": news_id,
            "partition_key": news_id
        }).encode("utf-8")

        event = EventData(payload)
        event.properties = {
            "event_type": "realtime_news"
        }
        print(f"\nEVENT: {event}\n")
        await self.producer.send_event(event)
