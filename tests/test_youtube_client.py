"""YouTubeClient retry/backoff and error handling, using a fake HTTP session."""

import pytest
import requests

from src.ingestion.youtube import (
    LIVE_CHAT_URL,
    LiveChatUnavailableError,
    YouTubeAPIError,
    YouTubeClient,
    extract_live_chat_id,
)

API_KEY = "test-key-not-real"


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = str(self._body)

    def json(self):
        return self._body


def error_response(status, reason, message="error", headers=None):
    body = {"error": {"code": status, "message": message, "errors": [{"reason": reason}]}}
    return FakeResponse(status, body, headers)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_client(responses, max_retries=3):
    session = FakeSession(responses)
    sleeps = []
    client = YouTubeClient(API_KEY, session=session, max_retries=max_retries, sleep=sleeps.append)
    return client, session, sleeps


def test_success_sends_expected_params():
    client, session, sleeps = make_client([FakeResponse(200, {"items": []})])

    assert client.list_chat_messages("chat-1", page_token="tok", max_results=500) == {"items": []}

    call = session.calls[0]
    assert call["url"] == LIVE_CHAT_URL
    assert call["params"] == {
        "liveChatId": "chat-1",
        "part": "snippet,authorDetails",
        "maxResults": 500,
        "pageToken": "tok",
        "key": API_KEY,
    }
    assert call["timeout"] > 0
    assert sleeps == []


def test_retries_transient_errors_then_succeeds():
    client, session, sleeps = make_client(
        [
            FakeResponse(503, {}),
            requests.ConnectionError("boom"),
            error_response(403, "rateLimitExceeded"),
            FakeResponse(200, {"items": [1]}),
        ]
    )

    assert client.get_video("vid") == {"items": [1]}
    assert len(session.calls) == 4
    assert len(sleeps) == 3


def test_honours_retry_after_header():
    client, _, sleeps = make_client(
        [FakeResponse(429, {}, headers={"Retry-After": "7"}), FakeResponse(200, {})]
    )

    client.get_video("vid")

    assert sleeps == [7.0]


def test_backoff_grows_exponentially_and_is_capped():
    client = YouTubeClient(API_KEY, backoff_base=1.0, backoff_max=10.0)

    for attempt, upper in [(0, 1), (1, 2), (2, 4), (3, 8), (10, 10)]:
        delay = client._backoff_delay(attempt)
        assert upper / 2 <= delay <= upper


@pytest.mark.parametrize("status, reason", [(403, "quotaExceeded"), (400, "keyInvalid"), (403, "liveChatEnded")])
def test_permanent_errors_are_not_retried(status, reason):
    client, session, sleeps = make_client([error_response(status, reason)])

    with pytest.raises(YouTubeAPIError) as exc_info:
        client.list_chat_messages("chat")

    assert exc_info.value.reason == reason
    assert len(session.calls) == 1
    assert sleeps == []


def test_gives_up_after_max_retries():
    client, session, sleeps = make_client([FakeResponse(500, {})] * 3, max_retries=2)

    with pytest.raises(YouTubeAPIError) as exc_info:
        client.get_video("vid")

    assert exc_info.value.status_code == 500
    assert len(session.calls) == 3
    assert len(sleeps) == 2


def test_api_key_is_redacted_from_errors():
    leaked = f"https://www.googleapis.com/youtube/v3/videos?key={API_KEY}"
    client, _, _ = make_client([requests.ConnectionError(leaked)], max_retries=0)

    with pytest.raises(YouTubeAPIError) as exc_info:
        client.get_video("vid")

    assert API_KEY not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_chat_ended_property():
    assert YouTubeAPIError(403, "liveChatEnded", "").chat_ended
    assert not YouTubeAPIError(403, "quotaExceeded", "").chat_ended


def test_extract_live_chat_id():
    video = {"items": [{"snippet": {}, "liveStreamingDetails": {"activeLiveChatId": "chat-123"}}]}
    assert extract_live_chat_id(video) == "chat-123"


@pytest.mark.parametrize(
    "video",
    [
        {"items": []},
        {},
        {"items": [{"snippet": {"liveBroadcastContent": "none"}}]},
        {"items": [{"snippet": {}, "liveStreamingDetails": {"actualEndTime": "x"}}]},
    ],
)
def test_extract_live_chat_id_raises_when_unavailable(video):
    with pytest.raises(LiveChatUnavailableError):
        extract_live_chat_id(video)
