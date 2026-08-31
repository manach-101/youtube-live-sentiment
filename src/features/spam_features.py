from collections import Counter
from datetime import datetime

import regex


def add_duplicate_text_count(messages: list[dict]) -> list[dict]:
    text_counts = Counter(
        message.get("message")
        for message in messages
        if message.get("message")
    )

    enriched_messages = []

    for message in messages:
        enriched_message = message.copy()

        text = message.get("message")
        enriched_message["duplicate_text_count"] = text_counts.get(text, 0)

        enriched_messages.append(enriched_message)

    return enriched_messages


def repeated_character_ratio(text: str) -> float:
    if not text:
        return 0.0

    graphemes = regex.findall(r"\X", text)

    if len(graphemes) < 2:
        return 0.0

    repeated_characters = 0

    for index in range(1, len(graphemes)):
        if graphemes[index] == graphemes[index - 1]:
            repeated_characters += 1

    return repeated_characters / (len(graphemes) - 1)


def add_repeated_character_ratio(messages: list[dict]) -> list[dict]:
    enriched_messages = []

    for message in messages:
        enriched_message = message.copy()

        text = message.get("message", "")
        enriched_message["repeated_character_ratio"] = repeated_character_ratio(text)

        enriched_messages.append(enriched_message)

    return enriched_messages

from datetime import datetime


def add_seconds_since_previous_message(messages: list[dict]) -> list[dict]:
    last_message_time_by_author = {}
    enriched_messages = []

    sorted_messages = sorted(
        messages,
        key=lambda message: message.get("published_at") or ""
    )

    for message in sorted_messages:
        enriched_message = message.copy()

        author_id = message.get("author_channel_id")
        published_at = message.get("published_at")

        seconds_since_previous_message = None

        if author_id and published_at:
            current_time = datetime.fromisoformat(
                published_at.replace("Z", "+00:00")
            )

            previous_time = last_message_time_by_author.get(author_id)

            if previous_time is not None:
                seconds_since_previous_message = (
                    current_time - previous_time
                ).total_seconds()

            last_message_time_by_author[author_id] = current_time

        enriched_message["seconds_since_previous_message"] = (
            seconds_since_previous_message
        )

        enriched_messages.append(enriched_message)

    return enriched_messages