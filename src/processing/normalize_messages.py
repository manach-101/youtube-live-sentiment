def normalize_message(item: dict) -> dict:
    snippet = item.get("snippet", {})
    author_details = item.get("authorDetails", {})

    return {
        "message_id": item.get("id"),
        "author_channel_id": author_details.get("channelId"),
        "author_name": author_details.get("displayName"),
        "message": snippet.get("displayMessage"),
        "published_at": snippet.get("publishedAt"),
        "is_moderator": author_details.get("isChatModerator", False),
        "is_owner": author_details.get("isChatOwner", False),
        "is_verified": author_details.get("isVerified", False),
        "live_chat_id": snippet.get("liveChatId"),
    }

def normalize_messages(data: dict) -> list[dict]:
    items = data.get("items", [])

    return [normalize_message(item) for item in items]
