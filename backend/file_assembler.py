import os


def merge_files(download_dir: str, filename: str, part_files: list):
    final_path = os.path.join(download_dir, filename)

    with open(final_path, "wb") as out:
        for part in part_files:
            with open(part, "rb") as f:
                out.write(f.read())

    for part in part_files:
        os.remove(part)