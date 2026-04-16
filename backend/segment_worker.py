import requests
import time
import os

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def download_segment(
    url,
    start,
    end,
    part_file,
    progress_callback,
    stop_flag,
    limiter=None,
    max_retries=3
):
    attempt = 0

    downloaded = 0
    if os.path.exists(part_file):
        downloaded = os.path.getsize(part_file)

    current_start = start + downloaded

    if current_start > end:
        return

    while attempt < max_retries:
        try:
            os.makedirs(os.path.dirname(part_file), exist_ok=True)

            headers = {
                **DEFAULT_HEADERS,
                "Range": f"bytes={current_start}-{end}"
            }

            with requests.get(url, headers=headers, stream=True, timeout=30) as response:
                response.raise_for_status()

                with open(part_file, "ab") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if stop_flag["stop"]:
                            return
                        if chunk:
                            if limiter:
                                limiter.consume(len(chunk))
                            f.write(chunk)
                            progress_callback(len(chunk))
            return

        except Exception as e:
            attempt += 1
            print(f"[Retry {attempt}] Segment {start}-{end} failed: {e}")
            time.sleep(2)

    raise Exception(f"Segment {start}-{end} failed after {max_retries} retries")