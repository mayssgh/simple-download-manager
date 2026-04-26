import requests
import os
import threading

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_file(url, task):
    try:
        file_name = url.split("/")[-1] or "file"
        file_path = os.path.join(DOWNLOAD_DIR, file_name)

        response = requests.get(url, stream=True)

        total = int(response.headers.get("content-length", 0))
        downloaded = 0

        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total > 0:
                        task["progress"] = int((downloaded / total) * 100)

        task["status"] = "completed"
        task["file_path"] = file_path

    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)


def start_download(url, task):
    thread = threading.Thread(target=download_file, args=(url, task))
    thread.start()