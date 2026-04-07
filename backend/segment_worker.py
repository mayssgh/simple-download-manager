import requests
import time
import os


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

    # 🔥 RESUME SUPPORT
    downloaded = 0
    if os.path.exists(part_file):
        downloaded = os.path.getsize(part_file)

    current_start = start + downloaded

    if current_start > end:
        return  # already done

    headers = {"Range": f"bytes={current_start}-{end}"}

    while attempt < max_retries:
        try:
            with requests.get(url, headers=headers, stream=True) as response:
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
            time.sleep(1)

    raise Exception(f"Segment {start}-{end} failed after retries")