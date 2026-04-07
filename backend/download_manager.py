import threading
import os
import time
import requests
from queue import Queue
from urllib.parse import urlparse

from segment_worker import download_segment
from models import DownloadStatus
from bandwidth_limiter import BandwidthLimiter


class DownloadManager:
    def __init__(self, download_dir="downloads", num_threads=4, max_workers=2):
        self.download_dir = download_dir
        self.num_threads = num_threads
        self.max_workers = max_workers

        self.downloads = {}
        self.lock = threading.Lock()

        self.queue = Queue()
        self.worker_threads = []

        os.makedirs(download_dir, exist_ok=True)

        for _ in range(max_workers):
            t = threading.Thread(target=self.worker_loop, daemon=True)
            t.start()
            self.worker_threads.append(t)

    # -------------------------------
    # WORKER LOOP
    # -------------------------------
    def worker_loop(self):
        while True:
            task_id, url = self.queue.get()
            try:
                self._process_download(task_id, url)
            except Exception as e:
                print(f"Download failed: {e}")
                self.downloads[task_id]["status"] = DownloadStatus.FAILED
            finally:
                self.queue.task_done()

    # -------------------------------
    # START DOWNLOAD
    # -------------------------------
    def start_download(self, task_id, url):
        self.downloads[task_id] = {
            "downloaded": 0,
            "total": 0,
            "status": DownloadStatus.PENDING,
            "stop_flag": {"stop": False},
            "start_time": time.time(),
            "filename": "",
            "limiter": BandwidthLimiter(500_000)
        }

        self.queue.put((task_id, url))

    # -------------------------------
    # PROCESS DOWNLOAD
    # -------------------------------
    def _process_download(self, task_id, url):
        file_size, filename = self.get_file_info(url)
        segments = self.split_segments(file_size)

        data = self.downloads[task_id]
        data["total"] = file_size
        data["filename"] = filename
        data["status"] = DownloadStatus.DOWNLOADING

        # 🔥 RECOVER EXISTING PROGRESS (REAL RESUME)
        existing_downloaded = 0
        part_files = []

        for i in range(len(segments)):
            part_file = os.path.join(self.download_dir, f"{task_id}.part{i}")
            part_files.append(part_file)

            if os.path.exists(part_file):
                existing_downloaded += os.path.getsize(part_file)

        data["downloaded"] = existing_downloaded

        threads = []

        def progress_callback(bytes_downloaded):
            with self.lock:
                data["downloaded"] += bytes_downloaded

        for i, (start, end) in enumerate(segments):
            part_file = part_files[i]

            thread = threading.Thread(
                target=download_segment,
                args=(
                    url,
                    start,
                    end,
                    part_file,
                    progress_callback,
                    data["stop_flag"],
                    data["limiter"]
                )
            )

            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        if not data["stop_flag"]["stop"]:
            self.merge_files(filename, part_files)
            data["status"] = DownloadStatus.COMPLETED

    # -------------------------------
    # HELPERS
    # -------------------------------
    def get_file_info(self, url):
        response = requests.head(url)
        size = int(response.headers.get("content-length", 0))

        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or "file"

        return size, filename

    def split_segments(self, file_size):
        segment_size = file_size // self.num_threads
        segments = []

        for i in range(self.num_threads):
            start = i * segment_size
            end = start + segment_size - 1 if i < self.num_threads - 1 else file_size - 1
            segments.append((start, end))

        return segments

    def merge_files(self, filename, part_files):
        final_path = os.path.join(self.download_dir, filename)

        with open(final_path, "wb") as out:
            for part in part_files:
                with open(part, "rb") as f:
                    out.write(f.read())

        for part in part_files:
            os.remove(part)

    # -------------------------------
    # CONTROL METHODS
    # -------------------------------
    def pause(self, task_id):
        self.downloads[task_id]["stop_flag"]["stop"] = True
        self.downloads[task_id]["status"] = DownloadStatus.PAUSED

    def cancel(self, task_id):
        self.downloads[task_id]["stop_flag"]["stop"] = True
        self.downloads[task_id]["status"] = DownloadStatus.CANCELLED

    def resume(self, task_id, url):
        if task_id in self.downloads:
            self.downloads[task_id]["stop_flag"]["stop"] = False
            self.downloads[task_id]["status"] = DownloadStatus.PENDING
            self.queue.put((task_id, url))

    # -------------------------------
    # PROGRESS
    # -------------------------------
    def get_progress(self, task_id):
        data = self.downloads.get(task_id)
        if not data:
            return None

        downloaded = data["downloaded"]
        total = data["total"]
        elapsed = time.time() - data["start_time"]

        speed = downloaded / elapsed if elapsed > 0 else 0
        progress = (downloaded / total) * 100 if total else 0
        eta = (total - downloaded) / speed if speed > 0 else None

        return {
            "id": task_id,
            "progress": round(progress, 2),
            "speed": int(speed),
            "eta": int(eta) if eta else None,
            "status": data["status"]
        }