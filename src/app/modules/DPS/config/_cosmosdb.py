import os
from azure.cosmos import CosmosClient
from azure.cosmos.aio import CosmosClient as AsyncCosmosClient
from azure.cosmos import PartitionKey

COSMOSDB_CONFIG = {
    "database_name": "SMIF",
    "containers": {
        "news": {
            "name": "news",
            "partition_key": "/id"
        }
    }
}
COSMOS_URL = os.getenv("COSMOS_URL")
COSMOS_KEY = os.getenv("COSMOS_KEY")

async def _ensure_container(cosmos_client: AsyncCosmosClient) -> None:
    try:
        db = await cosmos_client.create_database_if_not_exists(COSMOSDB_CONFIG["database_name"])
        print(f"Database ready: {COSMOSDB_CONFIG["database_name"]}", )
    except Exception as exc:
        print(f"Error: {exc}")

    try:
        await db.create_container_if_not_exists(
            id=COSMOSDB_CONFIG["containers"]["news"]["name"],
            partition_key=PartitionKey(
                path=COSMOSDB_CONFIG["containers"]["news"]["partition_key"]
            ),
        )
        print(f"Container ready: {COSMOSDB_CONFIG["containers"]["news"]["name"]} (partition key: {COSMOSDB_CONFIG["containers"]["news"]["partition_key"]})")
    except Exception as exc:
        print(f"Error: {exc}")

class CosmosSyncClient:
    def __init__(self):
        database_name = COSMOSDB_CONFIG["database_name"]
        container_name = COSMOSDB_CONFIG["containers"]["news"]["name"]
        self.client = CosmosClient(
            os.getenv("COSMOS_URL"),
            credential=os.getenv("COSMOS_KEY"),
            connection_verify=False
        )
        self.database = self.client.get_database_client(database_name)
        self.container = self.database.get_container_client(container_name)

    def upsert_document(self, doc: dict):
        self.container.upsert_item(doc)

    def read_document(self, doc_id, partition_key):
        return self.container.read_item(doc_id, partition_key)

class CosmosAsyncClient:
    def __init__(self):
        self.client = None
        self.database = None
        self.container = None
        self.database_name = COSMOSDB_CONFIG["database_name"]
        self.container_name = COSMOSDB_CONFIG["containers"]["news"]["name"]

    async def connect(self):
        self.client = AsyncCosmosClient(
            os.getenv("COSMOS_URL"),
            credential=os.getenv("COSMOS_KEY"),
            connection_verify=False
        )
        await _ensure_container(self.client)
        self.database = self.client.get_database_client(self.database_name)
        self.container = self.database.get_container_client(self.container_name)

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