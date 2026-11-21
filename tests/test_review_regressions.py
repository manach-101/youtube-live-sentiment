"""Regression tests for the defects found in the PR #1 review (H1, H2, M1, M2)."""

import json

import pandas as pd
import pytest

from src import youtube_ingest
from src.ingestion.live_chat_poller import Checkpoint, poll_live_chat
from src.ingestion.youtube import YouTubeAPIError, YouTubeClient
from src.processing.process_raw_files import process_raw_files
from tests.test_youtube_client import FakeResponse, FakeSession


def item(message_id, chat, channel, ts, text=None, event_type="textMessageEvent", **details):
    snippet = {"type": event_type, "liveChatId": chat, "publishedAt": ts, **details}
    if text is not None:
        snippet["displayMessage"] = text
    return {
        "id": message_id,
        "snippet": snippet,
        "authorDetails": {"channelId": channel, "displayName": channel},
    }


def write_page(raw_dir, name, items):
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"youtube_comments_{name}.json"
    path.write_text(json.dumps({"items": items}), encoding="utf-8")
    return path


# ---------- H1: non-text moderation events must not become Silver messages ----------


def test_h1_moderation_events_are_excluded_from_silver_but_kept_in_bronze(tmp_path):
    raw = tmp_path / "raw"
    path = write_page(
        raw,
        "1",
        [
            item("a", "chat", "user", "2026-09-01T12:00:00Z", "buy now"),
            item("b", "chat", "mod", "2026-09-01T12:00:05Z", event_type="messageDeletedEvent",
                 messageDeletedDetails={"deletedMessageId": "a"}),
            item("c", "chat", "mod", "2026-09-01T12:00:06Z", event_type="userBannedEvent"),
            item("d", "chat", "fan", "2026-09-01T12:00:07Z", "thanks!", event_type="superChatEvent"),
        ],
    )
    bronze_before = path.read_bytes()

    stats = process_raw_files(raw, tmp_path / "silver.parquet")
    silver = pd.read_parquet(tmp_path / "silver.parquet")

    assert sorted(silver["message_id"]) == ["a", "d"]
    assert "mod" not in set(silver["author_channel_id"])
    assert stats["events_excluded"] == 2
    assert stats["events_excluded_by_type"] == {"messageDeletedEvent": 1, "userBannedEvent": 1}
    assert path.read_bytes() == bronze_before


def test_h1_excluded_event_counts_are_not_inflated_by_overlapping_polls(tmp_path):
    raw = tmp_path / "raw"
    event = item("b", "chat", "mod", "2026-09-01T12:00:05Z", event_type="messageDeletedEvent")
    write_page(raw, "1", [event])
    write_page(raw, "2", [event])

    stats = process_raw_files(raw, tmp_path / "silver.parquet")

    assert stats["events_excluded"] == 1
    assert stats["duplicates_dropped"] == 1


# ---------- H2: streams must not contaminate each other ----------


def test_h2_live_chat_id_in_silver_and_features_are_per_stream(tmp_path):
    raw = tmp_path / "raw"
    spam = "FREE GIFT CARDS!!!!!!"
    write_page(
        raw,
        "1",
        [
            item("s1-1", "stream-1", "bot", "2026-09-01T12:00:00Z", spam),
            item("s1-2", "stream-1", "bot", "2026-09-01T12:00:30Z", spam),
            item("s1-3", "stream-1", "bot", "2026-09-01T12:01:00Z", spam),
        ],
    )
    write_page(raw, "2", [item("s2-1", "stream-2", "bot", "2026-09-01T12:00:05Z", spam)])

    process_raw_files(raw, tmp_path / "silver.parquet")
    silver = pd.read_parquet(tmp_path / "silver.parquet").set_index("message_id")

    assert silver.loc["s2-1", "live_chat_id"] == "stream-2"
    assert set(silver["live_chat_id"]) == {"stream-1", "stream-2"}
    # Without isolation, s2-1 would count 4 duplicates and s1-2 would see a
    # 25 s gap to the stream-2 message instead of 30 s to s1-1.
    assert silver.loc["s2-1", "duplicate_text_count"] == 1
    assert pd.isna(silver.loc["s2-1", "seconds_since_previous_message"])
    assert silver.loc["s1-1", "duplicate_text_count"] == 3
    assert silver.loc["s1-2", "seconds_since_previous_message"] == 30.0


