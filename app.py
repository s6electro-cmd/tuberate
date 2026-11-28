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
        "過去90日（直近7日除外・王道企画）": (2160, 168),
        "過去1年（直近7日除外・名作発掘）": (8760, 168),
    }
    selected_period = st.selectbox("対象期間", list(period_options.keys()), index=2)
    hours_start, hours_end = period_options[selected_period]

    subscriber_options = {
        "指定なし": None,
        "100人以下（超穴場・初期）": 100,
        "300人以下（発掘初期）": 300,
        "500人以下（注目株）": 500,
        "1,000人以下（伸び盛り）": 1000,
        "1,500人以下（ブレイク前夜）": 1500,
        "2,000人以下（準推し候補）": 2000,
    }
    selected_sub_label = st.selectbox(
        "チャンネル登録者数（上限）",
        list(subscriber_options.keys()),
        index=4,
    )
    max_subscribers = subscriber_options[selected_sub_label]

    search_button = st.button("🚀 推しチャンネルを探す", type="primary", use_container_width=True)

    with st.expander("⚙️ 詳細フィルター（再生数・ショート除外）", expanded=False):
        min_views = st.number_input("最低再生回数（足切り）", min_value=0, value=1000, step=500)
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
        with st.spinner("YouTubeから動画とチャンネル情報を取得し、推し度を計算中..."):
            try:
                ranking_data = fetch_youtube_ranking(
                    api_key=active_api_key,
                    keyword=search_keyword,
                    category_id=category_id,
                    hours_start=hours_start,
                    hours_end=hours_end,
                    min_views=min_views,
                    exclude_shorts=exclude_shorts,
                    max_results=max_results,
                    max_subscribers=max_subscribers,
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
        st.warning("条件に一致するチャンネルが見つかりませんでした。登録者数の上限を広げるか、最低再生回数を下げてお試しください。")
    else:
        sort_options = {
            "総合推し度スコア順": ("oshi_score", True),
            "登録者比の再生倍率順": ("view_to_sub_ratio", True),
            "高評価率順": ("like_rate", True),
            "コメント数順": ("comment_count", True),
            "コメント率順": ("comment_rate", True),
            "再生回数順": ("view_count", True),
        }
        col_title, col_sort = st.columns([2.2, 1.2])
        with col_title:
            st.subheader(f"🏆 推しチャンネル発掘ランキング（該当 {len(results)} 件）")
        with col_sort:
            selected_sort = st.selectbox("並び替え", list(sort_options.keys()), index=0)

        sort_key, sort_rev = sort_options[selected_sort]
        sorted_results = sorted(results, key=lambda x: x.get(sort_key, 0), reverse=sort_rev)

        df = pd.DataFrame(sorted_results)[[
            "title", "channel_title", "subscriber_count", "view_to_sub_ratio",
            "like_rate", "view_count", "like_count", "comment_count", "oshi_score", "url"
        ]]
        df.columns = [
            "タイトル", "チャンネル名", "登録者数", "再生倍率(対登録者)",
            "高評価率(%)", "再生回数", "高評価数", "コメント数", "推し度スコア", "URL"
        ]
        st.download_button(
            label="📥 ランキング結果をCSVでダウンロード",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"oshi_channels_{datetime.date.today()}.csv",
            mime="text/csv",
        )

        for idx, video in enumerate(sorted_results, start=1):
            with st.container(border=True):
                vid = video["video_id"]
                yt_url = video["url"]
                ch_url = video.get("channel_url", "")
                embed_url = "https:" + chr(47) + chr(47) + "www.youtube.com" + chr(47) + "embed/" + vid
                thumb_url = video["thumbnail"] or ""

                sub_count = video.get("subscriber_count", -1)
                sub_text = f"{sub_count:,}人" if sub_count >= 0 else "非公開"
                ratio_text = f"{video.get('view_to_sub_ratio', 0.0):.1f}倍" if sub_count > 0 else "-"

                col1, col2 = st.columns([1, 2.4])
                with col1:
                    components.html(
                        f"""
                        <style>
                          .hover-box-{vid} {{
                            position: relative;
                            width: 100%;
                            aspect-ratio: 16 / 9;
                            overflow: hidden;
                            border-radius: 8px;
                            background: #000;
                          }}
                          .hover-box-{vid} img,
                          .hover-box-{vid} iframe {{
                            position: absolute;
                            inset: 0;
                            width: 100%;
                            height: 100%;
                            border: 0;
                          }}
                          .hover-box-{vid} img {{
                            object-fit: cover;
                            z-index: 2;
                            transition: opacity 0.15s ease;
                          }}
                          .hover-box-{vid} iframe {{
                            z-index: 1;
                          }}
                          .hover-box-{vid}:hover img {{
                            opacity: 0;
                            pointer-events: none;
                          }}
                        </style>
                        <div class="hover-box-{vid}">
                          <img src="{thumb_url}" alt="thumbnail">
                          <iframe src="{embed_url}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
                        </div>
                        """,
                        height=190,
                    )
                with col2:
                    st.markdown(f"**:red[第 {idx} 位]** ｜ 推し度スコア: **{video.get('oshi_score', 0.0):.1f}**")
                    st.markdown(f"### [{video['title']}]({yt_url})")

                    if ch_url:
                        ch_link_md = f"[{video['channel_title']}]({ch_url})"
                    else:
                        ch_link_md = video["channel_title"]
                    st.caption(
                        f"📺 {ch_link_md} ｜ 👥 登録者: **{sub_text}** ｜ 📈 再生倍率: **{ratio_text}** ｜ 📅 {video['published_date']}"
                    )

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("高評価率", f"{video['like_rate']:.2f}%")
                    m2.metric("再生回数", f"{video['view_count']:,}")
                    m3.metric("高評価数", f"{video['like_count']:,}")
                    m4.metric("コメント数", f"{video['comment_count']:,}")

                    st.markdown(
                        f'<div class="oshi-box">{video.get("oshi_comment", "")}</div>',
                        unsafe_allow_html=True,
                    )

                    ch_desc = (video.get("channel_description") or "").strip()
                    with st.expander("📝 チャンネル概要を見る", expanded=False):
                        if ch_desc:
                            st.write(ch_desc)
                        else:
                            st.caption("チャンネル概要文は登録されていません。")
                        if video.get("channel_video_count", 0) > 0:
                            st.caption(f"公開動画数: {video['channel_video_count']:,}本")
