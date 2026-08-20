from ingestion.youtube import get_video_metadata, get_live_chat_messages
from config.settings import YOUTUBE_API_KEY
from storage.raw_writer import save_raw_json



video_id = "cb12KmMMDJA"

# ---------- VIDEO METADATA ------------

url = "https://www.googleapis.com/youtube/v3/videos"

params = {
    "part": "snippet,liveStreamingDetails",
    "id": video_id,
    "key": YOUTUBE_API_KEY
}

response = get_video_metadata(url, params)

print("Video status:", response.status_code)

data = response.json()

video = data["items"][0]
snippet = video["snippet"]
live_details = video["liveStreamingDetails"]

live_chat_id = live_details["activeLiveChatId"]

print("Live chat ID:", live_chat_id)

print("Title:", snippet["title"])
print("Channel:", snippet["channelTitle"])
print("Live status:", snippet["liveBroadcastContent"])

live_status = snippet["liveBroadcastContent"]

if live_status == "live":
    print("Stream is live. Pipeline can continue.")
else:
    print("Warning: stream is not live.")

print("Published:", snippet["publishedAt"])

# ---------- LIVE CHAT DATA ------------

chat_url = "https://www.googleapis.com/youtube/v3/liveChat/messages"

chat_params = {
    "key": YOUTUBE_API_KEY,
    "liveChatId": live_chat_id,
    "part": "snippet,authorDetails",
    "maxResults": 5
}

chat_response = get_live_chat_messages(chat_url, chat_params)

print("Chat status:", chat_response.status_code)

chat_data = chat_response.json()

saved_path = save_raw_json(
    data=chat_data,
    source="youtube_comments"
)

print(f"Raw comments saved to {saved_path}")


messages = chat_data["items"]

for message in messages:
    author = message["authorDetails"]["displayName"]
    published_at = message["snippet"]["publishedAt"]
    text = message["snippet"]["displayMessage"]

    print(author, "|", published_at, "|", text)