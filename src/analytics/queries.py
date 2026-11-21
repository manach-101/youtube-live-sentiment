from pathlib import Path

import duckdb

from src.config import settings

SILVER_PATH = str(settings.SILVER_PATH)


def _source(path: str | Path) -> str:
    escaped = str(path).replace("'", "''")
    return f"read_parquet('{escaped}')"


def get_top_authors(limit: int = 10, silver_path: str | Path = SILVER_PATH):
    query = f"""
        SELECT
            author_channel_id,
            any_value(author_name) AS author_name,
            COUNT(*) AS total_messages
        FROM {_source(silver_path)}
        GROUP BY author_channel_id
        ORDER BY total_messages DESC, author_channel_id
        LIMIT {int(limit)}
    """

    return duckdb.sql(query)


def get_spam_summary(silver_path: str | Path = SILVER_PATH):
    query = f"""
        SELECT
            COUNT(*) AS total_messages,
            COALESCE(SUM(CASE WHEN is_spam THEN 1 ELSE 0 END), 0) AS spam_messages,
            ROUND(
                100.0 * SUM(CASE WHEN is_spam THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                2
            ) AS spam_rate_pct
        FROM {_source(silver_path)}
    """

    return duckdb.sql(query)


def get_messages_per_minute(silver_path: str | Path = SILVER_PATH):
    query = f"""
        SELECT
            date_trunc(
                'minute',
                CAST(TRY_CAST(published_at AS TIMESTAMPTZ) AT TIME ZONE 'UTC' AS TIMESTAMP)
            ) AS minute,
            COUNT(*) AS total_messages,
            SUM(CASE WHEN is_spam THEN 1 ELSE 0 END) AS spam_messages
        FROM {_source(silver_path)}
        GROUP BY minute
        ORDER BY minute
    """

    return duckdb.sql(query)
