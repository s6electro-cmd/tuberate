import os
import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from googleapiclient.errors import HttpError
from youtube_api import fetch_youtube_ranking

st.set_page_config(
    page_title="TubeRate - YouTube高評価率ランキング",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
        /* 不要なツールバーとバッジを非表示 */
        [data-testid="stToolbarActions"], [data-testid="stMainMenu"],
        .stAppDeployButton, footer, [data-testid="stStatusWidget"],
        [class^="viewerBadge_"], [class*="viewerBadge"], #MainMenu {
            display: none !important;
            visibility: hidden !important;
        }
        header[data-testid="stHeader"] {
            background: transparent !important;
        }

        /* サイドバーを開くボタンのデザイン */
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stExpandSidebarButton"],
        header[data-testid="stHeader"] button {
            visibility: visible !important;
            display: inline-flex !important;
            align-items: center !important;
            background-color: #ff4b4b !important;
            color: white !important;
            border-radius: 24px !important;
            padding: 8px 16px 8px 12px !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3) !important;
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
            content: "🔍 検索画面を開く";
            font-size: 14px !important;
            font-weight: bold !important;
            color: white !important;
            margin-left: 6px !important;
            white-space: nowrap !important;
        }

        /* スマホ画面（768px以下）：ボタンを左端・縦の真ん中に配置 */
        @media (max-width: 768px) {
            [data-testid="stSidebarCollapsedControl"],
            [data-testid="stExpandSidebarButton"],
            header[data-testid="stHeader"] button {
                position: fixed !important;
                top: 50% !important;
                left: 8px !important;
                transform: translateY(-50%) !important;
                margin: 0 !important;
            }
        }

        /* PC画面（769px以上） */
        @media (min-width: 769px) {
            [data-testid="stSidebarCollapsedControl"],
            [data-testid="stExpandSidebarButton"],
            header[data-testid="stHeader"] button {
                margin-top: 8px !important;
                margin-left: 8px !important;
            }
        }

        .block-container { padding-top: 2.5rem; padding-bottom: 5rem; }
    </style>
""", unsafe_allow_html=True)

# 左スワイプでのみサイドバーを閉じる（クリック横取りは廃止してリンク遷移を保護）
components.html("""
    <script>
    const doc = window.parent.document;
    function closeSidebar() {
        const closeBtn = doc.querySelector('[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebar"] button[kind="header"]');
        if (closeBtn) { closeBtn.click(); }
    }
    let touchStartX = 0;
    doc.addEventListener('touchstart', function(e) { touchStartX = e.changedTouches.screenX; }, {passive: true});
    doc.addEventListener('touchend', function(e) {
        if (window.parent.innerWidth <= 768 && (touchStartX - e.changedTouches.screenX > 50)) {
            closeSidebar();
        }
    }, {passive: true});
    </script>
