import os
from azure.eventhub.aio import EventHubConsumerClient
from azure.eventhub.extensions.checkpointstoreblobaio import BlobCheckpointStore


class EventConsumer:

    def __init__(self):

        conn = (
            "Endpoint=sb://localhost;"
            "SharedAccessKeyName=RootManageSharedAccessKey;"
            "SharedAccessKey=SAS_KEY_VALUE;"
            "UseDevelopmentEmulator=true;"
        )

        hub = os.getenv("EVENTHUB_NAME")
        consumer_group = "MAS"

        blob_conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        print(blob_conn)
        checkpoint_store = BlobCheckpointStore.from_connection_string(
            conn_str=blob_conn,
            container_name="eventhub-checkpoints"
        )

        self.consumer = EventHubConsumerClient.from_connection_string(
            conn_str=conn,
            eventhub_name=hub,
            consumer_group=consumer_group,
            checkpoint_store=checkpoint_store
        )

    def client(self):
        return self.consumer