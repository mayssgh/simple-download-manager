from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

# Shared models - DO NOT rename / modify on your side
from models import DownloadTask, DownloadStatus
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
# Core engine functions implemented by your teammate
from download_manager import (
    start_download,
    pause,
    resume,
    cancel,
    get_progress,
)


# -----------------------------
# Request models
# -----------------------------
class CreateDownloadRequest(BaseModel):
    url: HttpUrl


# -----------------------------
# In-memory API registry
# This avoids depending on engine internals for listing tasks.
# -----------------------------
TASKS: Dict[str, Dict[str, Any]] = {}
CLIENTS: Set[WebSocket] = set()
POLL_INTERVAL = 0.5


# -----------------------------
# Helpers
# -----------------------------
def utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def normalize_status(value: Any) -> str:
    """
    Convert status to a string safely without changing the shared contract.
    """
    if value is None:
        return "unknown"

    if hasattr(value, "value"):
        return str(value.value)

    return str(value).lower()


def build_task_response(task_id: str) -> Dict[str, Any]:
    """
    Build a response dict from our registry.
    Keep it tolerant in case DownloadTask is a pydantic model, dataclass, or unused.
    """
    if task_id not in TASKS:
        raise KeyError(f"Task {task_id} not found")

    task = TASKS[task_id]

    # If your shared DownloadTask is a Pydantic model with these fields, use it.
    # If field names differ, keep returning the plain dict below.
    try:
        model = DownloadTask(**task)  # type: ignore
        if hasattr(model, "model_dump"):
            return model.model_dump()
        if hasattr(model, "dict"):
            return model.dict()
    except Exception:
        pass

    return task


async def broadcast(message: Dict[str, Any]) -> None:
    """
    Broadcast a JSON message to all connected WebSocket clients.
    Removes disconnected sockets safely.
    """
    dead_clients = []

    for ws in CLIENTS:
        try:
            await ws.send_json(message)
        except Exception:
            dead_clients.append(ws)

    for ws in dead_clients:
        CLIENTS.discard(ws)


async def poll_engine_loop() -> None:
    """
    Poll the engine for each known task and push real-time progress to clients.
    This keeps your WebSocket independent from engine implementation details.
    """
    while True:
        try:
            for task_id, task in list(TASKS.items()):
                status = normalize_status(task.get("status"))

                # Don't poll tasks that are already terminal unless you want to keep refreshing them
                if status in {"completed", "cancelled", "failed"}:
                    continue

                try:
                    progress_data = get_progress(task_id) or {}
                except Exception:
                    progress_data = {}

                # Expected shared WebSocket payload:
                # {
                #   "id": "...",
                #   "progress": 65.4,
                #   "speed": 120000,
                #   "eta": 20,
                #   "status": "downloading"
                # }

                task["progress"] = float(progress_data.get("progress", task.get("progress", 0.0)))
                task["speed"] = float(progress_data.get("speed", task.get("speed", 0.0)))
                task["eta"] = progress_data.get("eta", task.get("eta"))
                task["status"] = normalize_status(progress_data.get("status", task.get("status", "queued")))
                task["updated_at"] = utc_now_iso()

                payload = {
                    "id": task_id,
                    "progress": task["progress"],
                    "speed": task["speed"],
                    "eta": task["eta"],
                    "status": task["status"],
                }
                await broadcast(payload)

        except Exception as e:
            print(f"[poll_engine_loop] error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


# -----------------------------
# Lifespan
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    poller = asyncio.create_task(poll_engine_loop())
    try:
        yield
    finally:
        poller.cancel()
        try:
            await poller
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Simple Download Manager API", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="../frontend"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("../frontend/index.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# API Endpoints
# -----------------------------
@app.post("/downloads")
async def create_download(payload: CreateDownloadRequest):
    task_id = str(uuid4())

    # Registry entry created first so GET /downloads shows it immediately
    TASKS[task_id] = {
        "id": task_id,
        "url": str(payload.url),
        "status": "queued",
        "progress": 0.0,
        "speed": 0.0,
        "eta": None,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }

    try:
        # Engine call
        start_download(task_id, str(payload.url))
        TASKS[task_id]["status"] = "downloading"
        TASKS[task_id]["updated_at"] = utc_now_iso()
    except Exception as e:
        TASKS[task_id]["status"] = "failed"
        TASKS[task_id]["updated_at"] = utc_now_iso()
        raise HTTPException(status_code=500, detail=f"Failed to start download: {e}")

    return build_task_response(task_id)


@app.get("/downloads")
async def list_downloads():
    return [build_task_response(task_id) for task_id in TASKS.keys()]


@app.post("/downloads/{task_id}/pause")
async def pause_download(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Download not found")

    try:
        pause(task_id)
        TASKS[task_id]["status"] = "paused"
        TASKS[task_id]["updated_at"] = utc_now_iso()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to pause download: {e}")

    return build_task_response(task_id)


@app.post("/downloads/{task_id}/resume")
async def resume_download(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Download not found")

    try:
        resume(task_id)
        TASKS[task_id]["status"] = "downloading"
        TASKS[task_id]["updated_at"] = utc_now_iso()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume download: {e}")

    return build_task_response(task_id)


@app.delete("/downloads/{task_id}")
async def cancel_download(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Download not found")

    try:
        cancel(task_id)
        TASKS[task_id]["status"] = "cancelled"
        TASKS[task_id]["updated_at"] = utc_now_iso()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel download: {e}")

    return {"message": "Download cancelled", "id": task_id}


# -----------------------------
# WebSocket
# -----------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    CLIENTS.add(websocket)

    try:
        # Send initial snapshot so the UI can hydrate immediately
        for task_id in TASKS:
            task = TASKS[task_id]
            await websocket.send_json({
                "id": task["id"],
                "progress": task["progress"],
                "speed": task["speed"],
                "eta": task["eta"],
                "status": task["status"],
            })

        while True:
            # Optional: keep connection alive and allow future client commands
            await websocket.receive_text()

    except WebSocketDisconnect:
        CLIENTS.discard(websocket)
    except Exception:
        CLIENTS.discard(websocket)