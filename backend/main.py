from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uuid
import os

from download_manager import start_download

app = FastAPI()

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in production → replace with frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- In-memory storage ----------------
tasks = {}

# ---------------- Request Model ----------------
class DownloadRequest(BaseModel):
    url: str

# ---------------- Root route ----------------
@app.get("/")
def home():
    return {"message": "Download Manager API is running 🚀"}

# ---------------- Create download ----------------
@app.post("/downloads")
def create_download(data: DownloadRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())

    tasks[task_id] = {
        "id": task_id,
        "url": data.url,
        "status": "downloading",
        "progress": 0,
        "file_path": None
    }

    # Run download in background (non-blocking)
    background_tasks.add_task(start_download, data.url, tasks[task_id])

    return tasks[task_id]

# ---------------- Get all downloads ----------------
@app.get("/downloads")
def get_downloads():
    return list(tasks.values())

# ---------------- Get single download ----------------
@app.get("/downloads/{id}")
def get_download(id: str):
    task = tasks.get(id)

    if not task:
        raise HTTPException(status_code=404, detail="Download not found")

    return task

# ---------------- Download file ----------------
@app.get("/downloads/{id}/file")
def get_file(id: str):
    task = tasks.get(id)

    if not task or not task.get("file_path"):
        raise HTTPException(status_code=404, detail="File not found")

    file_path = task["file_path"]

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File does not exist on disk")

    return FileResponse(
        file_path,
        filename=os.path.basename(file_path)
    )

# ---------------- Delete download ----------------
@app.delete("/downloads/{id}")
def delete_download(id: str):
    if id not in tasks:
        raise HTTPException(status_code=404, detail="Not found")

    del tasks[id]
    return {"status": "deleted", "id": id}