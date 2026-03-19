from azure.storage.blob.aio import BlobServiceClient
from .settings import settings

async def ensure_checkpoint_container():
    async with BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING) as client:
        container = client.get_container_client(settings.CHECKPOINT_CONTAINER)
        try:
            await container.create_container()
            print(f"Checkpoint container created: {settings.CHECKPOINT_CONTAINER}")
        except Exception:
            print(f"Checkpoint container exists: {settings.CHECKPOINT_CONTAINER}")