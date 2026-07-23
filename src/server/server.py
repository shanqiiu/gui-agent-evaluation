"""Web server for GUI Agent Evaluation — trigger, monitor, and visualize evaluation runs.

Start:   python -m src.server.server
         or: uvicorn src.server.server:app --host 0.0.0.0 --port 8025 --reload
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

from .runner import JobInfo, get_job_manager

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="GUI Agent Evaluation Server", version="1.0")

# Serve static files (dashboard HTML)
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── pages ────────────────────────────────────────────────────────────


@app.get("/")
async def index():
    """Serve the main dashboard."""
    index_path = STATIC_DIR / "index.html"
    if index_path.is_file():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)


# ── job API ──────────────────────────────────────────────────────────


@app.get("/api/jobs")
async def list_jobs():
    return get_job_manager().list_jobs()


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = get_job_manager().get_job(job_id)
    if job is None:
        return {"error": "job not found"}
    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "config": job.config,
        "result": job.result,
        "output_dir": job.output_dir,
        "error": job.error,
        "log_count": len(job.logs),
    }


@app.get("/api/jobs/{job_id}/logs")
async def get_job_logs(job_id: str):
    job = get_job_manager().get_job(job_id)
    if job is None:
        return {"error": "job not found"}
    return {"logs": job.logs}


@app.get("/api/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    job = get_job_manager().get_job(job_id)
    if job is None:
        return {"error": "job not found"}
    return job.result


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    """SSE endpoint that streams job output in real-time."""
    queue = get_job_manager().get_queue(job_id)
    if queue is None:
        return PlainTextResponse("data: {\"error\": \"job not found\"}\n\n", media_type="text/event-stream")

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ":\n\n"  # heartbeat
                    continue
                if data is None:
                    yield "data: {\"type\": \"done\"}\n\n"
                    break
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── run actions ──────────────────────────────────────────────────────


@app.post("/api/run/preprocess")
async def run_preprocess(
    input_path: str = Form(...),
    output_dir: str = Form(...),
    batch: bool = Form(False),
    task_graph: bool = Form(False),
    mock: bool = Form(False),
):
    """Start a preprocessing job."""
    manager = get_job_manager()
    config = {
        "input_path": input_path,
        "output_dir": output_dir,
        "batch": batch,
        "task_graph_enabled": task_graph,
        "mock": mock,
    }
    job = manager.create_job("preprocess", config)
    asyncio.create_task(manager.run_preprocess(job))
    return {"job_id": job.job_id, "status": "started"}


@app.post("/api/run/evaluate")
async def run_evaluate(
    input_path: str = Form(...),
    output_dir: str = Form(...),
    batch: bool = Form(False),
    mock: bool = Form(False),
    skip_checkpoint_verify: bool = Form(False),
):
    """Start an evaluation job."""
    manager = get_job_manager()
    config = {
        "input_path": input_path,
        "output_dir": output_dir,
        "batch": batch,
        "mock": mock,
        "skip_checkpoint_verify": skip_checkpoint_verify,
    }
    job = manager.create_job("evaluate", config)
    asyncio.create_task(manager.run_evaluate(job))
    return {"job_id": job.job_id, "status": "started"}


@app.post("/api/run/pipeline")
async def run_pipeline(
    input_path: str = Form(...),
    output_dir: str = Form(...),
    batch: bool = Form(True),
    task_graph: bool = Form(False),
    mock: bool = Form(False),
    skip_checkpoint_verify: bool = Form(False),
):
    """Start a full pipeline job: preprocess → evaluate."""
    manager = get_job_manager()
    config = {
        "input_path": input_path,
        "output_dir": output_dir,
        "batch": batch,
        "task_graph_enabled": task_graph,
        "mock": mock,
        "skip_checkpoint_verify": skip_checkpoint_verify,
    }
    job = manager.create_job("pipeline", config)
    asyncio.create_task(manager.run_pipeline(job))
    return {"job_id": job.job_id, "status": "started"}


# ── quick info ───────────────────────────────────────────────────────


@app.get("/api/info")
async def server_info():
    return {
        "server": "GUI Agent Evaluation Server",
        "version": "1.0",
        "endpoints": {
            "dashboard": "/",
            "jobs": "/api/jobs",
            "run_preprocess": "/api/run/preprocess",
            "run_evaluate": "/api/run/evaluate",
            "run_pipeline": "/api/run/pipeline",
        },
    }


# ── main ─────────────────────────────────────────────────────────────


def main():
    import uvicorn

    uvicorn.run(
        "src.server.server:app",
        host="0.0.0.0",
        port=8025,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
