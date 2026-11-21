from collections import Counter
from datetime import datetime, timezone
from typing import Optional

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

        text = message.get("message") or ""
        enriched_message["repeated_character_ratio"] = repeated_character_ratio(text)

        enriched_messages.append(enriched_message)

    return enriched_messages

def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parses an ISO-8601 timestamp (``Z`` or offset). Returns None if invalid."""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def add_seconds_since_previous_message(messages: list[dict]) -> list[dict]:
    """Seconds since the same author's previous message.

    Messages are ordered by their parsed timestamp (not the raw string, whose
    lexical order breaks with mixed formats such as ``...18Z`` vs
    ``...18.7+00:00``). Messages with a missing or invalid timestamp are
    placed last and get ``None``.
    """
    last_message_time_by_author = {}
    enriched_messages = []

    parsed_messages = [
        (parse_timestamp(message.get("published_at")), index, message)
        for index, message in enumerate(messages)
    ]
    parsed_messages.sort(
        key=lambda entry: (entry[0] is None, entry[0] or datetime.min.replace(tzinfo=timezone.utc), entry[1])
    )

    for current_time, _, message in parsed_messages:
        enriched_message = message.copy()

        author_id = message.get("author_channel_id")

        seconds_since_previous_message = None

        if author_id and current_time is not None:
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
