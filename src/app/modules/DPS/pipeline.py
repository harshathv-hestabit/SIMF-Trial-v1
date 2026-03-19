from app.modules.DPS.ingestion import collect_documents
from app.modules.DPS.transformation import preprocess_news
from app.modules.DPS.config.cosmosdb import CosmosAsyncClient

import asyncio
import logging
from datetime import datetime
from pathlib import Path


LOGS_DIR = Path(__file__).resolve().parent / "logs"


def _build_run_logger() -> tuple[logging.Logger, logging.Handler, Path]:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger(f"dps.pipeline.{log_path.stem}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(handler)

    return logger, handler, log_path


async def process_document(cosmos, doc, logger, doc_index):
    processed = await asyncio.to_thread(preprocess_news, doc)
    logger.info(
        "UPSERT_START doc_index=%s processed_id=%s title=%r published_at=%r",
        doc_index,
        processed.get("id"),
        processed.get("title", ""),
        processed.get("published_at"),
    )
    await cosmos.upsert_document(processed)
    logger.info(
        "UPSERT_OK doc_index=%s processed_id=%s title=%r",
        doc_index,
        processed.get("id"),
        processed.get("title", ""),
    )

async def run_pipeline(news_documents: list):
    docs = collect_documents(news_documents)
    tasks = []
    logger, handler, log_path = _build_run_logger()
    cosmos = CosmosAsyncClient()
    await cosmos.connect()
    logger.info("PIPELINE_START total_documents=%s", len(docs))

    try:
        for doc_index, doc in enumerate(docs, start=1):
            task = asyncio.create_task(process_document(cosmos, doc, logger, doc_index))
            tasks.append(task)

        await asyncio.gather(*tasks)
        logger.info("PIPELINE_SUCCESS total_documents=%s", len(docs))
        return f"pipeline completed; log={log_path}"
    except Exception:
        logger.exception("PIPELINE_FAILURE")
        raise
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await cosmos.close()
        handler.close()
        logger.removeHandler(handler)
