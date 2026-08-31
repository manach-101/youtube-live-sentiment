from pathlib import Path

import pandas as pd


SILVER_PATH = Path("data/processed/youtube_messages.parquet")
GOLD_PATH = Path("data/analytics/author_summary.parquet")


def build_author_summary() -> None:
    df = pd.read_parquet(SILVER_PATH)

    author_summary = (
        df.groupby("author_name", dropna=False)
        .agg(
            total_messages=("message_id", "count"),
            spam_messages=("is_spam", "sum"),
            average_spam_score=("spam_score", "mean"),
        )
        .reset_index()
    )

    author_summary["spam_rate"] = (
        author_summary["spam_messages"]
        / author_summary["total_messages"]
    )

    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)

    author_summary.to_parquet(GOLD_PATH, index=False)

    print(f"Authors summarized: {len(author_summary)}")
    print(f"Output: {GOLD_PATH}")


if __name__ == "__main__":
    build_author_summary()