import pytest

from src.features.spam_features import (
    add_duplicate_text_count,
    add_repeated_character_ratio,
    add_seconds_since_previous_message,
    parse_timestamp,
    repeated_character_ratio,
)


def test_duplicate_text_count_ignores_empty_messages():
    messages = [{"message": "hi"}, {"message": "hi"}, {"message": None}, {"message": "yo"}]

    result = add_duplicate_text_count(messages)

    assert [m["duplicate_text_count"] for m in result] == [2, 2, 0, 1]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", 0.0),
        (None, 0.0),
        ("a", 0.0),
        ("abc", 0.0),
        ("aaaa", 1.0),
        ("!!!!!", 1.0),
        # Family emoji is one grapheme made of several code points.
        ("👨‍👩‍👧👨‍👩‍👧", 1.0),
    ],
)
def test_repeated_character_ratio(text, expected):
    assert repeated_character_ratio(text) == pytest.approx(expected)


def test_repeated_character_ratio_handles_missing_message():
    result = add_repeated_character_ratio([{"message": None}, {}])

    assert [m["repeated_character_ratio"] for m in result] == [0.0, 0.0]


def test_parse_timestamp_formats():
    assert parse_timestamp("2026-09-01T12:00:00Z") == parse_timestamp("2026-09-01T12:00:00+00:00")
    assert parse_timestamp("2026-09-01T12:00:00.5+00:00").microsecond == 500000
    assert parse_timestamp("not a date") is None
    assert parse_timestamp(None) is None


def test_seconds_since_previous_message_uses_parsed_time_order():
    # Lexical order would put "...18.700+00:00" before "...18Z" ('.' < 'Z'),
    # producing a negative interval.
    messages = [
        {"author_channel_id": "a", "published_at": "2026-09-01T12:00:18Z", "message_id": "1"},
        {"author_channel_id": "a", "published_at": "2026-09-01T12:00:18.700+00:00", "message_id": "2"},
        {"author_channel_id": "b", "published_at": "2026-09-01T12:00:19Z", "message_id": "3"},
    ]

    result = {m["message_id"]: m for m in add_seconds_since_previous_message(messages)}

    assert result["1"]["seconds_since_previous_message"] is None
    assert result["2"]["seconds_since_previous_message"] == pytest.approx(0.7)
    assert result["3"]["seconds_since_previous_message"] is None


def test_seconds_since_previous_message_tolerates_bad_timestamps():
    messages = [
        {"author_channel_id": "a", "published_at": "garbage", "message_id": "bad"},
        {"author_channel_id": "a", "published_at": "2026-09-01T12:00:00Z", "message_id": "1"},
        {"author_channel_id": "a", "published_at": "2026-09-01T12:00:30Z", "message_id": "2"},
    ]

    result = add_seconds_since_previous_message(messages)

    assert [m["message_id"] for m in result] == ["1", "2", "bad"]
    assert [m["seconds_since_previous_message"] for m in result] == [None, 30.0, None]
