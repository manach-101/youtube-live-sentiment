from dotenv import load_dotenv
import os

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if YOUTUBE_API_KEY is None:
    raise ValueError("YOUTUBE_API_KEY is missing. Check your .env file.")