def test_h2_cross_stream_activity_cannot_flip_spam_flag(tmp_path):
    raw = tmp_path / "raw"
    text = "Great coverage tonight"
    write_page(
        raw,
        "1",
        [
            item("a1", "stream-1", "alice", "2026-09-01T12:00:00Z", text),
            item("a2", "stream-1", "alice", "2026-09-01T12:01:00Z", text),
        ],
    )
    # Same viewer, same text, 5 s earlier, in a different stream.
    write_page(raw, "2", [item("b1", "stream-2", "alice", "2026-09-01T12:00:55Z", text)])

    process_raw_files(raw, tmp_path / "silver.parquet")
    silver = pd.read_parquet(tmp_path / "silver.parquet").set_index("message_id")

    assert not silver["is_spam"].any()
    assert silver.loc["a2", "seconds_since_previous_message"] == 60.0


# ---------- M1: checkpoint reset only for invalid page tokens; --max-results range ----------


class RaisingClient:
    def __init__(self, errors_then_pages):
        self.responses = list(errors_then_pages)
        self.tokens = []

    def list_chat_messages(self, live_chat_id, page_token=None, max_results=2000):
        self.tokens.append(page_token)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def test_m1_unrelated_400_keeps_checkpoint(tmp_path):
    Checkpoint(tmp_path, "chat").save("GOOD_TOKEN")
    client = RaisingClient([YouTubeAPIError(400, "invalidValue", "maxResults out of range")])

    with pytest.raises(YouTubeAPIError):
        poll_live_chat(client, "chat", tmp_path, sleep=lambda s: None)

    assert client.tokens == ["GOOD_TOKEN"]
    assert Checkpoint(tmp_path, "chat").load() == "GOOD_TOKEN"


@pytest.mark.parametrize("reason", ["invalidPageToken", "pageTokenInvalid"])
def test_m1_invalid_page_token_resets_checkpoint(tmp_path, reason):
    Checkpoint(tmp_path, "chat").save("STALE")
    client = RaisingClient([YouTubeAPIError(400, reason, "bad token"), {"items": [], "nextPageToken": "T2"}])

    poll_live_chat(client, "chat", tmp_path, max_polls=1, sleep=lambda s: None)

    assert client.tokens == ["STALE", None]
    assert Checkpoint(tmp_path, "chat").load() == "T2"


@pytest.mark.parametrize("value", ["199", "2001", "0", "-5", "abc"])
def test_m1_cli_rejects_out_of_range_max_results(value, capsys):
    with pytest.raises(SystemExit) as exc_info:
        youtube_ingest.parse_args(["--video-id", "v", "--max-results", value])

    assert exc_info.value.code == 2
    assert "--max-results" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["200", "2000", "500"])
def test_m1_cli_accepts_valid_max_results(value):
    assert youtube_ingest.parse_args(["--video-id", "v", "--max-results", value]).max_results == int(value)


def test_m1_client_rejects_out_of_range_max_results():
    client = YouTubeClient("k", session=FakeSession([]))

    with pytest.raises(ValueError):
        client.list_chat_messages("chat", max_results=100)


# ---------- M2: malformed JSON in HTTP 200 is a retryable YouTubeAPIError ----------


class NonJsonResponse(FakeResponse):
    def __init__(self):
        super().__init__(200, None)
        self.text = "<html>proxy login</html>"

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


def test_m2_malformed_json_is_retried_then_succeeds():
    sleeps = []
    session = FakeSession([NonJsonResponse(), FakeResponse(200, {"items": []})])
    client = YouTubeClient("k", session=session, max_retries=3, sleep=sleeps.append)

    assert client.get_video("v") == {"items": []}
    assert len(session.calls) == 2
    assert len(sleeps) == 1


@pytest.mark.parametrize("bad", [NonJsonResponse(), FakeResponse(200, ["not", "an", "object"])])
def test_m2_malformed_json_raises_api_error_after_bounded_retries(bad):
    sleeps = []
    session = FakeSession([bad] * 3)
    client = YouTubeClient("k", session=session, max_retries=2, sleep=sleeps.append)

    with pytest.raises(YouTubeAPIError) as exc_info:
        client.list_chat_messages("chat")

    assert exc_info.value.status_code == 200
    assert exc_info.value.reason == "invalidJson"
    assert len(session.calls) == 3
    assert len(sleeps) == 2


def test_m2_cli_exits_cleanly_on_malformed_json(monkeypatch, tmp_path):
    session = FakeSession([NonJsonResponse()] * 2)
    monkeypatch.setenv("YOUTUBE_API_KEY", "dummy")
    monkeypatch.setattr(
        youtube_ingest,
        "YouTubeClient",
        lambda key: YouTubeClient(key, session=session, max_retries=1, sleep=lambda s: None),
    )

    assert youtube_ingest.main(["--video-id", "v", "--raw-dir", str(tmp_path)]) == 1
