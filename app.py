import streamlit as st
import datetime
import re
import pandas as pd
from googleapiclient.discovery import build

st.set_page_config(page_title="TubeRate - YouTube高評価率ランキング", layout="wide")
st.title("📊 TubeRate 〜YouTube高評価率ランキング〜")
st.markdown("再生回数だけでなく、視聴者の満足度（高評価率）が高い動画を期間指定で発掘できます。")

default_key = st.secrets.get("YOUTUBE_API_KEY", "") if "YOUTUBE_API_KEY" in st.secrets else ""

with st.sidebar:
    st.header("🔍 検索条件")
    api_key = st.text_input(
        "YouTube APIキー",
        value=default_key,
        type="password",
        help="Google Cloud Consoleで取得した無料のYouTube Data API v3キーを入力してください"
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

    min_views = st.number_input("最低再生回数（足切り）", min_value=0, value=3000, step=1000)
    exclude_shorts = st.checkbox("ショート動画（3分未満）を除外する", value=True)
    max_results = st.slider("取得する候補数（最大50件）", min_value=10, max_value=50, value=50)

    search_button = st.button("🚀 ランキングを作成する", type="primary", use_container_width=True)

def parse_duration(duration_str):
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return 0
    return int(match.group(1) or 0) * 3600 + int(match.group(2) or 0) * 60 + int(match.group(3) or 0)

if search_button:
    if not api_key:
        st.error("⚠️ 左側のメニューに YouTube APIキー を入力してください。")
    else:
        with st.spinner("YouTubeからデータを取得・分析中..."):
            try:
                youtube = build("youtube", "v3", developerKey=api_key)
                now = datetime.datetime.now(datetime.timezone.utc)
                published_after = (now - datetime.timedelta(hours=hours_start)).isoformat()
                published_before = (now - datetime.timedelta(hours=hours_end)).isoformat()

                search_params = {
                    "part": "id",
                    "type": "video",
                    "q": search_keyword,
                    "publishedAfter": published_after,
                    "publishedBefore": published_before,
                    "maxResults": max_results,
                    "order": "viewCount",
                    "regionCode": "JP",
                    "relevanceLanguage": "ja"
                }
                if category_id != "0":
                    search_params["videoCategoryId"] = category_id

                search_response = youtube.search().list(**search_params).execute()
                video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]

                if not video_ids:
                    st.warning("条件に一致する動画が見つかりませんでした。キーワードや期間を変更してください。")
                else:
                    videos_response = youtube.videos().list(
                        part="snippet,statistics,contentDetails",
                        id=",".join(video_ids)
                    ).execute()

                    ranking_data = []
                    for item in videos_response.get("items", []):
                        snippet = item["snippet"]
                        stats = item["statistics"]
                        content_details = item["contentDetails"]

                        title = snippet["title"]
                        view_count = int(stats.get("viewCount", 0))
                        like_count = int(stats.get("likeCount", 0))
                        duration_sec = parse_duration(content_details.get("duration", ""))

                        if view_count < min_views:
                            continue
                        if exclude_shorts and (duration_sec < 180 or "#shorts" in title.lower() or "#ショート" in title):
                            continue

                        like_rate = (like_count / view_count) * 100 if view_count > 0 else 0

                        ranking_data.append({
                            "サムネイル": snippet["thumbnails"]["medium"]["url"],
                            "タイトル": title,
                            "チャンネル名": snippet["channelTitle"],
                            "高評価率(%)": round(like_rate, 2),
                            "再生回数": view_count,
                            "高評価数": like_count,
                            "動画時間(分)": round(duration_sec / 60, 1),
                            "公開日": snippet["publishedAt"][:10],
                            "動画リンク": f"https://youtube.com{item['id']}"
                        })

                    if not ranking_data:
                        st.warning("フィルター条件（最低再生回数やショート除外）を通過した動画がありませんでした。")
                    else:
                        df = pd.DataFrame(ranking_data)
                        df = df.sort_values(by="高評価率(%)", ascending=False).reset_index(drop=True)
                        df.index = df.index + 1

                        st.success(f"🎉 分析完了！全 {len(df)} 件のランキングを作成しました。")

                        st.dataframe(
                            df,
                            column_config={
                                "サムネイル": st.column_config.ImageColumn("サムネ", width="small"),
                                "動画リンク": st.column_config.LinkColumn("YouTubeで見る", display_text="▶ 再生"),
                                "高評価率(%)": st.column_config.NumberColumn("高評価率", format="%.2f %%"),
                                "再生回数": st.column_config.NumberColumn("再生回数", format="%d 回"),
                                "高評価数": st.column_config.NumberColumn("高評価数", format="%d"),
                            },
                            use_container_width=True,
                            height=600
                        )

                        csv = df.to_csv(index=True).encode('utf-8-sig')
                        st.download_button(
                            label="📥 このランキングをCSVでダウンロード",
                            data=csv,
                            file_name="youtube_likerate_ranking.csv",
                            mime="text/csv",
                        )
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
