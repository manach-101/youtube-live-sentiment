import json
from pathlib import Path
from datetime import datetime, timezone


def save_raw_json(data: dict, source: str, output_dir: str = "raw") -> Path:
    """
    Saves raw API response as JSON.

    We preserve raw data so future pipeline steps can be reprocessed
    without calling the external API again.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_path = Path(output_dir) / f"{source}_{timestamp}.json"

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    return file_path