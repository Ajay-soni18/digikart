"""YouTube Data API helpers for the admin "Import from playlist" feature.

Pure functions + a small fetch wrapper, kept out of the view so they're easy to
unit-test (the tests patch `_get`). Nothing here touches the database — the view
turns the returned dicts into Lecture rows.

Requires a YouTube Data API v3 key (settings.YOUTUBE_API_KEY). When the key is
missing or the playlist can't be read, a YouTubeError with a friendly message is
raised so the view can surface it to the admin.
"""

import re

import requests

API_BASE = "https://www.googleapis.com/youtube/v3"
PAGE_SIZE = 50           # YouTube's max per page
MAX_PAGES = 40           # safety cap → up to 2000 videos per import
REQUEST_TIMEOUT = 20     # seconds per HTTP call


class YouTubeError(Exception):
    """Raised with a user-safe message when the playlist can't be imported."""


def extract_playlist_id(url):
    """Pull the playlist id out of common YouTube URL shapes, or accept a bare id.

    Handles:
      - https://www.youtube.com/playlist?list=PLxxxx
      - https://www.youtube.com/watch?v=VID&list=PLxxxx
      - https://youtu.be/VID?list=PLxxxx
      - PLxxxx  (a bare playlist id)
    Returns "" when nothing playlist-like is found.
    """
    if not url:
        return ""
    url = url.strip()
    m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    # A bare id pasted on its own (no scheme, no query string).
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", url):
        return url
    return ""


def iso8601_duration_to_clock(value):
    """Convert a YouTube ISO-8601 duration (e.g. "PT1H2M30S") to the "H:MM:SS" /
    "M:SS" clock format the Lecture model stores. Returns "" if unparseable."""
    if not value:
        return ""
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value)
    if not m:
        return ""
    hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _get(path, params):
    """Single GET against the YouTube Data API, returning parsed JSON.

    Maps transport/HTTP/quota failures onto a YouTubeError carrying a message
    that's safe to show an admin.
    """
    try:
        resp = requests.get(f"{API_BASE}/{path}", params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        raise YouTubeError("Couldn't reach YouTube. Please try again in a moment.")

    if resp.status_code == 200:
        return resp.json()

    # Try to extract YouTube's own reason for a clearer message.
    reason = ""
    try:
        errors = resp.json().get("error", {}).get("errors", [])
        if errors:
            reason = errors[0].get("reason", "")
    except ValueError:
        pass

    if resp.status_code == 404 or reason in {"playlistNotFound", "notFound"}:
        raise YouTubeError("Playlist not found. Check the link or that it isn't private.")
    if resp.status_code == 403:
        if reason in {"quotaExceeded", "dailyLimitExceeded"}:
            raise YouTubeError("YouTube API quota exceeded. Please try again later.")
        raise YouTubeError("The YouTube API key is invalid or not authorized.")
    if resp.status_code == 400 and reason == "keyInvalid":
        raise YouTubeError("The YouTube API key is invalid.")
    raise YouTubeError("YouTube returned an unexpected error. Please try again.")


def fetch_playlist_videos(playlist_id, api_key):
    """Fetch every video in a playlist (following pagination), returning a list of
    dicts in playlist order:

        {video_id, title, description, duration, unavailable}

    `unavailable` is True for private/deleted videos that have no playable id;
    the view records those as failures rather than creating broken lectures.
    Raises YouTubeError on a missing key or an unreadable playlist.
    """
    if not api_key:
        raise YouTubeError("The YouTube API key is not configured on the server.")

    items = []
    page_token = None
    for _ in range(MAX_PAGES):
        params = {
            "part": "snippet,contentDetails,status",
            "maxResults": PAGE_SIZE,
            "playlistId": playlist_id,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        data = _get("playlistItems", params)
        items.extend(data.get("items", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    # Pull durations in batches of 50 (the videos endpoint accepts up to 50 ids).
    video_ids = [
        it.get("contentDetails", {}).get("videoId")
        for it in items
        if it.get("contentDetails", {}).get("videoId")
    ]
    durations = _fetch_durations(video_ids, api_key)

    videos = []
    for it in items:
        snippet = it.get("snippet", {})
        vid = it.get("contentDetails", {}).get("videoId") or ""
        title = snippet.get("title", "")
        # YouTube exposes private/deleted entries with these placeholder titles
        # and no usable description; flag them so the view can skip cleanly.
        unavailable = (not vid) or title in {"Private video", "Deleted video", ""}
        videos.append({
            "video_id": vid,
            "title": title or "Untitled",
            "description": snippet.get("description", ""),
            "duration": durations.get(vid, ""),
            "unavailable": unavailable,
        })
    return videos


def _fetch_durations(video_ids, api_key):
    """Map {video_id: "H:MM:SS"} for the given ids (batched 50 at a time)."""
    out = {}
    for i in range(0, len(video_ids), PAGE_SIZE):
        batch = video_ids[i:i + PAGE_SIZE]
        if not batch:
            continue
        data = _get("videos", {
            "part": "contentDetails",
            "id": ",".join(batch),
            "key": api_key,
        })
        for v in data.get("items", []):
            iso = v.get("contentDetails", {}).get("duration", "")
            out[v.get("id", "")] = iso8601_duration_to_clock(iso)
    return out
