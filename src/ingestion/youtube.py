import requests


def get_video_metadata(url, params):
    """
    Calls the YouTube Video API and returns the HTTP response.
    """
    return requests.get(url, params=params)