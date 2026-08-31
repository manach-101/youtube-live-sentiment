import json
from pathlib import Path

from src.classification.spam_classifier import classify_spam
from src.features.spam_features import (
    add_duplicate_text_count,
    add_repeated_character_ratio,
    add_seconds_since_previous_message,
)
from src.processing.normalize_messages import normalize_messages
from src.storage.parquet_writer import write_parquet


RAW_DIR = Path("raw")
OUTPUT_PATH = "data/processed/youtube_messages.parquet"


def process_raw_files() -> None:
    all_messages = []

    raw_files = list(RAW_DIR.glob("youtube_comments_*.json"))

    for file_path in raw_files:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        messages = normalize_messages(data)
        all_messages.extend(messages)

    all_messages = add_duplicate_text_count(all_messages)
    all_messages = add_repeated_character_ratio(all_messages)
    all_messages = add_seconds_since_previous_message(all_messages)

    classified_messages = [
        classify_spam(message)
        for message in all_messages
    ]

    write_parquet(classified_messages, OUTPUT_PATH)

    print(f"Files processed: {len(raw_files)}")
    print(f"Messages processed: {len(classified_messages)}")
    print(f"Spam messages: {sum(message['is_spam'] for message in classified_messages)}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    process_raw_files()