import asyncio

from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
from azure.core.exceptions import ServiceRequestError
from .settings import settings

_initialized = False
_async_client_instance = None

async def init_cosmos():
    global _initialized
    if _initialized:
        return

    client = AsyncCosmosClient(
        settings.COSMOS_URL,
        credential=settings.COSMOS_KEY,
        connection_verify=False,
        enable_endpoint_discovery=False,
        connection_timeout=5,
    )

    async with client:
        db = await client.create_database_if_not_exists(settings.COSMOS_DB)
        await db.create_container_if_not_exists(
            id=settings.NEWS_CONTAINER,
            partition_key=PartitionKey(
                path=settings.NEWS_CONTAINER_PARTITION_ID
            ),
        )

    _initialized = True
    print("[Cosmos] Initialization complete")

class CosmosAsyncClient:
    def __init__(self):
        self.client = None
        self.database = None
        self.container = None

    async def connect(self):
        await init_cosmos()

        self.client = AsyncCosmosClient(
            settings.COSMOS_URL,
            credential=settings.COSMOS_KEY,
            connection_verify=False,
            enable_endpoint_discovery=False,
            connection_timeout=5,
        )
        self.database = self.client.get_database_client(settings.COSMOS_DB)
        self.container = self.database.get_container_client(settings.NEWS_CONTAINER)

    async def close(self):
        if self.client:
            await self.client.close()

    async def upsert_document(self, doc: dict):
        await self.container.upsert_item(doc)
                
    async def read_document(self, doc_id, partition_key):
        return await self.container.read_item(doc_id, partition_key)

    def get_change_feed(self):
        return self.container.query_items_change_feed(
            is_start_from_beginning=False
        )

async def get_cosmos_async_client() -> CosmosAsyncClient:
    global _async_client_instance
    if _async_client_instance is None:
        client = CosmosAsyncClient()
        await client.connect()
        _async_client_instance = client

    return _async_client_instance
