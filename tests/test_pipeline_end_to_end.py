"""Bronze -> Silver -> Gold on synthetic fixtures (no network)."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.analytics.queries import (
    get_messages_per_minute,
    get_spam_summary,
    get_stream_summary,
    get_top_authors,
)
from src.pipeline import run_pipeline
from src.processing.build_gold import GOLD_SCHEMA, build_author_summary
from src.processing.process_raw_files import SILVER_SCHEMA, process_raw_files

FIXTURE_RAW = Path(__file__).parent / "fixtures" / "raw"


@pytest.fixture
def paths(tmp_path):
    raw = tmp_path / "raw"
    shutil.copytree(FIXTURE_RAW, raw)
    return raw, tmp_path / "silver.parquet", tmp_path / "gold.parquet"


def test_full_pipeline_on_fixtures(paths):
    raw, silver_path, gold_path = paths
    bronze_before = {p.name: p.read_bytes() for p in raw.iterdir()}

    result = run_pipeline(raw, silver_path, gold_path, show_analytics=False)

    stats = result["silver"]
    assert stats["files_processed"] == 5
    assert stats["raw_messages"] == 16
    assert stats["duplicates_dropped"] == 1
    assert stats["events_excluded"] == 2
    assert stats["events_excluded_by_type"] == {"messageDeletedEvent": 1, "userBannedEvent": 1}
    assert stats["messages_processed"] == 13
    assert stats["spam_messages"] == 2
    # Bronze is never modified by processing.
    assert {p.name: p.read_bytes() for p in raw.iterdir()} == bronze_before

    silver = pd.read_parquet(silver_path)
    assert silver["message_id"].is_unique
    assert pq.read_schema(silver_path).remove_metadata().equals(SILVER_SCHEMA)
    assert sorted(silver.loc[silver["is_spam"], "message_id"]) == ["msg-004", "msg-005"]
    assert not silver["message_id"].str.startswith("mod-").any()
    assert silver["seconds_since_previous_message"].dropna().min() > 0
    assert silver.groupby("live_chat_id").size().to_dict() == {
        "SYNTHETIC_LIVE_CHAT_ID": 11,
        "SYNTHETIC_LIVE_CHAT_ID_2": 2,
    }

    by_id = silver.set_index("message_id")
    # Per-stream features: stream 2 does not inherit stream 1's duplicates/cadence.
    assert by_id.loc["msg-002", "duplicate_text_count"] == 4
    assert by_id.loc["s2-msg-001", "duplicate_text_count"] == 1
    assert pd.isna(by_id.loc["s2-msg-001", "seconds_since_previous_message"])
    assert by_id.loc["s2-msg-001", "spam_score"] == pytest.approx(0.2)
    # Alice's stream-2 message 5 s earlier must not make msg-011 look like spam.
    assert by_id.loc["msg-011", "seconds_since_previous_message"] == 20.0
    assert by_id.loc["msg-011", "duplicate_text_count"] == 2
    assert not by_id.loc["msg-011", "is_spam"]

    gold = pd.read_parquet(gold_path)
    assert pq.read_schema(gold_path).remove_metadata().equals(GOLD_SCHEMA)
    assert result["gold_authors"] == len(gold) == 6
    # Two channels named "Bob" must not be merged.
    assert (gold["author_name"] == "Bob").sum() == 2

    gold = gold.set_index("author_channel_id")
    promobot = gold.loc["UC_synthetic_promobot"]
    assert promobot["total_messages"] == 5
    assert promobot["spam_messages"] == 2
    assert promobot["spam_rate"] == pytest.approx(0.4)
    assert promobot["average_spam_score"] == pytest.approx(0.68)
    # Moderation events by Carol are not counted as her messages.
    assert gold.loc["UC_synthetic_carol", "total_messages"] == 1
    assert gold.loc["UC_synthetic_alice", "total_messages"] == 4
    assert gold["total_messages"].sum() == 13


def test_pipeline_is_idempotent(paths):
    raw, silver_path, gold_path = paths

    run_pipeline(raw, silver_path, gold_path, show_analytics=False)
    first = pd.read_parquet(silver_path)
    run_pipeline(raw, silver_path, gold_path, show_analytics=False)

    pd.testing.assert_frame_equal(first, pd.read_parquet(silver_path))


def test_analytics_queries_on_silver(paths):
    raw, silver_path, gold_path = paths
    run_pipeline(raw, silver_path, gold_path, show_analytics=False)

    assert get_spam_summary(silver_path).fetchone() == (13, 2, 15.38)
    assert get_spam_summary(silver_path, live_chat_id="SYNTHETIC_LIVE_CHAT_ID").fetchone() == (11, 2, 18.18)
    assert get_spam_summary(silver_path, live_chat_id="SYNTHETIC_LIVE_CHAT_ID_2").fetchone() == (2, 0, 0.0)

    per_minute = get_messages_per_minute(silver_path).fetchall()
    assert [(row[0].strftime("%H:%M"), row[1], row[2]) for row in per_minute] == [
        ("12:00", 7, 2),
        ("12:01", 6, 0),
    ]
    per_minute_s2 = get_messages_per_minute(silver_path, live_chat_id="SYNTHETIC_LIVE_CHAT_ID_2").fetchall()
    assert [(row[0].strftime("%H:%M"), row[1]) for row in per_minute_s2] == [("12:01", 2)]

    assert get_stream_summary(silver_path).fetchall() == [
        ("SYNTHETIC_LIVE_CHAT_ID", 11, 2, 6),
        ("SYNTHETIC_LIVE_CHAT_ID_2", 2, 0, 2),
    ]

    top = get_top_authors(limit=1, silver_path=silver_path).fetchone()
    assert top == ("UC_synthetic_promobot", "PromoBot", 5)
    top_s2 = get_top_authors(limit=5, silver_path=silver_path, live_chat_id="SYNTHETIC_LIVE_CHAT_ID_2").fetchall()
    assert {row[0] for row in top_s2} == {"UC_synthetic_alice", "UC_synthetic_promobot"}


def test_corrupt_raw_file_is_skipped(paths):
    raw, silver_path, _ = paths
    (raw / "youtube_comments_99999999_999999_999999.json").write_text("{not json", encoding="utf-8")

    stats = process_raw_files(raw, silver_path)

    assert stats["files_skipped"] == 1
    assert stats["messages_processed"] == 13


def test_non_chat_files_are_ignored(paths):
    raw, silver_path, _ = paths
    (raw / "youtube_video_20260901_120000_000000.json").write_text(
        json.dumps({"items": [{"id": "video"}]}), encoding="utf-8"
    )
    (raw / "_state").mkdir()
    (raw / "_state" / "chat.json").write_text("{}", encoding="utf-8")

    assert process_raw_files(raw, silver_path)["messages_processed"] == 13


def test_empty_raw_dir_produces_empty_but_valid_datasets(tmp_path):
    silver_path, gold_path = tmp_path / "silver.parquet", tmp_path / "gold.parquet"

    stats = process_raw_files(tmp_path / "raw", silver_path)
    gold = build_author_summary(silver_path, gold_path)

    assert stats["messages_processed"] == 0
    assert list(pd.read_parquet(silver_path).columns) == SILVER_SCHEMA.names
    assert gold.empty
    assert list(pd.read_parquet(gold_path).columns) == GOLD_SCHEMA.names
    assert get_spam_summary(silver_path).fetchone() == (0, 0, None)


def test_gold_requires_silver(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_author_summary(tmp_path / "missing.parquet", tmp_path / "gold.parquet")
