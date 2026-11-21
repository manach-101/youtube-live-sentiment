import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file + rename so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def save_raw_json(data: dict, source: str, output_dir: str = "raw") -> Path:
    """
    Saves raw API response as JSON.

    We preserve raw data so future pipeline steps can be reprocessed
    without calling the external API again. Filenames use microsecond
    timestamps and never overwrite an existing file.
    """
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    file_path = directory / f"{source}_{timestamp}.json"

    suffix = 1
    while file_path.exists():
        file_path = directory / f"{source}_{timestamp}_{suffix}.json"
        suffix += 1

    atomic_write_text(file_path, json.dumps(data, ensure_ascii=False, indent=2))

    return file_path
