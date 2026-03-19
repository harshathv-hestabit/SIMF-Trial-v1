from .settings import settings
from azure.eventhub.aio import EventHubConsumerClient
from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore

class EventConsumer:
    def __init__(self):
        self.conn = settings.EVENTHUB_CONNECTION_STRING
        self.hub = settings.EVENTHUB_NAME
        self.consumer_group = "MAS"
        self.checkpoint_store = BlobCheckpointStore.from_connection_string(
            conn_str=settings.AZURE_STORAGE_CONNECTION_STRING,
            container_name=settings.CHECKPOINT_CONTAINER
        )
        self.consumer = EventHubConsumerClient.from_connection_string(
            conn_str=self.conn,
            eventhub_name=self.hub,
            consumer_group=self.consumer_group,
            checkpoint_store=self.checkpoint_store
        )

    def client(self):
        return self.consumer