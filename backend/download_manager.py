import threading
import os
import time
import requests
from queue import Queue
from urllib.parse import urlparse

from segment_worker import download_segment
from models import DownloadStatus
from bandwidth_limiter import BandwidthLimiter
from history_manager import add_download, update_download
from file_assembler import merge_files

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


class DownloadManager:
    def __init__(self, download_dir=None, num_threads=4, max_workers=2):
        if download_dir is None:
            download_dir = os.path.join(BASE_DIR, "downloads")

        self.download_dir = download_dir
        self.num_threads = num_threads
        self.max_workers = max_workers

        self.downloads = {}
        self.lock = threading.Lock()

        self.queue = Queue()
        self.worker_threads = []

        os.makedirs(self.download_dir, exist_ok=True)

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
                if task_id in self.downloads:
                    self.downloads[task_id]["status"] = DownloadStatus.FAILED
                    update_download(url, {"status": "failed"})
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
            "limiter": BandwidthLimiter(500_000),
            "url": url
        }

        add_download({
            "url": url,
            "filename": "",
            "status": "pending",
            "progress": 0
        })

        self.queue.put((task_id, url))

    # -------------------------------
    # PROCESS DOWNLOAD
    # -------------------------------
    def _process_download(self, task_id, url):
        file_size, filename, supports_range = self.get_file_info(url)

        data = self.downloads[task_id]
        data["total"] = file_size
        data["filename"] = filename
        data["status"] = DownloadStatus.DOWNLOADING

        update_download(url, {
            "filename": filename,
            "status": "downloading"
        })

        # Fall back to single-thread if no content-length or no range support
        if file_size == 0 or not supports_range:
            print(f"[Info] Falling back to single-thread download for {url}")
            self._download_single_thread(task_id, url, filename, data)
            return

        part_files = []
        segments = self.split_segments(file_size)
        existing_downloaded = 0

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
                progress = (data["downloaded"] / data["total"]) * 100 if data["total"] else 0
                update_download(url, {"progress": round(progress, 2)})

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

        if data["stop_flag"]["stop"]:
            data["status"] = DownloadStatus.PAUSED
            update_download(url, {"status": "paused"})
            return

        merge_files(self.download_dir, filename, part_files)
        data["status"] = DownloadStatus.COMPLETED
        update_download(url, {"status": "completed", "progress": 100})

    # -------------------------------
    # SINGLE THREAD FALLBACK
    # -------------------------------
    def _download_single_thread(self, task_id, url, filename, data):
        final_path = os.path.join(self.download_dir, filename)

        try:
            with requests.get(url, stream=True, headers=DEFAULT_HEADERS, timeout=30) as response:
                response.raise_for_status()

                total = int(response.headers.get("content-length", 0))
                data["total"] = total

                with open(final_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if data["stop_flag"]["stop"]:
                            data["status"] = DownloadStatus.PAUSED
                            update_download(url, {"status": "paused"})
                            return
                        if chunk:
                            if data["limiter"]:
                                data["limiter"].consume(len(chunk))
                            f.write(chunk)
                            with self.lock:
                                data["downloaded"] += len(chunk)
                                progress = (data["downloaded"] / total * 100) if total else 0
                                update_download(url, {"progress": round(progress, 2)})

            data["status"] = DownloadStatus.COMPLETED
            update_download(url, {"status": "completed", "progress": 100})

        except Exception as e:
            raise Exception(f"Single-thread download failed: {e}")

    # -------------------------------
    # HELPERS
    # -------------------------------
    def get_file_info(self, url):
        size = 0
        supports_range = False

        try:
            response = requests.head(
                url,
                allow_redirects=True,
                timeout=10,
                headers=DEFAULT_HEADERS
            )
            size = int(response.headers.get("content-length", 0))
            supports_range = response.headers.get("Accept-Ranges", "none").lower() == "bytes"
        except Exception:
            pass

        # If HEAD didn't work, try GET with range test
        if size == 0:
            try:
                test_headers = {**DEFAULT_HEADERS, "Range": "bytes=0-0"}
                response = requests.get(
                    url,
                    headers=test_headers,
                    stream=True,
                    timeout=10
                )
                if response.status_code == 206:
                    supports_range = True
                    content_range = response.headers.get("Content-Range", "")
                    if "/" in content_range:
                        size = int(content_range.split("/")[-1])
                elif response.status_code == 200:
                    size = int(response.headers.get("content-length", 0))
                response.close()
            except Exception:
                pass

        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or "file"

        print(f"[Info] URL: {url} | Size: {size} | Range support: {supports_range}")
        return size, filename, supports_range

    def split_segments(self, file_size):
        segment_size = file_size // self.num_threads
        segments = []
        for i in range(self.num_threads):
            start = i * segment_size
            end = start + segment_size - 1 if i < self.num_threads - 1 else file_size - 1
            segments.append((start, end))
        return segments

    # -------------------------------
    # CONTROL METHODS
    # -------------------------------
    def pause(self, task_id):
        if task_id in self.downloads:
            self.downloads[task_id]["stop_flag"]["stop"] = True
            self.downloads[task_id]["status"] = DownloadStatus.PAUSED
            update_download(self.downloads[task_id]["url"], {"status": "paused"})

    def cancel(self, task_id):
        if task_id in self.downloads:
            self.downloads[task_id]["stop_flag"]["stop"] = True
            self.downloads[task_id]["status"] = DownloadStatus.CANCELLED
            update_download(self.downloads[task_id]["url"], {"status": "cancelled"})

    def resume(self, task_id, url):
        if task_id in self.downloads:
            self.downloads[task_id]["stop_flag"]["stop"] = False
            self.downloads[task_id]["status"] = DownloadStatus.PENDING
            self.downloads[task_id]["start_time"] = time.time()
            update_download(url, {"status": "downloading"})
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


# -----------------------------------
# Module-level bridge for main.py
# -----------------------------------
_manager = DownloadManager()


def start_download(task_id: str, url: str):
    _manager.start_download(task_id, url)


def pause(task_id: str):
    _manager.pause(task_id)


def resume(task_id: str):
    data = _manager.downloads.get(task_id)
    url = data["url"] if data else ""
    _manager.resume(task_id, url)


def cancel(task_id: str):
    _manager.cancel(task_id)


def get_progress(task_id: str):
    return _manager.get_progress(task_id)
