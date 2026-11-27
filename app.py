import os
import re
import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

st.set_page_config(page_title="TubeRate - YouTube高評価率ランキング", layout="wide")

st.markdown("""
    <style>
        [data-testid="stToolbarActions"],
        [data-testid="stMainMenu"],
        .stAppDeployButton,
        footer,
        [data-testid="stStatusWidget"],
        [class^="viewerBadge_"],
        [class*="viewerBadge"],
        #MainMenu {
            display: none !important;
            visibility: hidden !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stExpandSidebarButton"],
        header[data-testid="stHeader"] button {
            visibility: visible !important;
            display: inline-flex !important;
            align-items: center !important;
            background-color: #ff4b4b !important;
            color: white !important;
            border-radius: 24px !important;
            padding: 6px 16px 6px 10px !important;
            margin-top: 8px !important;
            margin-left: 8px !important;
            box-shadow: 0 3px 8px rgba(0,0,0,0.25) !important;
            border: none !important;
            width: auto !important;
            height: auto !important;
        }
        [data-testid="stSidebarCollapsedControl"] svg,
        [data-testid="stExpandSidebarButton"] svg,
        header[data-testid="stHeader"] button svg {
            fill: white !important;
            color: white !important;
        }
        [data-testid="stSidebarCollapsedControl"]::after,
        [data-testid="stExpandSidebarButton"]::after,
        header[data-testid="stHeader"] button::after {
            content: "🔍 検索画面";
            font-size: 14px !important;
            font-weight: bold !important;
            color: white !important;
            margin-left: 6px !important;
            white-space: nowrap !important;
        }
        .block-container {
            padding-top: 3.5rem;
            padding-bottom: 5rem;
        }
        section[data-testid="stSidebar"] > div {
            padding-top: 1rem !important;
            padding-bottom: 0.5rem !important;
        }
        section[data-testid="stSidebar"] .block-container {
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
        }
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.45rem !important;
        }
        section[data-testid="stSidebar"] h2 {
            margin-top: 0 !important;
            margin-bottom: 0.2rem !important;
            padding-top: 0 !important;
            font-size: 1.2rem !important;
        }
    </style>
""", unsafe_allow_html=True)

components.html("""
    <script>
    const doc = window.parent.document;
    function closeSidebar() {
        const closeBtn = doc.querySelector('[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebar"] button[kind="header"]');
        if (closeBtn) { closeBtn.click(); }
    }
    let touchStartX = 0;
    doc.addEventListener('touchstart', function(e) {
        touchStartX = e.changedTouches.screenX;
    }, {passive: true});
    doc.addEventListener('touchend', function(e) {
        const touchEndX = e.changedTouches.screenX;
        if (touchStartX - touchEndX > 50) { closeSidebar(); }
    }, {passive: true});
    doc.addEventListener('click', function(e) {
        const btn = e.target.closest('button');
        if (btn && btn.innerText.includes('ランキングを作成する')) {
            setTimeout(closeSidebar, 200);
        }
    }, true);
    </script>
""", height=0)


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

        results.append({
            "video_id": item["id"],
            "title": title,
            "channel_title": snippet.get("channelTitle", ""),
            "published_date": published_date,
            "view_count": view_count,
            "like_count": like_count,
            "comment_count": comment_count,
            "like_rate": round(like_rate, 2),
            "duration_sec": duration_sec,
            "thumbnail": thumb_url,
            "url": f"https://youtube.com{item['id']}",
        })

    results.sort(key=lambda x: x["like_rate"], reverse=True)
    return results


st.title("📊 TubeRate 〜YouTube高評価率ランキング〜")
st.markdown("再生回数だけでなく、視聴者の満足度（高評価率）が高い動画を期間指定で発掘できます。")
st.info("💡 左上の「🔍 検索画面」から、あなたの好きなYouTubeのジャンルやお気に入りのチャンネル名を入れて試してみてください！")

owner_api_key = os.environ.get("YOUTUBE_API_KEY", "")
if not owner_api_key:
    try:
        owner_api_key = st.secrets.get("YOUTUBE_API_KEY", "")
    except Exception:
        owner_api_key = ""

if "quota_exceeded" not in st.session_state:
    st.session_state.quota_exceeded = False

with st.sidebar:
    st.header("🔍 検索画面")

    user_api_key = ""
    if not owner_api_key or st.session_state.quota_exceeded:
        st.warning("⚠️ 本日の無料お試し枠が上限に達しました。続けて利用するにはご自身のYouTube APIキーを入力してください。")
        user_api_key = st.text_input(
            "ご自身のYouTube APIキー",
            type="password",
            placeholder="AIzaSy..."
        )
        with st.expander("📖 APIキーの無料取得方法（約3分）"):
            st.markdown("""
            1. [Google Cloud Console](https://google.com) にGoogleアカウントでログイン
            2. 新しいプロジェクトを作成し、「ライブラリ」から **YouTube Data API v3** を有効化
            3. 「認証情報」＞「＋認証情報を作成」＞「APIキー」で発行された文字列をコピーして上に貼り付け
            ※完全無料・クレジットカード登録不要です。
            """)
    else:
        st.caption("✅ 無料お試しモード稼働中（キー入力不要）")
        with st.expander("🔑 自分のAPIキーを使う（上級者向け）"):
            user_api_key = st.text_input(
                "YouTube APIキー（任意）",
                type="password",
                help="空欄のままでもそのまま検索できます"
            )

    search_keyword = st.text_input("検索キーワード", value="キャンプ道具 -切り抜き")

    categories = {
        "すべて（全ジャンル）": "0",
        "映画とアニメ": "1",
        "自動車と乗り物": "2",
        "音楽": "10",
        "ペットと動物": "15",
        "スポーツ": "17",
        "旅行とイベント": "19",
        "ゲーム": "20",
        "ブログ（日常・Vlog）": "22",
        "コメディ": "23",
        "エンターテイメント": "24",
        "ニュースと政治": "25",
        "ハウツーとスタイル": "26",
        "教育": "27",
        "科学と技術": "28",
    }
    selected_cat_name = st.selectbox("ジャンル（カテゴリー）", list(categories.keys()))
    category_id = categories[selected_cat_name]

    period_options = {
        "過去6時間以内（超リアルタイム・初動）": (6, 0),
        "過去24時間以内（今日の急上昇）": (24, 0),
        "過去30日（直近7日除外・トレンド分析）": (720, 168),
        "過去90日（直近7日除外・王道企画）": (2160, 168),
        "過去1年（直近7日除外・名作発掘）": (8760, 168),
    }
    selected_period = st.selectbox("対象期間", list(period_options.keys()), index=2)
    hours_start, hours_end = period_options[selected_period]

