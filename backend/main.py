from fastapi import FastAPI
from pydantic import BaseModel
import uuid

from download_manager import DownloadManager
from history_manager import load_history

app = FastAPI()

manager = DownloadManager()


class DownloadRequest(BaseModel):
    url: str


# -------------------------------
# CREATE DOWNLOAD
# -------------------------------
@app.post("/downloads")
def create_download(req: DownloadRequest):
    task_id = str(uuid.uuid4())
    manager.start_download(task_id, req.url)
    return {"task_id": task_id}


# -------------------------------
# CONTROL
# -------------------------------
@app.post("/pause/{task_id}")
def pause(task_id: str):
    manager.pause(task_id)
    return {"status": "paused"}


@app.post("/resume/{task_id}")
def resume(task_id: str, req: DownloadRequest):
    manager.resume(task_id, req.url)
    return {"status": "resumed"}


@app.post("/cancel/{task_id}")
def cancel(task_id: str):
    manager.cancel(task_id)
    return {"status": "cancelled"}


# -------------------------------
# PROGRESS
# -------------------------------
@app.get("/progress/{task_id}")
def progress(task_id: str):
    return manager.get_progress(task_id)


# -------------------------------
# HISTORY
# -------------------------------
@app.get("/history")
def history():
    return load_history()


# -------------------------------
# AUTO RESUME ON STARTUP
# -------------------------------
@app.on_event("startup")
def resume_downloads():
    history = load_history()

    for item in history:
        if item["status"] in ["downloading", "paused"]:
            print(f"Resuming: {item['filename']}")