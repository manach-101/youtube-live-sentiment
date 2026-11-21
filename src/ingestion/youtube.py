"""Thin, resilient client for the two YouTube Data API v3 endpoints we use.

- ``videos.list``           -> video metadata and ``activeLiveChatId``
- ``liveChatMessages.list`` -> paginated live chat messages

Transient failures (network errors, HTTP 429/5xx, rate-limit reasons) are
retried with exponential backoff and jitter. Permanent failures (bad key,
quota exhausted, chat ended, ...) raise :class:`YouTubeAPIError` immediately.
The API key is never written to logs or exception messages.
"""

import logging
import random
import time
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

API_BASE_URL = "https://www.googleapis.com/youtube/v3"
VIDEOS_URL = f"{API_BASE_URL}/videos"
LIVE_CHAT_URL = f"{API_BASE_URL}/liveChat/messages"

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
# YouTube reports per-user/short-term throttling as HTTP 403 with these reasons.
RETRYABLE_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "backendError"}
# Reasons meaning the live chat can no longer be read.
CHAT_ENDED_REASONS = {"liveChatEnded", "liveChatNotFound", "liveChatDisabled"}


class YouTubeAPIError(Exception):
    def __init__(self, status_code: Optional[int], reason: Optional[str], message: str):
        self.status_code = status_code
        self.reason = reason
        super().__init__(f"HTTP {status_code} ({reason}): {message}")

    @property
    def chat_ended(self) -> bool:
        return self.reason in CHAT_ENDED_REASONS


class LiveChatUnavailableError(Exception):
    """The video does not exist or has no active live chat."""


def _parse_error(response: requests.Response) -> tuple[Optional[str], str]:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return None, response.text[:200]

    errors = error.get("errors") or [{}]
    return errors[0].get("reason"), error.get("message", "")


def _redact(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


class YouTubeClient:
    def __init__(
        self,
        api_key: str,
        session: Optional[requests.Session] = None,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
        timeout: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._api_key = api_key
        self._session = session or requests.Session()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.timeout = timeout
        self._sleep = sleep

    def _backoff_delay(self, attempt: int, retry_after: Optional[str] = None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), self.backoff_max)
            except ValueError:
                pass

        delay = self.backoff_base * (2**attempt)
        return min(delay, self.backoff_max) * random.uniform(0.5, 1.0)

    def _get(self, url: str, params: dict) -> dict:
        params = {**params, "key": self._api_key}
        endpoint = url.rsplit("/", 1)[-1]

        for attempt in range(self.max_retries + 1):
            is_last_attempt = attempt == self.max_retries

            try:
                response = self._session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                detail = _redact(str(exc), self._api_key)
                if is_last_attempt:
                    raise YouTubeAPIError(None, "networkError", detail) from None
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "%s: network error (%s), retry %d/%d in %.1fs",
                    endpoint, type(exc).__name__, attempt + 1, self.max_retries, delay,
                )
                self._sleep(delay)
                continue

            if response.status_code == 200:
                return response.json()

            reason, message = _parse_error(response)
            retryable = (
                response.status_code in RETRYABLE_STATUS_CODES
                or reason in RETRYABLE_REASONS
            )

            if not retryable or is_last_attempt:
                raise YouTubeAPIError(
                    response.status_code, reason, _redact(message, self._api_key)
                )

            delay = self._backoff_delay(attempt, response.headers.get("Retry-After"))
            logger.warning(
                "%s: HTTP %s (%s), retry %d/%d in %.1fs",
                endpoint, response.status_code, reason,
                attempt + 1, self.max_retries, delay,
            )
            self._sleep(delay)

        raise AssertionError("unreachable")  # pragma: no cover

    def get_video(self, video_id: str) -> dict:
        return self._get(
            VIDEOS_URL, {"part": "snippet,liveStreamingDetails", "id": video_id}
        )

    def list_chat_messages(
        self,
        live_chat_id: str,
        page_token: Optional[str] = None,
        max_results: int = 2000,
    ) -> dict:
        params = {
            "liveChatId": live_chat_id,
            "part": "snippet,authorDetails",
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token

        return self._get(LIVE_CHAT_URL, params)


def extract_live_chat_id(video_response: dict) -> str:
    items = video_response.get("items") or []

    if not items:
        raise LiveChatUnavailableError("Video not found (empty 'items').")

    details = items[0].get("liveStreamingDetails") or {}
    live_chat_id = details.get("activeLiveChatId")

    if not live_chat_id:
        status = items[0].get("snippet", {}).get("liveBroadcastContent")
        raise LiveChatUnavailableError(
            f"Video has no active live chat (liveBroadcastContent={status!r})."
        )

    return live_chat_id


# Backwards-compatible helpers from the original module.
def get_video_metadata(url, params):
    """Calls the YouTube Video API and returns the HTTP response."""
    return requests.get(url, params=params, timeout=15)


def get_live_chat_messages(url, params):
    """Calls the YouTube Live Chat API and returns the HTTP response."""
    return requests.get(url, params=params, timeout=15)
