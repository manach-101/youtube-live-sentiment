from dotenv import load_dotenv
import os
import requests
import json

load_dotenv()

api_key = os.getenv("YOUTUBE_API_KEY")

video_id = "cb12KmMMDJA"

# ---------- VIDEO METADATA ------------

url = "https://www.googleapis.com/youtube/v3/videos"

params = {
    "part": "snippet,liveStreamingDetails",
    "id": video_id,
    "key": api_key
}

response = requests.get(url, params=params)

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
    "key": api_key,
    "liveChatId": live_chat_id,
    "part": "snippet,authorDetails",
    "maxResults": 5
}

chat_response = requests.get(chat_url, params=chat_params)

print("Chat status:", chat_response.status_code)

chat_data = chat_response.json()

with open("raw/comments.json", "w", encoding="utf-8") as file:
    json.dump(chat_data, file, ensure_ascii=False, indent=4)

print("Raw comments saved to raw/comments.json")

messages = chat_data["items"]

for message in messages:
    author = message["authorDetails"]["displayName"]
    published_at = message["snippet"]["publishedAt"]
    text = message["snippet"]["displayMessage"]

    print(author, "|", published_at, "|", text)