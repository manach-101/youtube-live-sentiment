"""Polls a live chat page by page and persists every response to the raw layer.

Reliability properties:

- Pagination follows ``nextPageToken`` so the same page is not requested twice.
- Sleeps for the API-provided ``pollingIntervalMillis`` (never less than
  ``min_interval``) to respect quota and avoid empty polls.
- After every page the ``nextPageToken`` is checkpointed to disk, so a restart
  resumes where it left off instead of re-downloading the chat.
- Raw responses are stored unmodified (source of truth); message-level
  de-duplication by ``message_id`` happens in the Silver step. The poller also
  tracks seen IDs to report how many new messages each page contained.
- Stops cleanly on: chat ended (``offlineAt`` or a chat-ended API error),
  ``max_polls``, ``max_duration`` or Ctrl+C.
"""

import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from src.ingestion.youtube import YouTubeAPIError, YouTubeClient
from src.storage.raw_writer import atomic_write_text, save_raw_json

logger = logging.getLogger(__name__)

RAW_SOURCE = "youtube_comments"


@dataclass
class PollStats:
    polls: int = 0
    pages_saved: int = 0
    messages_received: int = 0
    new_messages: int = 0
    stop_reason: str = ""
    files: list[Path] = field(default_factory=list)


class Checkpoint:
    """Stores the last ``nextPageToken`` per live chat."""

    def __init__(self, raw_dir: Path, live_chat_id: str):
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in live_chat_id)
        self.path = Path(raw_dir) / "_state" / f"{safe_id}.json"

    def load(self) -> Optional[str]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("next_page_token")
        except (FileNotFoundError, ValueError):
            return None

    def save(self, page_token: Optional[str]) -> None:
        atomic_write_text(self.path, json.dumps({"next_page_token": page_token}))


class SeenIds:
    """Bounded set of recently seen message IDs."""

    def __init__(self, max_size: int = 100_000):
        self._order: deque[str] = deque()
        self._ids: set[str] = set()
        self._max_size = max_size

    def add(self, message_id: str) -> bool:
        """Returns True if the ID was not seen before."""
        if message_id in self._ids:
            return False
        self._ids.add(message_id)
        self._order.append(message_id)
        if len(self._order) > self._max_size:
            self._ids.discard(self._order.popleft())
        return True


def poll_live_chat(
    client: YouTubeClient,
    live_chat_id: str,
    raw_dir: Path,
    max_polls: Optional[int] = None,
    max_duration: Optional[float] = None,
    max_results: int = 2000,
    min_interval: float = 1.0,
    resume: bool = True,
    sleep: Optional[Callable[[float], None]] = None,
    clock: Optional[Callable[[], float]] = None,
) -> PollStats:
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    stats = PollStats()
    checkpoint = Checkpoint(raw_dir, live_chat_id)
    seen = SeenIds()
    page_token = checkpoint.load() if resume else None
    started = clock()

    if page_token:
        logger.info("Resuming from checkpoint %s", checkpoint.path)

    try:
        while True:
            try:
                response = client.list_chat_messages(live_chat_id, page_token, max_results)
            except YouTubeAPIError as exc:
                if exc.chat_ended:
                    stats.stop_reason = f"chat ended ({exc.reason})"
                    break
                if page_token and exc.status_code == 400:
                    # A stale checkpoint token: restart from the current chat head.
                    logger.warning("Page token rejected (%s); restarting without it", exc.reason)
                    page_token = None
                    checkpoint.save(None)
                    continue
                raise

            stats.polls += 1
            items = response.get("items") or []
            new_count = sum(1 for item in items if item.get("id") and seen.add(item["id"]))
            stats.messages_received += len(items)
            stats.new_messages += new_count

            if items:
                path = save_raw_json(response, source=RAW_SOURCE, output_dir=str(raw_dir))
                stats.pages_saved += 1
                stats.files.append(path)
                logger.info("Poll %d: %d messages (%d new) -> %s", stats.polls, len(items), new_count, path)
            else:
                logger.info("Poll %d: no new messages", stats.polls)

            # Checkpoint only after the page is durably written.
            page_token = response.get("nextPageToken") or page_token
            checkpoint.save(page_token)

            if response.get("offlineAt"):
                stats.stop_reason = "chat ended (offlineAt)"
                break
            if max_polls is not None and stats.polls >= max_polls:
                stats.stop_reason = "max_polls reached"
                break

            interval = max(response.get("pollingIntervalMillis", 0) / 1000, min_interval)
            if max_duration is not None and clock() - started + interval > max_duration:
                stats.stop_reason = "max_duration reached"
                break

            sleep(interval)
    except KeyboardInterrupt:
        stats.stop_reason = "interrupted"

    logger.info(
        "Stopped: %s | polls=%d pages_saved=%d messages=%d new=%d",
        stats.stop_reason, stats.polls, stats.pages_saved,
        stats.messages_received, stats.new_messages,
    )
    return stats
