import re
import datetime
import streamlit as st
from googleapiclient.discovery import build


def parse_duration_seconds(duration_str: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_youtube_ranking(
    api_key: str,
    keyword: str,
    category_id: str,
    hours_start: int,
    hours_end: int,
    min_views: int,
    exclude_shorts: bool,
    max_results: int,
    cache_version: str = "v2",
) -> list[dict]:
    youtube = build("youtube", "v3", developerKey=api_key)
    now = datetime.datetime.now(datetime.timezone.utc)
    published_after = (now - datetime.timedelta(hours=hours_start)).isoformat()
    published_before = (
        (now - datetime.timedelta(hours=hours_end)).isoformat()
        if hours_end > 0
        else None
    )

    search_params = {
        "part": "id",
        "q": keyword,
        "type": "video",
        "order": "viewCount",
        "maxResults": max_results,
        "publishedAfter": published_after,
        "regionCode": "JP",
        "relevanceLanguage": "ja",
    }
    if published_before:
        search_params["publishedBefore"] = published_before
    if category_id != "0":
        search_params["videoCategoryId"] = category_id

    search_response = youtube.search().list(**search_params).execute()
    video_ids = [
        item["id"]["videoId"]
        for item in search_response.get("items", [])
        if "videoId" in item.get("id", {})
    ]

    if not video_ids:
        return []

    videos_response = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(video_ids),
    ).execute()

    slash = chr(47)
    base_url = f"https:{chr(47)*2}www.youtube.com{chr(47)}watch?v="

    results = []
    for item in videos_response.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        title = snippet.get("title", "")
        description = snippet.get("description", "")
        duration_sec = parse_duration_seconds(content.get("duration", ""))

        if exclude_shorts:
            is_short_tag = "#shorts" in title.lower() or "#shorts" in description.lower()
            if duration_sec < 180 or is_short_tag:
                continue

        view_count = int(stats.get("viewCount", 0))
        if view_count < min_views:
            continue

        if "likeCount" not in stats:
            continue

        like_count = int(stats.get("likeCount", 0))
        comment_count = int(stats.get("commentCount", 0))
        like_rate = (like_count / view_count * 100) if view_count > 0 else 0.0

        thumbnails = snippet.get("thumbnails", {})
        thumb_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url", "")
        )

        published_at_raw = snippet.get("publishedAt", "")
        published_date = published_at_raw[:10] if published_at_raw else ""

        vid = item["id"]

        results.append({
            "video_id": vid,
            "title": title,
            "channel_title": snippet.get("channelTitle", ""),
            "published_date": published_date,
            "view_count": view_count,
            "like_count": like_count,
            "comment_count": comment_count,
            "like_rate": round(like_rate, 2),
            "duration_sec": duration_sec,
            "thumbnail": thumb_url,
            "url": base_url + vid,
        })

    st.caption(
        f"取得内訳: 検索ID={len(video_ids)}件 / 詳細={len(videos_response.get('items', []))}件 / 絞り込み後={len(results)}件"
    )
    results.sort(key=lambda x: x["like_rate"], reverse=True)
    return results
