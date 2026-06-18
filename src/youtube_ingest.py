from dotenv import load_dotenv
import os
import requests

load_dotenv()

api_key = os.getenv("YOUTUBE_API_KEY")

video_id = "cb12KmMMDJA"

url = "https://www.googleapis.com/youtube/v3/videos"

params = {
    "part": "snippet",
    "id": video_id,
    "key": api_key
}

response = requests.get(url, params=params)

print(response.status_code)

data = response.json()

video = data["items"][0]
snippet = video["snippet"]

print("Title:", snippet["title"])
print("Channel:", snippet["channelTitle"])
print("Live status:", snippet["liveBroadcastContent"])