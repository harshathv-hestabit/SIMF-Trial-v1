from .services.change_feed_service import ChangeFeedListener
import asyncio

if __name__ == "__main__":
    print("Starting Change Feed Listener Service...")
    listener = ChangeFeedListener()
    asyncio.run(listener.start())