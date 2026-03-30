from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.modules.DPS.pipeline import run_pipeline


async def run_pipeline_from_upload(files: list[UploadFile]) -> dict[str, Any]:
    docs = []
    for uploaded_file in files:
        payload = await uploaded_file.read()
        data = json.loads(payload.decode("utf-8"))
        if isinstance(data, list):
            docs.extend(data)
        else:
            docs.append(data)

    pipeline_status = await run_pipeline(docs)
    return {
        "documents_processed": len(docs),
        "pipeline_status": pipeline_status,
    }


async def run_pipeline_from_sample_folder(sample_folder: Path) -> dict[str, Any]:
    if not sample_folder.exists():
        raise FileNotFoundError(f"Sample folder not found: {sample_folder}")

    docs = []
    for file_path in sample_folder.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            docs.extend(data)
        else:
            docs.append(data)

    pipeline_status = await run_pipeline(docs)
    return {
        "documents_processed": len(docs),
        "pipeline_status": pipeline_status,
        "sample_folder": str(sample_folder),
    }