""", height=0)

st.title("📊 TubeRate 〜YouTube高評価率ランキング〜")
st.markdown("再生回数だけでなく、視聴者の満足度（高評価率）が高い動画を期間指定で発掘できます。")
st.info("💡 左側の「検索画面」（スマホは左中央の赤いボタン）から条件を選んでランキングを作成できます！")

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

    search_keyword = st.text_input("検索キーワード", value="キャンプ道具 -切り抜き")
    categories = {
        "すべて（全ジャンル）": "0", "映画とアニメ": "1", "自動車と乗り物": "2",
        "音楽": "10", "ペットと動物": "15", "スポーツ": "17", "旅行とイベント": "19",
        "ゲーム": "20", "ブログ（日常・Vlog）": "22", "コメディ": "23",
        "エンターテイメント": "24", "ニュースと政治": "25", "ハウツーとスタイル": "26",
        "教育": "27", "科学と技術": "28",
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

    search_button = st.button("🚀 ランキングを作成する", type="primary", use_container_width=True)

    with st.expander("⚙️ 詳細フィルター（再生数・ショート除外）", expanded=False):
        min_views = st.number_input("最低再生回数（足切り）", min_value=0, value=3000, step=1000)
        exclude_shorts = st.checkbox("ショート動画（3分未満）を除外する", value=True)
        max_results = st.slider("取得する候補数（最大50件）", min_value=10, max_value=50, value=50)

    user_api_key = ""
    if st.session_state.quota_exceeded:
        st.info("ご利用にはAPIのキーの入力が必要です")
        user_api_key = st.text_input("YouTube APIキー", type="password", placeholder="AIzaSy...")
        with st.expander("📖 APIキーの無料取得方法（約3分）"):
            st.caption("1. Google Cloud Console にログイン")
            st.caption("2. 新しいプロジェクトを作成し YouTube Data API v3 を有効化")
            st.caption("3. 「認証情報」＞「＋認証情報を作成」＞「APIキー」で発行された文字列を貼り付け")


if search_button:
    active_api_key = user_api_key.strip() if user_api_key.strip() else owner_api_key
    if not active_api_key:
        st.error("❌ APIキーが設定されていません。")
        
    else:
        with st.spinner("YouTubeからデータを取得し、高評価率を計算中..."):
            try:
                ranking_data = fetch_youtube_ranking(
                    api_key=active_api_key, keyword=search_keyword, category_id=category_id,
                    hours_start=hours_start, hours_end=hours_end, min_views=min_views,
                    exclude_shorts=exclude_shorts, max_results=max_results,
                )
                st.session_state["ranking_data"] = ranking_data
            except HttpError as e:
                if e.resp.status == 403 and "quotaExceeded" in str(e):
                    if not user_api_key.strip():
                        st.session_state.quota_exceeded = True
                        st.rerun()
                    else:
                        st.error("❌ 入力されたAPIキーの1日の利用上限（Quota）を超過しています。")
                else:
                    st.error(f"❌ YouTube APIエラーが発生しました: {e}")
            except Exception as e:
                st.error(f"❌ 予期せぬエラーが発生しました: {e}")

if "ranking_data" in st.session_state:
    results = st.session_state["ranking_data"]
    if not results:
        st.warning("条件に一致する動画が見つかりませんでした。最低再生回数を下げるか、対象期間を広げてお試しください。")
    else:
        st.subheader(f"🏆 高評価率ランキング（該当 {len(results)} 件）")
    
   
        df = pd.DataFrame(results)[["title", "channel_title", "published_date", "like_rate", "view_count", "like_count", "comment_count", "url"]]
        df.columns = ["タイトル", "チャンネル名", "公開日", "高評価率(%)", "再生回数", "高評価数", "コメント数", "URL"]
        st.download_button(
            label="📥 ランキング結果をCSVでダウンロード",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"tuberate_{datetime.date.today()}.csv",
            mime="text/csv",
        )
        for idx, video in enumerate(results, start=1):
            with st.container(border=True):
                player_key = f"player_open_{video['video_id']}"
                if player_key not in st.session_state:
                    st.session_state[player_key] = False
                yt_url = "https:" + chr(47) + chr(47) + "www.youtube.com" + chr(47) + "watch?v=" + video["video_id"]

                col1, col2 = st.columns([1, 2.4])
                with col1:
                    if st.session_state[player_key]:
                        st.video(yt_url)
                        if st.button("❌ サムネに戻す", key=f"close_{video['video_id']}", use_container_width=True):
                            st.session_state[player_key] = False
                            st.rerun()
                    else:
                        if video["thumbnail"]:
                            st.image(video["thumbnail"], use_container_width=True)
                        if st.button("🎬 ここで再生", key=f"open_{video['video_id']}", use_container_width=True):
                            st.session_state[player_key] = True
                            st.rerun()
                            
                   
                with col2:
                    st.markdown(f"**:red[第 {idx} 位]**")
                    st.markdown(f"### [{video['title']}]({yt_url})")
                    st.caption(f"📺 {video['channel_title']} ｜ 📅 {video['published_date']}")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("高評価率", f"{video['like_rate']:.2f}%")
                    m2.metric("再生回数", f"{video['view_count']:,}")
                    m3.metric("高評価数", f"{video['like_count']:,}")
                    m4.metric("コメント数", f"{video['comment_count']:,}")
                    st.link_button("▶️ YouTubeで開く", yt_url, type="primary")
 　　　　　　　　 　  

