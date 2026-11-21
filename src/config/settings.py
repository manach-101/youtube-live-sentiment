"""Central configuration.

Values come from environment variables (optionally loaded from a local
``.env`` file). Importing this module never fails: the API key is only
required by the ingestion step, which calls :func:`get_api_key`.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class MissingCredentialsError(RuntimeError):
    """Raised when the YouTube API key is not configured."""


# Kept for backwards compatibility; may be None.
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

RAW_DIR = Path(os.getenv("RAW_DIR", "raw"))
SILVER_PATH = Path(
    os.getenv("SILVER_PATH", "data/processed/youtube_messages.parquet")
)
GOLD_PATH = Path(os.getenv("GOLD_PATH", "data/analytics/author_summary.parquet"))


def get_api_key() -> str:
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()

    if not api_key:
        raise MissingCredentialsError(
            "YOUTUBE_API_KEY is missing. Copy .env.example to .env and set it."
        )

    return api_key
