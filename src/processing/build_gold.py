"""Silver -> Gold: author-level summary.

Authors are identified by ``author_channel_id`` (display names are not
unique and can change); ``author_name`` is the most recent display name.
"""

import argparse
from pathlib import Path

import pandas as pd
import pyarrow as pa

from src.config import settings
from src.storage.parquet_writer import write_parquet

SILVER_PATH = settings.SILVER_PATH
GOLD_PATH = settings.GOLD_PATH

GOLD_SCHEMA = pa.schema(
    [
        ("author_channel_id", pa.string()),
        ("author_name", pa.string()),
        ("total_messages", pa.int64()),
        ("spam_messages", pa.int64()),
        ("average_spam_score", pa.float64()),
        ("spam_rate", pa.float64()),
    ]
)


def summarize_authors(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=GOLD_SCHEMA.names)

    df = df.assign(
        _published=pd.to_datetime(df["published_at"], utc=True, errors="coerce", format="ISO8601")
    ).sort_values("_published", kind="stable", na_position="first")

    author_summary = (
        df.groupby("author_channel_id", dropna=False)
        .agg(
            author_name=("author_name", "last"),
            total_messages=("message_id", "size"),
            spam_messages=("is_spam", "sum"),
            average_spam_score=("spam_score", "mean"),
        )
        .reset_index()
    )

    author_summary["spam_rate"] = (
        author_summary["spam_messages"] / author_summary["total_messages"]
    )

    return author_summary.sort_values(
        ["total_messages", "author_channel_id"], ascending=[False, True]
    ).reset_index(drop=True)


def build_author_summary(silver_path: str | Path = None, gold_path: str | Path = None) -> pd.DataFrame:
    silver_path = Path(silver_path if silver_path is not None else SILVER_PATH)
    gold_path = Path(gold_path if gold_path is not None else GOLD_PATH)

    if not silver_path.exists():
        raise FileNotFoundError(
            f"Silver dataset not found at {silver_path}. Run the Silver step first."
        )

    author_summary = summarize_authors(pd.read_parquet(silver_path))

    write_parquet(author_summary, gold_path, schema=GOLD_SCHEMA)

    print(f"Authors summarized: {len(author_summary)}")
    print(f"Output: {gold_path}")

    return author_summary


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Build the Gold author summary.")
    parser.add_argument("--silver-path", type=Path, default=SILVER_PATH)
    parser.add_argument("--output", type=Path, default=GOLD_PATH)
    args = parser.parse_args(argv)
    build_author_summary(args.silver_path, args.output)


if __name__ == "__main__":
    main()
