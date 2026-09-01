import duckdb


SILVER_PATH = "data/processed/youtube_messages.parquet"


def get_top_authors(limit: int = 10):
    query = f"""
        SELECT
            author_name,
            COUNT(*) AS total_messages
        FROM '{SILVER_PATH}'
        GROUP BY author_name
        ORDER BY total_messages DESC
        LIMIT {limit}
    """

    return duckdb.sql(query)


def get_spam_summary():
    query = f"""
        SELECT
            COUNT(*) AS total_messages,
            SUM(CASE WHEN is_spam THEN 1 ELSE 0 END) AS spam_messages,
            ROUND(
                100.0 * SUM(CASE WHEN is_spam THEN 1 ELSE 0 END) / COUNT(*),
                2
            ) AS spam_rate_pct
        FROM '{SILVER_PATH}'
    """

    return duckdb.sql(query)


def get_messages_per_minute():
    query = f"""
        SELECT
            date_trunc(
                'minute',
                CAST(published_at AS TIMESTAMP)
            ) AS minute,
            COUNT(*) AS total_messages,
            SUM(CASE WHEN is_spam THEN 1 ELSE 0 END) AS spam_messages
        FROM '{SILVER_PATH}'
        GROUP BY minute
        ORDER BY minute
    """

    return duckdb.sql(query)