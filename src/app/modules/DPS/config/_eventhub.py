import os
from azure.eventhub import EventData
from azure.eventhub import EventHubProducerClient
import json

class EventProducer:
    def __init__(self):        
        conn = (
            "Endpoint=sb://localhost;SharedAccessKeyName=RootManageSharedAccessKey;"
            "SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;"
        )
        hub = os.getenv("EVENTHUB_NAME")
        self.producer = EventHubProducerClient.from_connection_string(
            conn_str=conn,
            eventhub_name=hub
        )

    def publish(self, news_id: str):
        '''
        This Function is not being invoked in the change feed service currently
        '''
        payload = json.dumps({
            "news_doc_id": news_id,
            "partition_key": news_id
        }).encode("utf-8")

        event = EventData(payload)
        event.properties = {
            "event_type": "news_processed"
        }
        self.producer.send_event(event)