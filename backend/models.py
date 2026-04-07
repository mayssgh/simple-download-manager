from pydantic import BaseModel
from typing import Optional
from enum import Enum


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloadTask(BaseModel):
    id: str
    url: str
    filename: str

    total_size: int = 0
    downloaded: int = 0

    status: DownloadStatus = DownloadStatus.PENDING

    progress: float = 0.0
    speed: float = 0.0
    eta: Optional[int] = None

    created_at: Optional[str] = None