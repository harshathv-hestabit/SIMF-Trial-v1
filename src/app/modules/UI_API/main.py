from __future__ import annotations

from contextlib import asynccontextmanager
import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.common.mongo import build_sync_mongo_client, get_database_client
from app.modules.UI_API.services.clients import (
    load_client_insights,
    load_client_portfolio,
    load_clients,
)
from app.modules.UI_API.services.ops import (
    load_metrics,
    load_news_detail,
    load_news_rows,
    load_recent_insights,
)
# from app.modules.UI_API.services.pipeline import (
#     run_pipeline_from_sample_folder,
#     run_pipeline_from_upload,
# )
from app.modules.UI_API.settings import settings


def _cors_origins() -> list[str]:
    return [origin.strip() for origin in settings.UI_CORS_ORIGINS.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_client = build_sync_mongo_client(settings.MONGO_URI)
    app.state.mongo_client = mongo_client
    app.state.database_client = get_database_client(mongo_client, settings.MONGO_DB)
    try:
        yield
    finally:
        mongo_client.close()


app = FastAPI(
    title="smif-ui-api",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _database(request: Request):
    return request.app.state.database_client


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/clients")
def get_clients(request: Request) -> dict[str, list[dict[str, str]]]:
    return {"items": load_clients(_database(request))}


@app.get("/api/clients/{client_id}/portfolio")
def get_client_portfolio(request: Request, client_id: str):
    portfolio = load_client_portfolio(_database(request), client_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail=f"Portfolio not found for client {client_id}")
    return portfolio


@app.get("/api/clients/{client_id}/insights")
def get_client_insights(request: Request, client_id: str) -> dict[str, object]:
    insights = load_client_insights(_database(request), client_id)
    return {
        "client_id": client_id,
        "count": len(insights),
        "items": insights,
    }


@app.get("/api/ops/metrics")
def get_ops_metrics(request: Request):
    return load_metrics(_database(request))


@app.get("/api/ops/news")
def get_ops_news(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    items = load_news_rows(_database(request), limit)
    return {
        "count": len(items),
        "items": items,
    }


@app.get("/api/ops/news/{news_id}")
def get_ops_news_detail(request: Request, news_id: str):
    item = load_news_detail(_database(request), news_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"News document not found: {news_id}")
    return item


@app.get("/api/ops/insights")
def get_ops_recent_insights(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, object]:
    items = load_recent_insights(_database(request), limit)
    return {
        "count": len(items),
        "items": items,
    }

@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )
