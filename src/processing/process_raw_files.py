"""Bronze (raw JSON) -> Silver (Parquet).

Rebuilds the Silver dataset from scratch from every raw chat page, so it is
idempotent: running it twice on the same raw files yields the same output.
"""

import argparse
import json
import logging
from pathlib import Path

import pyarrow as pa

from src.classification.spam_classifier import classify_spam
from src.config import settings
from src.features.spam_features import (
    add_duplicate_text_count,
    add_repeated_character_ratio,
    add_seconds_since_previous_message,
)
from src.processing.normalize_messages import normalize_messages
from src.storage.parquet_writer import write_parquet

logger = logging.getLogger(__name__)

RAW_DIR = settings.RAW_DIR
OUTPUT_PATH = str(settings.SILVER_PATH)
RAW_GLOB = "youtube_comments_*.json"

SILVER_SCHEMA = pa.schema(
    [
        ("message_id", pa.string()),
        ("author_channel_id", pa.string()),
        ("author_name", pa.string()),
        ("message", pa.string()),
        ("published_at", pa.string()),
        ("is_moderator", pa.bool_()),
        ("is_owner", pa.bool_()),
        ("is_verified", pa.bool_()),
        ("duplicate_text_count", pa.int64()),
        ("repeated_character_ratio", pa.float64()),
        ("seconds_since_previous_message", pa.float64()),
        ("spam_score", pa.float64()),
        ("is_spam", pa.bool_()),
    ]
)


def load_raw_messages(raw_dir: Path) -> tuple[list[dict], dict]:
    """Normalizes all raw pages, dropping messages already seen (same message_id).

    Consecutive polls can return overlapping messages; counting them twice
    would inflate ``duplicate_text_count`` and create fake 0-second cadence.
    Files are read in name (= capture time) order, so the first capture wins.
    """
    stats = {"files_processed": 0, "files_skipped": 0, "raw_messages": 0, "duplicates_dropped": 0}
    seen_ids: set[str] = set()
    messages: list[dict] = []

    for file_path in sorted(Path(raw_dir).glob(RAW_GLOB)):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, dict):
                raise ValueError("top-level JSON is not an object")
        except (OSError, ValueError) as exc:
            logger.warning("Skipping unreadable raw file %s: %s", file_path, exc)
            stats["files_skipped"] += 1
            continue

        stats["files_processed"] += 1

        for message in normalize_messages(data):
            stats["raw_messages"] += 1
            message_id = message.get("message_id")

            if message_id is not None:
                if message_id in seen_ids:
                    stats["duplicates_dropped"] += 1
                    continue
                seen_ids.add(message_id)

            messages.append(message)

    return messages, stats


def build_silver(messages: list[dict]) -> list[dict]:
    messages = add_duplicate_text_count(messages)
    messages = add_repeated_character_ratio(messages)
    messages = add_seconds_since_previous_message(messages)

    return [classify_spam(message) for message in messages]


def process_raw_files(raw_dir: Path = None, output_path: str | Path = None) -> dict:
    raw_dir = Path(raw_dir if raw_dir is not None else RAW_DIR)
    output_path = Path(output_path if output_path is not None else OUTPUT_PATH)

    messages, stats = load_raw_messages(raw_dir)
    classified_messages = build_silver(messages)

    write_parquet(classified_messages, output_path, schema=SILVER_SCHEMA)

    stats["messages_processed"] = len(classified_messages)
    stats["spam_messages"] = sum(bool(m["is_spam"]) for m in classified_messages)
    stats["output"] = str(output_path)

    print(f"Files processed: {stats['files_processed']}")
    if stats["files_skipped"]:
        print(f"Files skipped (unreadable): {stats['files_skipped']}")
    print(f"Duplicate messages dropped: {stats['duplicates_dropped']}")
    print(f"Messages processed: {stats['messages_processed']}")
    print(f"Spam messages: {stats['spam_messages']}")
    print(f"Output: {output_path}")

    return stats


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Build the Silver dataset from raw JSON.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output", type=Path, default=Path(OUTPUT_PATH))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    process_raw_files(args.raw_dir, args.output)


if __name__ == "__main__":
    main()
