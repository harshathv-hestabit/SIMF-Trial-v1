import asyncio

from ..config import get_cosmos_async_client, EventProducer
from ..config.settings import settings

class ChangeFeedListener:
    def __init__(self):
        self.cosmos = None
        self.container = None

    async def start(self):
        client = await get_cosmos_async_client()
        self.cosmos = client
        self.container = client.container

        async with EventProducer() as producer:
            print(f"Listening to Cosmos Container : {self.container.id}")
            change_feed = self.container.query_items_change_feed(is_start_from_beginning=False)
            while True:
                async for item in change_feed:
                    news_id = item["id"]
                    await producer.publish(news_id)
                await asyncio.sleep(1)