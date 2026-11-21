import json

import pytest

from src import youtube_ingest
from src.config import settings
from src.storage.raw_writer import save_raw_json


def test_save_raw_json_never_overwrites(tmp_path):
    paths = [save_raw_json({"n": i}, "youtube_comments", str(tmp_path)) for i in range(20)]

    assert len(set(paths)) == 20
    assert [json.loads(p.read_text(encoding="utf-8"))["n"] for p in paths] == list(range(20))
    assert not list(tmp_path.glob(".*.tmp"))


def test_save_raw_json_preserves_unicode(tmp_path):
    path = save_raw_json({"text": "¡Hola! 👋"}, "youtube_comments", str(tmp_path))

    assert "¡Hola! 👋" in path.read_text(encoding="utf-8")


def test_get_api_key_errors_clearly(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    with pytest.raises(settings.MissingCredentialsError):
        settings.get_api_key()


def test_ingest_cli_without_key_exits_with_code_2(monkeypatch, tmp_path):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)

    assert youtube_ingest.main(["--video-id", "abc", "--raw-dir", str(tmp_path)]) == 2


def test_ingest_cli_without_video_id_exits_with_code_2(monkeypatch):
    monkeypatch.delenv("YOUTUBE_VIDEO_ID", raising=False)
    monkeypatch.setenv("YOUTUBE_API_KEY", "dummy")

    assert youtube_ingest.main([]) == 2


def test_ingest_cli_end_to_end_with_fake_http(monkeypatch, tmp_path, capsys):
    """video lookup -> chat polling -> raw files -> Silver, without network."""
    from src.ingestion.youtube import YouTubeClient
    from src.processing.process_raw_files import process_raw_files
    from tests.test_youtube_client import FakeResponse, FakeSession, error_response

    video = {
        "items": [
            {
                "snippet": {"title": "T", "channelTitle": "C", "liveBroadcastContent": "live"},
                "liveStreamingDetails": {"activeLiveChatId": "chat-xyz"},
            }
        ]
    }
    chat_page = {
        "nextPageToken": "T2",
        "pollingIntervalMillis": 1000,
        "items": [
            {
                "id": "m1",
                "snippet": {"displayMessage": "hi", "publishedAt": "2026-09-01T12:00:00Z"},
                "authorDetails": {"channelId": "UC1", "displayName": "U"},
            }
        ],
    }
    session = FakeSession(
        [
            FakeResponse(200, video),
            FakeResponse(503, {}),  # transient error is retried
            FakeResponse(200, chat_page),
            error_response(403, "liveChatEnded"),
        ]
    )
    monkeypatch.setenv("YOUTUBE_API_KEY", "dummy")
    monkeypatch.setattr(
        youtube_ingest,
        "YouTubeClient",
        lambda key: YouTubeClient(key, session=session, sleep=lambda s: None),
    )
    monkeypatch.setattr("src.ingestion.live_chat_poller.time.sleep", lambda s: None)

    assert youtube_ingest.main(["--video-id", "vid", "--raw-dir", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "Stop reason: chat ended (liveChatEnded)" in out
    assert len(list(tmp_path.glob("youtube_video_*.json"))) == 1
    assert len(list(tmp_path.glob("youtube_comments_*.json"))) == 1
    assert process_raw_files(tmp_path, tmp_path / "s.parquet")["messages_processed"] == 1
