from pathlib import Path
from typing import Optional

import duckdb

from src.config import settings

SILVER_PATH = str(settings.SILVER_PATH)


def _source(path: str | Path) -> str:
    escaped = str(path).replace("'", "''")
    return f"read_parquet('{escaped}')"


def _stream_filter(live_chat_id: Optional[str]) -> tuple[str, list]:
    """Optional WHERE clause restricting a query to one live chat (stream)."""
    if live_chat_id is None:
        return "", []
    return "WHERE live_chat_id = ?", [live_chat_id]


def get_top_authors(
    limit: int = 10,
    silver_path: str | Path = SILVER_PATH,
    live_chat_id: Optional[str] = None,
):
    where, params = _stream_filter(live_chat_id)
    query = f"""
        SELECT
            author_channel_id,
            any_value(author_name) AS author_name,
            COUNT(*) AS total_messages
        FROM {_source(silver_path)}
        {where}
        GROUP BY author_channel_id
        ORDER BY total_messages DESC, author_channel_id
        LIMIT {int(limit)}
    """

    return duckdb.sql(query, params=params)


def get_spam_summary(silver_path: str | Path = SILVER_PATH, live_chat_id: Optional[str] = None):
    where, params = _stream_filter(live_chat_id)
    query = f"""
        SELECT
            COUNT(*) AS total_messages,
            COALESCE(SUM(CASE WHEN is_spam THEN 1 ELSE 0 END), 0) AS spam_messages,
            ROUND(
                100.0 * SUM(CASE WHEN is_spam THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                2
            ) AS spam_rate_pct
        FROM {_source(silver_path)}
        {where}
    """

    return duckdb.sql(query, params=params)


def get_messages_per_minute(silver_path: str | Path = SILVER_PATH, live_chat_id: Optional[str] = None):
    where, params = _stream_filter(live_chat_id)
    query = f"""
        SELECT
            date_trunc(
                'minute',
                CAST(TRY_CAST(published_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS TIMESTAMP)
            ) AS minute,
            COUNT(*) AS total_messages,
            SUM(CASE WHEN is_spam THEN 1 ELSE 0 END) AS spam_messages
        FROM {_source(silver_path)}
        {where}
        GROUP BY minute
        ORDER BY minute
    """

    return duckdb.sql(query, params=params)


def get_stream_summary(silver_path: str | Path = SILVER_PATH):
    """One row per live chat: volume, spam and distinct authors."""
    query = f"""
        SELECT
            live_chat_id,
            COUNT(*) AS total_messages,
            SUM(CASE WHEN is_spam THEN 1 ELSE 0 END) AS spam_messages,
            COUNT(DISTINCT author_channel_id) AS authors
        FROM {_source(silver_path)}
        GROUP BY live_chat_id
        ORDER BY live_chat_id NULLS LAST
    """

    return duckdb.sql(query)
