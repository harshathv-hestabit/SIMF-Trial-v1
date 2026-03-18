from app.modules.DPS.ingestion import collect_documents
from app.modules.DPS.transformation import preprocess_news
from app.modules.DPS.config.cosmosdb import CosmosAsyncClient

import asyncio

async def process_document(cosmos,doc):
    processed = await asyncio.to_thread(preprocess_news, doc)
    await cosmos.upsert_document(processed)

async def run_pipeline(news_documents: list):
    docs = collect_documents(news_documents)
    tasks = []

    cosmos = CosmosAsyncClient()
    await cosmos.connect()
    
    for doc in docs:
        task = asyncio.create_task(process_document(cosmos,doc))
        tasks.append(task)

    await asyncio.gather(*tasks)
    await cosmos.close()
    return "pipeline completed"
