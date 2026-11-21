"""Bronze (raw JSON) -> Silver (Parquet).

Rebuilds the Silver dataset from scratch from every raw chat page, so it is
idempotent: running it twice on the same raw files yields the same output.
"""

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

import pyarrow as pa

from src.classification.spam_classifier import classify_spam
from src.config import settings
from src.features.spam_features import (
    add_duplicate_text_count,
    add_repeated_character_ratio,
    add_seconds_since_previous_message,
)
from src.processing.normalize_messages import normalize_message
from src.storage.parquet_writer import write_parquet

logger = logging.getLogger(__name__)

RAW_DIR = settings.RAW_DIR
OUTPUT_PATH = str(settings.SILVER_PATH)
RAW_GLOB = "youtube_comments_*.json"

# Chat items that carry a viewer-authored message. Everything else
# (messageDeletedEvent, userBannedEvent, memberMilestoneChatEvent, ...) is a
# moderation or system event: it stays in Bronze but is excluded from Silver.
# Items without ``snippet.type`` (not produced by the API) are kept.
TEXT_EVENT_TYPES = {"textMessageEvent", "superChatEvent"}

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
        ("live_chat_id", pa.string()),
    ]
)


def load_raw_messages(raw_dir: Path) -> tuple[list[dict], dict]:
    """Normalizes all raw pages into Silver candidate messages.

    - Items already seen (same ``id``) are dropped. Consecutive polls can return
      overlapping messages; counting them twice would inflate
      ``duplicate_text_count`` and create fake 0-second cadence. Files are read
      in name (= capture time) order, so the first capture wins.
    - Non-text events are excluded (see ``TEXT_EVENT_TYPES``) and counted by
      type. De-duplication happens first, so overlapping polls do not inflate
      the excluded counts.
    """
    stats = {
        "files_processed": 0,
        "files_skipped": 0,
        "raw_messages": 0,
        "duplicates_dropped": 0,
        "events_excluded": 0,
        "events_excluded_by_type": {},
    }
    excluded_by_type: Counter[str] = Counter()
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

        for item in data.get("items", []):
            stats["raw_messages"] += 1
            message_id = item.get("id")

            if message_id is not None:
                if message_id in seen_ids:
                    stats["duplicates_dropped"] += 1
                    continue
                seen_ids.add(message_id)

            event_type = (item.get("snippet") or {}).get("type")
            if event_type is not None and event_type not in TEXT_EVENT_TYPES:
                excluded_by_type[event_type] += 1
                continue

            messages.append(normalize_message(item))

    stats["events_excluded"] = sum(excluded_by_type.values())
    stats["events_excluded_by_type"] = dict(sorted(excluded_by_type.items()))

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
    excluded_detail = ", ".join(f"{k}={v}" for k, v in stats["events_excluded_by_type"].items())
    print(
        f"Non-text events excluded: {stats['events_excluded']}"
        + (f" ({excluded_detail})" if excluded_detail else "")
    )
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
