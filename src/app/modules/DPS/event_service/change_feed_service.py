import os
import asyncio
import json
from dotenv import load_dotenv

from azure.eventhub.aio import EventHubProducerClient
from azure.eventhub import EventData

from ..config import CosmosAsyncClient

load_dotenv()

EVENTHUB_CONNECTION_STRING = (
    "Endpoint=sb://localhost;SharedAccessKeyName=RootManageSharedAccessKey;"
    "SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;"
)
EVENTHUB_NAME = os.getenv("EVENTHUB_NAME")

class ChangeFeedListener:

    def __init__(self):
        self.cosmos = None
        self.container = None


    async def start(self):
        client = CosmosAsyncClient()
        await client.connect()
        self.cosmos = client
        self.container = client.container

        async with EventHubProducerClient.from_connection_string(
            conn_str=EVENTHUB_CONNECTION_STRING,
            eventhub_name=EVENTHUB_NAME
        ) as producer:

            print("Listening to Cosmos Change Feed → Event Hub")
            print(self.container)
            change_feed = self.container.query_items_change_feed(
                is_start_from_beginning=False
            )

            while True:
                async for item in change_feed:
                    news_id = item["id"]
                    print(f"Change detected for news: {news_id}")

                    payload = json.dumps({
                        "news_doc_id": news_id,
                        "partition_key": news_id   # CosmosDB partition key path is /news_id
                    }).encode("utf-8")

                    event = EventData(payload)
                    event.properties = {
                        "event_type": "realtime_news"
                    }
                    print(f"\nEVENT: {event}\n")
                    await producer.send_event(event)

                await asyncio.sleep(1)

if __name__ == "__main__":
    listener = ChangeFeedListener()
    asyncio.run(listener.start())