import os
import streamlit as st
import datetime
import re
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ページ設定
st.set_page_config(page_title="TubeRate - YouTube高評価率ランキング", layout="wide")
# 上段のFork・GitHubボタンと、右下のStreamlitバッジを非表示にする（左上のサイドバー開閉ボタンは残す）
# 左上の「＞」ボタンは残し、上段のFork/GitHubと右下のバッジだけをピンポイントで消す
# スマホ操作性アップ：検索ボタンを目立たせるCSS ＆ 左スワイプで閉じる機能
import streamlit.components.v1 as components

# スマホ操作性アップ：検索ボタンを目立たせるCSS ＆ 検索実行時に自動でメニューを閉じる機能
import streamlit.components.v1 as components

st.markdown("""
    <style>
        /* 上段右側のツールバーと右下のバッジを非表示 */
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
        /* ★ 1. 左上の「＞」ボタンを確実に赤いピル型ボタンにして「検索条件」の文字を添える */
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
                /* ★ サイドバー（検索条件画面）の余白を詰めてスマホ1画面に収める */
        section[data-testid="stSidebar"] > div {
            padding-top: 1rem !important;
            padding-bottom: 0.5rem !important;
        }
        section[data-testid="stSidebar"] .block-container {
            padding-top: 0.5rem !important;
            padding-bottom: 0.5rem !important;
        }
        /* 各入力項目の縦の隙間をコンパクトにする */
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.45rem !important;
        }
        /* 見出し（🔍 検索条件）の上下の余白を小さくする */
        section[data-testid="stSidebar"] h2 {
            margin-top: 0 !important;
            margin-bottom: 0.2rem !important;
            padding-top: 0 !important;
            font-size: 1.2rem !important;
        }

    </style>
""", unsafe_allow_html=True)

# ★ 2. スワイプで閉じる機能 ＋ 「ランキングを作成する」ボタンを押したら自動でメニューを閉じる機能
components.html("""
    <script>
    const doc = window.parent.document;

    function closeSidebar() {
        const closeBtn = doc.querySelector('[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebar"] button[kind="header"]');
        if (closeBtn) {
            closeBtn.click();
        }
    }

    // 左スワイプで閉じる
    let touchStartX = 0;
    doc.addEventListener('touchstart', function(e) {
        touchStartX = e.changedTouches[0].screenX;
    }, {passive: true});
    doc.addEventListener('touchend', function(e) {
        const touchEndX = e.changedTouches[0].screenX;
        if (touchStartX - touchEndX > 50) {
            closeSidebar();
        }
    }, {passive: true});

    // 「🚀 ランキングを作成する」ボタンが押されたら自動でメニューを閉じる
    doc.addEventListener('click', function(e) {
        const btn = e.target.closest('button');
        if (btn && btn.innerText.includes('ランキングを作成する')) {
            setTimeout(closeSidebar, 200);
        }
    }, true);
    </script>
""", height=0)



st.title("📊 TubeRate 〜YouTube高評価率ランキング〜")
st.markdown("再生回数だけでなく、視聴者の満足度（高評価率）が高い動画を期間指定で発掘できます。")
st.info("💡 左上の「🔍 検索画面」から、あなたの好きなYouTubeのジャンルやお気に入りのチャンネル名を入れて試してみてください！")

# 裏側（Secrets）に保存された運営者のAPIキーを取得
owner_api_key = os.environ.get("YOUTUBE_API_KEY", "")
if not owner_api_key:
    try:
        owner_api_key = st.secrets.get("YOUTUBE_API_KEY", "")
    except Exception:
        owner_api_key = ""

# セッション状態（無料枠が切れたかどうかの記憶）を初期化
if "quota_exceeded" not in st.session_state:
    st.session_state.quota_exceeded = False

# サイドバー（検索条件の入力エリア）
with st.sidebar:
    st.header("🔍 検索画面")

    # 運営者キーがない場合、または無料枠の上限に達した場合のみ入力欄を表示
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
        # 自分のキーを使いたい人向けの折りたたみオプション
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

    min_views = st.number_input("最低再生回数（足切り）", min_value=0, value=3000, step=1000)
    exclude_shorts = st.checkbox("ショート動画（3分未満）を除外する", value=True)
    max_results = st.slider("取得する候補数（最大50件）", min_value=10, max_value=50, value=50)

    search_button = st.button("🚀 ランキングを作成する", type="primary", use_container_width=True)

def parse_duration(duration_str):
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return 0
    return int(match.group(1) or 0) * 3600 + int(match.group(2) or 0) * 60 + int(match.group(3) or 0)

# 使用するAPIキーを決定（ユーザー入力があればそちらを優先、なければ運営者キーを使用）
active_api_key = user_api_key if user_api_key else owner_api_key

if search_button:
    if not active_api_key:
        st.error("⚠️ YouTube APIキーを入力してください。")
    else:
        with st.spinner("YouTubeからデータを取得・分析中..."):
            try:
                youtube = build("youtube", "v3", developerKey=active_api_key)
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
                            "動画リンク": f"https://www.youtube.com/watch?v={item['id']}"


                        })

                    if not ranking_data:
                        st.warning("フィルター条件（最低再生回数やショート除外）を通過した動画がありませんでした。")
                    else:
                        df = pd.DataFrame(ranking_data)
                        df = df.sort_values(by="高評価率(%)", ascending=False).reset_index(drop=True)
                        df.index = df.index + 1

                        st.success(f"🎉 分析完了！全 {len(df)} 件のランキングを作成しました。")

                        csv = df.to_csv(index=True).encode('utf-8-sig')
                        st.download_button(
                            label="📥 このランキングをCSVでダウンロード",
                            data=csv,
                            file_name="youtube_likerate_ranking.csv",
                            mime="text/csv",
                        )

                        st.divider()

                        for rank, row in df.iterrows():
                            col1, col2 = st.columns([1, 2.5])
                            with col1:
                                st.image(row["サムネイル"], use_container_width=True)
                                st.link_button("▶ YouTubeで見る", row["動画リンク"], use_container_width=True)
                            with col2:
                                st.markdown(f"### {rank}位：[{row['タイトル']}]({row['動画リンク']})")
                                st.markdown(f"**📺 {row['チャンネル名']}** ｜ 公開日: {row['公開日']} ｜ 動画時間: {row['動画時間(分)']}分")
                                st.markdown(f"🔥 **高評価率：{row['高評価率(%)']}%** （再生回数：{row['再生回数']:,}回 ／ 高評価数：{row['高評価数']:,}）")
                            st.divider()

                                    except HttpError as e:
                if e.resp.status == 403 and "quotaExceeded" in str(e):
                    st.session_state.quota_exceeded = True
                    st.rerun()
                else:
                    st.error(f"YouTube APIエラーが発生しました: {e}")
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

