from src.processing.normalize_messages import normalize_message


def test_normalize_message():
    raw_message = {
        "id": "msg123",
        "snippet": {
            "displayMessage": "Hello world",
            "publishedAt": "2026-09-01T12:00:00Z",
        },
        "authorDetails": {
            "channelId": "channel123",
            "displayName": "Test User",
            "isChatModerator": False,
            "isChatOwner": False,
            "isVerified": True,
        },
    }

    result = normalize_message(raw_message)

    assert result["message_id"] == "msg123"
    assert result["author_channel_id"] == "channel123"
    assert result["author_name"] == "Test User"
    assert result["message"] == "Hello world"
    assert result["published_at"] == "2026-09-01T12:00:00Z"
    assert result["is_moderator"] is False
    assert result["is_owner"] is False
    assert result["is_verified"] is True