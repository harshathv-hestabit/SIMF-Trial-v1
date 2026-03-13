from azure.storage.blob.aio import BlobServiceClient
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def create_container():
    async with BlobServiceClient.from_connection_string(os.getenv("AZURE_STORAGE_CONNECTION_STRING")) as client:
        container = client.get_container_client("eventhub-checkpoints")
        print("TRYING")

        try:
            await container.create_container()
            print("SUCCESS")
        except Exception as e:
            print("FAILED:", e)