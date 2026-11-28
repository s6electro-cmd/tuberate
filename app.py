import os
import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from googleapiclient.errors import HttpError
from youtube_api import fetch_youtube_ranking

st.set_page_config(
    page_title="TubeRate - 推しチャンネル発掘ランキング",
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
        .oshi-box {
            background-color: #fff8eb;
            border-left: 4px solid #ff9800;
            padding: 10px 14px;
            border-radius: 6px;
            margin: 8px 0;
            font-size: 0.95rem;
        }
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

st.title("🌱 TubeRate 〜これから伸びる推しチャンネル発掘〜")
st.markdown("登録者がまだ少ないチャンネルの中から、**高評価率・コメントの多さ・登録者比の再生倍率**に注目して推しチャンネルを探せます。")
st.info("💡 左側の「検索画面」（スマホは左中央の赤いボタン）から登録者数上限や期間を選んで発掘できます！")

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
        "過去90日（直近7日除外・王道企画）": (2160, 1
    
