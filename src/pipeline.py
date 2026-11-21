"""Runs Bronze -> Silver -> Gold in one command (no API calls).

Usage:
    python -m src.pipeline                                   # uses raw/ and data/
    python -m src.pipeline --raw-dir tests/fixtures/raw --data-dir data/demo
"""

import argparse
import logging
from pathlib import Path

from src.analytics.queries import get_messages_per_minute, get_spam_summary
from src.config import settings
from src.processing.build_gold import build_author_summary
from src.processing.process_raw_files import process_raw_files


def run_pipeline(raw_dir: Path, silver_path: Path, gold_path: Path, show_analytics: bool = True) -> dict:
    silver_stats = process_raw_files(raw_dir, silver_path)
    gold = build_author_summary(silver_path, gold_path)

    if show_analytics:
        print("\nSpam summary:")
        print(get_spam_summary(silver_path))
        print("Messages per minute:")
        print(get_messages_per_minute(silver_path))

    return {"silver": silver_stats, "gold_authors": len(gold)}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Run the Silver and Gold steps.")
    parser.add_argument("--raw-dir", type=Path, default=settings.RAW_DIR)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Write processed/ and analytics/ under this directory instead of the configured paths.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.data_dir is not None:
        silver_path = args.data_dir / "processed" / settings.SILVER_PATH.name
        gold_path = args.data_dir / "analytics" / settings.GOLD_PATH.name
    else:
        silver_path, gold_path = settings.SILVER_PATH, settings.GOLD_PATH

    run_pipeline(args.raw_dir, silver_path, gold_path)


if __name__ == "__main__":
    main()
