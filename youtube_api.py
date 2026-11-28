import re
import math
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


def build_oshi_comment(
    sub_count: int,
    view_count: int,
    view_to_sub_ratio: float,
    like_rate: float,
    comment_rate: float,
) -> str:
    points = []

    if sub_count > 0 and view_to_sub_ratio >= 10.0:
        points.append(f"登録者{sub_count:,}人に対して再生数{view_to_sub_ratio:.1f}倍の伸びしろ")
    elif sub_count > 0 and view_to_sub_ratio >= 3.0:
        points.append(f"登録者数の{view_to_sub_ratio:.1f}倍規模で再生を獲得")

    if like_rate >= 5.0:
        points.append(f"高評価率{like_rate:.2f}%と視聴者満足度が非常に高い")
    elif like_rate >= 3.5:
        points.append(f"高評価率{like_rate:.2f}%で安定した高評価")

    if comment_rate >= 0.5:
        points.append(f"コメント率{comment_rate:.2f}%で熱量の高い交流が発生")
    elif comment_rate >= 0.2:
        points.append("コメント反応がありファンがつき始めている")

    if not points:
        points.append("小規模ながら一定の再生数と反応を確保している注目候補")

    return "💡 " + "／".join(points) + "。"


def calc_oshi_score(
    view_to_sub_ratio: float,
    like_rate: float,
    comment_rate: float,
    view_count: int,
) -> float:
    # 登録者比の再生倍率・高評価率・コメント率・再生規模をバランス良くスコア化
    ratio_part = min(view_to_sub_ratio, 100.0) * 1.4
    like_part = min(like_rate, 20.0) * 3.0
    comment_part = min(comment_rate * 10.0, 30.0)
    view_part = math.log10(max(view_count, 1)) * 4.0
    return round(ratio_part + like_part + comment_part + view_part, 2)


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
    max_subscribers: int | None = None,
    cache_version: str = "v3",
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

    raw_candidates = []
    channel_ids = []
    seen_channels = set()

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
        comment_rate = (comment_count / view_count * 100) if view_count > 0 else 0.0

        thumbnails = snippet.get("thumbnails", {})
        thumb_url = (
            thumbnails.get("high", {}).get("url")
            or thumbnails.get("medium", {}).get("url")
            or thumbnails.get("default", {}).get("url", "")
        )

        published_at_raw = snippet.get("publishedAt", "")
        published_date = published_at_raw[:10] if published_at_raw else ""

        channel_id = snippet.get("channelId", "")
        if channel_id and channel_id not in seen_channels:
            seen_channels.add(channel_id)
            channel_ids.append(channel_id)

        raw_candidates.append({
            "video_id": item["id"],
            "channel_id": channel_id,
            "title": title,
            "channel_title": snippet.get("channelTitle", ""),
            "published_date": published_date,
            "view_count": view_count,
            "like_count": like_count,
            "comment_count": comment_count,
            "like_rate": round(like_rate, 2),
            "comment_rate": round(comment_rate, 2),
            "duration_sec": duration_sec,
            "thumbnail": thumb_url,
        })

    if not raw_candidates:
        return []

    channel_info_map: dict[str, dict] = {}
    if channel_ids:
        channels_response = youtube.channels().list(
            part="snippet,statistics",
            id=",".join(channel_ids[:50]),
        ).execute()

        for ch in channels_response.get("items", []):
            ch_id = ch.get("id", "")
            ch_snippet = ch.get("snippet", {})
            ch_stats = ch.get("statistics", {})
            sub_hidden = bool(ch_stats.get("hiddenSubscriberCount", False))
            sub_count = int(ch_stats.get("subscriberCount", 0)) if not sub_hidden else -1
            ch_desc = (ch_snippet.get("description", "") or "").strip()
            channel_info_map[ch_id] = {
                "subscriber_count": sub_count,
                "subscriber_hidden": sub_hidden or (sub_count < 0),
                "channel_description": ch_desc,
                "channel_video_count": int(ch_stats.get("videoCount", 0)),
            }

    slash = chr(47)
    base_url = f"https:{chr(47)*2}www.youtube.com{chr(47)}watch?v="
    ch_base_url = f"https:{chr(47)*2}www.youtube.com{chr(47)}channel{chr(47)}"

    results = []
    st.caption(
        f"検証: 検索ID={len(video_ids)}件 / 詳細={len(videos_response.get('items', []))}件 / "
        f"動画フィルタ通過={len(raw_candidates)}件 / チャンネル情報={len(channel_info_map)}件"
    )
    for cand in raw_candidates:
        ch_info = channel_info_map.get(cand["channel_id"], {})
        sub_count = ch_info.get("subscriber_count", -1)
        sub_hidden = ch_info.get("subscriber_hidden", True)
        
