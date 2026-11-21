"""Bronze -> Silver -> Gold on synthetic fixtures (no network)."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.analytics.queries import get_messages_per_minute, get_spam_summary, get_top_authors
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

    result = run_pipeline(raw, silver_path, gold_path, show_analytics=False)

    stats = result["silver"]
    assert stats["files_processed"] == 3
    assert stats["raw_messages"] == 12
    assert stats["duplicates_dropped"] == 1
    assert stats["messages_processed"] == 11
    assert stats["spam_messages"] == 2

    silver = pd.read_parquet(silver_path)
    assert silver["message_id"].is_unique
    assert pq.read_schema(silver_path).remove_metadata().equals(SILVER_SCHEMA)
    assert sorted(silver.loc[silver["is_spam"], "message_id"]) == ["msg-004", "msg-005"]
    assert silver.set_index("message_id").loc["msg-002", "duplicate_text_count"] == 4
    assert silver["seconds_since_previous_message"].dropna().min() > 0

    gold = pd.read_parquet(gold_path)
    assert pq.read_schema(gold_path).remove_metadata().equals(GOLD_SCHEMA)
    assert result["gold_authors"] == len(gold) == 6
    # Two channels named "Bob" must not be merged.
    assert (gold["author_name"] == "Bob").sum() == 2

    promobot = gold.set_index("author_channel_id").loc["UC_synthetic_promobot"]
    assert promobot["total_messages"] == 4
    assert promobot["spam_messages"] == 2
    assert promobot["spam_rate"] == pytest.approx(0.5)
    assert promobot["average_spam_score"] == pytest.approx(0.8)
    assert gold["total_messages"].sum() == 11


def test_pipeline_is_idempotent(paths):
    raw, silver_path, gold_path = paths

    run_pipeline(raw, silver_path, gold_path, show_analytics=False)
    first = pd.read_parquet(silver_path)
    run_pipeline(raw, silver_path, gold_path, show_analytics=False)

    pd.testing.assert_frame_equal(first, pd.read_parquet(silver_path))


def test_analytics_queries_on_silver(paths):
    raw, silver_path, gold_path = paths
    run_pipeline(raw, silver_path, gold_path, show_analytics=False)

    assert get_spam_summary(silver_path).fetchone() == (11, 2, 18.18)

    per_minute = get_messages_per_minute(silver_path).fetchall()
    assert [(row[1], row[2]) for row in per_minute] == [(7, 2), (4, 0)]

    top = get_top_authors(limit=1, silver_path=silver_path).fetchone()
    assert top[:2] == ("UC_synthetic_promobot", "PromoBot")
    assert top[2] == 4


def test_corrupt_raw_file_is_skipped(paths):
    raw, silver_path, _ = paths
    (raw / "youtube_comments_99999999_999999_999999.json").write_text("{not json", encoding="utf-8")

    stats = process_raw_files(raw, silver_path)

    assert stats["files_skipped"] == 1
    assert stats["messages_processed"] == 11


def test_non_chat_files_are_ignored(paths):
    raw, silver_path, _ = paths
    (raw / "youtube_video_20260901_120000_000000.json").write_text(
        json.dumps({"items": [{"id": "video"}]}), encoding="utf-8"
    )
    (raw / "_state").mkdir()
    (raw / "_state" / "chat.json").write_text("{}", encoding="utf-8")

    assert process_raw_files(raw, silver_path)["messages_processed"] == 11


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
