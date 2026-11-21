"""Polling loop behaviour, using a scripted fake client (no network)."""

import json

import pytest

from src.ingestion.live_chat_poller import Checkpoint, SeenIds, poll_live_chat
from src.ingestion.youtube import YouTubeAPIError
from src.processing.process_raw_files import process_raw_files


def page(ids, next_token, interval_ms=5000, **extra):
    items = [
        {
            "id": message_id,
            "snippet": {"displayMessage": f"text {message_id}", "publishedAt": f"2026-09-01T12:00:{i:02d}Z"},
            "authorDetails": {"channelId": "UC1", "displayName": "User"},
        }
        for i, message_id in enumerate(ids)
    ]
    return {"items": items, "nextPageToken": next_token, "pollingIntervalMillis": interval_ms, **extra}


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.tokens = []

    def list_chat_messages(self, live_chat_id, page_token=None, max_results=2000):
        self.tokens.append(page_token)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def run(client, raw_dir, **kwargs):
    sleeps = []
    stats = poll_live_chat(client, "chat-1", raw_dir, sleep=sleeps.append, **kwargs)
    return stats, sleeps


def test_follows_page_tokens_and_respects_polling_interval(tmp_path):
    client = ScriptedClient([page(["a", "b"], "T2", 3000), page(["c"], "T3", 500)])

    stats, sleeps = run(client, tmp_path, max_polls=2)

    assert client.tokens == [None, "T2"]
    assert sleeps == [3.0]
    assert stats.polls == 2
    assert stats.pages_saved == 2
    assert stats.new_messages == 3
    assert stats.stop_reason == "max_polls reached"
    assert Checkpoint(tmp_path, "chat-1").load() == "T3"


def test_min_interval_floor(tmp_path):
    client = ScriptedClient([page(["a"], "T2", 0), page(["b"], "T3", 0)])

    _, sleeps = run(client, tmp_path, max_polls=2, min_interval=2.0)

    assert sleeps == [2.0]


def test_counts_overlapping_messages_and_silver_dedupes(tmp_path):
    client = ScriptedClient([page(["a", "b"], "T2"), page(["b", "c"], "T3")])

    stats, _ = run(client, tmp_path, max_polls=2)

    assert stats.messages_received == 4
    assert stats.new_messages == 3
    # Raw keeps the API response untouched...
    assert len(stats.files) == 2
    assert [i["id"] for i in json.loads(stats.files[1].read_text())["items"]] == ["b", "c"]
    # ...and Silver keeps each message once.
    silver_stats = process_raw_files(tmp_path, tmp_path / "silver.parquet")
    assert silver_stats["messages_processed"] == 3
    assert silver_stats["duplicates_dropped"] == 1


def test_empty_pages_are_not_written(tmp_path):
    client = ScriptedClient([page([], "T2"), page(["a"], "T3")])

    stats, _ = run(client, tmp_path, max_polls=2)

    assert stats.pages_saved == 1
    assert len(list(tmp_path.glob("youtube_comments_*.json"))) == 1


def test_stops_when_chat_goes_offline(tmp_path):
    client = ScriptedClient([page(["a"], "T2", offlineAt="2026-09-01T13:00:00Z")])

    stats, sleeps = run(client, tmp_path)

    assert stats.stop_reason == "chat ended (offlineAt)"
    assert sleeps == []


def test_stops_on_chat_ended_error(tmp_path):
    client = ScriptedClient([page(["a"], "T2"), YouTubeAPIError(403, "liveChatEnded", "ended")])

    stats, _ = run(client, tmp_path)

    assert stats.stop_reason == "chat ended (liveChatEnded)"
    assert stats.pages_saved == 1


def test_other_api_errors_propagate_after_checkpointing(tmp_path):
    client = ScriptedClient([page(["a"], "T2"), YouTubeAPIError(403, "quotaExceeded", "quota")])

    with pytest.raises(YouTubeAPIError):
        run(client, tmp_path)

    assert Checkpoint(tmp_path, "chat-1").load() == "T2"


def test_resumes_from_checkpoint(tmp_path):
    Checkpoint(tmp_path, "chat-1").save("SAVED")
    client = ScriptedClient([page(["a"], "T2")])

    run(client, tmp_path, max_polls=1)

    assert client.tokens == ["SAVED"]


def test_no_resume_ignores_checkpoint(tmp_path):
    Checkpoint(tmp_path, "chat-1").save("SAVED")
    client = ScriptedClient([page(["a"], "T2")])

    run(client, tmp_path, max_polls=1, resume=False)

    assert client.tokens == [None]


def test_stale_checkpoint_token_falls_back_to_chat_head(tmp_path):
    Checkpoint(tmp_path, "chat-1").save("STALE")
    client = ScriptedClient([YouTubeAPIError(400, "pageTokenInvalid", "bad"), page(["a"], "T2")])

    stats, _ = run(client, tmp_path, max_polls=1)

    assert client.tokens == ["STALE", None]
    assert stats.pages_saved == 1


def test_max_duration(tmp_path):
    times = iter([0.0, 1.0, 7.0])
    client = ScriptedClient([page(["a"], "T2", 5000), page(["b"], "T3", 5000)])

    stats, sleeps = run(client, tmp_path, max_duration=10, clock=lambda: next(times))

    assert stats.polls == 2
    assert sleeps == [5.0]
    assert stats.stop_reason == "max_duration reached"


def test_keyboard_interrupt_stops_cleanly(tmp_path):
    client = ScriptedClient([page(["a"], "T2"), KeyboardInterrupt()])

    stats, _ = run(client, tmp_path)

    assert stats.stop_reason == "interrupted"
    assert Checkpoint(tmp_path, "chat-1").load() == "T2"


def test_seen_ids_is_bounded():
    seen = SeenIds(max_size=2)

    assert seen.add("a") and seen.add("b") and not seen.add("a")
    seen.add("c")  # evicts "a"
    assert seen.add("a")
