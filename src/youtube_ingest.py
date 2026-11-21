"""Ingest live chat messages for a YouTube live stream into the raw layer.

Usage:
    python -m src.youtube_ingest --video-id VIDEO_ID [--max-polls N] [--duration SECONDS]

Requires YOUTUBE_API_KEY (see .env.example).
"""

import argparse
import logging
import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python src/youtube_ingest.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings  # noqa: E402
from src.ingestion.live_chat_poller import poll_live_chat  # noqa: E402
from src.ingestion.youtube import (  # noqa: E402
    LiveChatUnavailableError,
    YouTubeAPIError,
    YouTubeClient,
    extract_live_chat_id,
)
from src.storage.raw_writer import save_raw_json  # noqa: E402

logger = logging.getLogger("youtube_ingest")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--video-id",
        default=os.getenv("YOUTUBE_VIDEO_ID"),
        help="YouTube video ID of a live stream (or set YOUTUBE_VIDEO_ID).",
    )
    parser.add_argument("--raw-dir", type=Path, default=settings.RAW_DIR)
    parser.add_argument("--max-polls", type=int, default=None, help="Stop after N polls.")
    parser.add_argument("--duration", type=float, default=None, help="Stop after N seconds.")
    parser.add_argument("--max-results", type=int, default=2000, help="Messages per page (200-2000).")
    parser.add_argument("--no-resume", action="store_true", help="Ignore the saved page-token checkpoint.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # urllib3 debug logs include full request URLs (with the API key).
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    if not args.video_id:
        logger.error("No video ID given. Use --video-id or set YOUTUBE_VIDEO_ID.")
        return 2

    try:
        client = YouTubeClient(settings.get_api_key())
    except settings.MissingCredentialsError as exc:
        logger.error("%s", exc)
        return 2

    try:
        video = client.get_video(args.video_id)
        save_raw_json(video, source="youtube_video", output_dir=str(args.raw_dir))
        live_chat_id = extract_live_chat_id(video)

        snippet = video["items"][0].get("snippet", {})
        logger.info(
            "Video: %r | channel: %r | status: %s",
            snippet.get("title"), snippet.get("channelTitle"), snippet.get("liveBroadcastContent"),
        )

        stats = poll_live_chat(
            client,
            live_chat_id,
            raw_dir=args.raw_dir,
            max_polls=args.max_polls,
            max_duration=args.duration,
            max_results=args.max_results,
            resume=not args.no_resume,
        )
    except LiveChatUnavailableError as exc:
        logger.error("%s", exc)
        return 1
    except YouTubeAPIError as exc:
        logger.error("YouTube API error: %s", exc)
        return 1

    print(f"Polls: {stats.polls}")
    print(f"Raw pages saved: {stats.pages_saved}")
    print(f"Messages received: {stats.messages_received} ({stats.new_messages} new)")
    print(f"Stop reason: {stats.stop_reason}")
    print(f"Raw directory: {args.raw_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
