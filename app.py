# -*- coding: utf-8 -*-
"""
產業回落/創高比較工具 (Sector Breadth Monitor)
仿照 Turning Point Market Research 的圖表邏輯：
上圖 = 產業ETF指數走勢
下圖 = 該產業成分股中「從252日高點回落超過X%（熊市）」與「接近/創252日新高」的股票比例

給 Albert 的說明（寫在註解裡，方便你對照學習）：
- 這個 App 完全不需要你懂程式，只要照著下面的部署步驟做就好
- 核心邏輯只有三步：抓股價 -> 算每檔股票離一年內高點多遠 -> 統計比例畫圖
"""

import os
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

# ---------- 基本設定 ----------
st.set_page_config(page_title="產業回落/創高比較工具", layout="wide")

# ---------- 中文字型設定（跟你金開心Pro同一套邏輯） ----------
# Streamlit Cloud / Render 上的 Linux 環境預設沒有中文字型，
# 需要透過 packages.txt 安裝 fonts-noto-cjk 這個系統套件，圖表中文才不會變成方框。
_CJK_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
]
for _font_path in _CJK_FONT_CANDIDATES:
    if os.path.exists(_font_path):
        matplotlib.font_manager.fontManager.addfont(_font_path)
        _font_name = matplotlib.font_manager.FontProperties(fname=_font_path).get_name()
        matplotlib.rcParams["font.family"] = _font_name
        break
else:
    # 本機（例如 Mac）沒有安裝上面路徑的字型時，退而求其次用系統常見中文字型
    matplotlib.rcParams["font.family"] = ["PingFang TC", "Microsoft JhengHei", "Noto Sans CJK TC", "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False

# 11大 GICS 產業 對應的「S&P 500 產業指數」本身（不是ETF代替，跟原始截圖標題一致）
# 這些是 Yahoo Finance 上真實存在的指數代號，例如 ^SP500-45 就是「S&P 500 Information Technology」
SECTOR_ETF = {
    "Information Technology": "^SP500-45",
    "Financials": "^SP500-40",
    "Health Care": "^SP500-35",
    "Consumer Discretionary": "^SP500-25",
    "Consumer Staples": "^SP500-30",
    "Utilities": "^SP500-55",
    "Real Estate": "^SP500-60",
    "Materials": "^SP500-15",
    "Communication Services": "^SP500-50",
    "Energy": "^SP500-10",
    "Industrials": "^SP500-20",
}

SECTOR_CN = {
    "Information Technology": "資訊科技",
    "Financials": "金融",
    "Health Care": "醫療保健",
    "Consumer Discretionary": "非必需消費",
    "Consumer Staples": "必需消費",
    "Utilities": "公用事業",
    "Real Estate": "不動產",
    "Materials": "原物料",
    "Communication Services": "通訊服務",
    "Energy": "能源",
    "Industrials": "工業",
}


# ---------- 讀取成分股清單 ----------
@st.cache_data(ttl=24 * 3600)
def load_constituents():
    """讀取標普500成分股與所屬產業（本地CSV，來源: datasets/s-and-p-500-companies）"""
    df = pd.read_csv("constituents.csv")
    df = df.rename(columns={"Symbol": "Ticker", "GICS Sector": "Sector"})
    # yfinance 對股票代號的格式要求：BRK.B -> BRK-B
    df["Ticker"] = df["Ticker"].str.replace(".", "-", regex=False)
    return df[["Ticker", "Security", "Sector"]]


# ---------- 抓取股價（重頭戲，也是最花時間的部分） ----------
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def download_prices(tickers, period="2y"):
    """
    一次批次下載多檔股票的收盤價。
    yfinance 對多檔股票下載時，回傳的是 MultiIndex 欄位 (欄位名, 股票代號)，
    所以 data['Close'] 會直接得到一個「每一欄是一檔股票」的收盤價表格。
    """
    data = yf.download(
        tickers,
        period=period,
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"]
    else:
        # 只有單一檔股票時，欄位不會是 MultiIndex
        close = data[["Close"]]
        close.columns = tickers
    return close


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def download_index(ticker, period="2y"):
    data = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    return data["Close"]


# ---------- 核心計算：離252日高點回落幾% ----------
def compute_breadth(close_df, lookback=252, bear_threshold=20, near_high_threshold=1):
    """
    close_df: 每一欄是一檔股票的收盤價
    回傳: 每天「熊市股票比例」與「接近新高股票比例」的時間序列
    """
    rolling_high = close_df.rolling(window=lookback, min_periods=int(lookback * 0.6)).max()
    pct_below = (rolling_high - close_df) / rolling_high * 100  # 離高點回落幾%

    valid = pct_below.notna()
    n_valid = valid.sum(axis=1)

    bear_mask = (pct_below >= bear_threshold) & valid
    newhigh_mask = (pct_below <= near_high_threshold) & valid

    bear_pct = bear_mask.sum(axis=1) / n_valid.replace(0, np.nan) * 100
    newhigh_pct = newhigh_mask.sum(axis=1) / n_valid.replace(0, np.nan) * 100

    return pct_below, bear_pct, newhigh_pct


# ---------- 畫圖：仿照 Turning Point Research 的上下兩張圖 ----------
def plot_sector_chart(index_price, bear_pct, newhigh_pct, sector_name_cn, bear_threshold):
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True,
        gridspec_kw={"height_ratios": [2, 1.2]},
    )

    # 上圖：產業ETF指數
    ax1.plot(index_price.index, index_price.values, color="black", linewidth=1)
    ax1.set_title(f"標普500「{sector_name_cn}」成分股回落/創高狀況", fontsize=14, fontweight="bold", loc="left")
    last_val = index_price.iloc[-1]
    ax1.annotate(f"{last_val:,.2f}", xy=(index_price.index[-1], last_val),
                 xytext=(6, 0), textcoords="offset points", fontsize=9, color="black")
    ax1.grid(alpha=0.2)
    ax1.spines[["top", "right"]].set_visible(False)

    # 下圖：熊市比例（藍） vs 接近新高比例（綠）
    ax2.plot(bear_pct.index, bear_pct.values, color="#4A90D9", linewidth=1.2,
              label=f"距高點回落 > {bear_threshold}% 的股票比例")
    ax2.plot(newhigh_pct.index, newhigh_pct.values, color="#2E9E4E", linewidth=1.2,
              label="接近/創252日新高的股票比例")
    ax2.axhline(50, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax2.set_ylim(0, 100)
    ax2.grid(alpha=0.2)
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.legend(loc="upper left", fontsize=8, frameon=False)

    last_bear = bear_pct.dropna().iloc[-1] if bear_pct.dropna().shape[0] else np.nan
    last_new = newhigh_pct.dropna().iloc[-1] if newhigh_pct.dropna().shape[0] else np.nan
    ax2.annotate(f"{last_bear:.1f}", xy=(bear_pct.index[-1], last_bear),
                 xytext=(6, 0), textcoords="offset points", fontsize=9, color="#4A90D9")
    ax2.annotate(f"{last_new:.1f}", xy=(newhigh_pct.index[-1], last_new),
                 xytext=(6, -10), textcoords="offset points", fontsize=9, color="#2E9E4E")

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%y/%m"))
    fig.autofmt_xdate()
    plt.tight_layout()
    return fig


# ---------- 主畫面 ----------
st.title("📊 產業回落 / 創高比較工具")
st.caption("仿照 Turning Point Research 圖表邏輯，統計標普500各產業成分股「離一年高點回落幅度」")

const_df = load_constituents()

with st.sidebar:
    st.header("設定")
    bear_threshold = st.slider("熊市定義：回落超過多少%", 10, 40, 20, step=5)
    near_high_threshold = st.slider("新高定義：距高點在多少%以內算「接近新高」", 0, 10, 1, step=1)
    period = st.selectbox("資料回溯期間", ["1y", "2y", "3y"], index=1)
    st.markdown("---")
    st.caption("首次載入單一產業約需 30 秒 ~ 2 分鐘（視股票檔數與 Yahoo 回應速度而定），資料會快取 6 小時。")

tab1, tab2 = st.tabs(["🔍 11大產業總覽比較", "📈 單一產業深入圖"])

# ---------- Tab 1：11大產業總覽比較（長條圖） ----------
with tab1:
    st.subheader("目前各產業的「熊市股票比例」與「接近新高股票比例」")
    if st.button("開始計算全部11大產業（第一次會比較久）", type="primary"):
        overview_rows = []
        progress = st.progress(0.0, text="準備中...")
        sectors = list(SECTOR_ETF.keys())
        for i, sector in enumerate(sectors):
            tickers = const_df[const_df["Sector"] == sector]["Ticker"].tolist()
            progress.progress((i) / len(sectors), text=f"下載中：{SECTOR_CN[sector]} ({len(tickers)}檔)")
            try:
                close = download_prices(tickers, period=period)
                _, bear_pct, newhigh_pct = compute_breadth(
                    close, bear_threshold=bear_threshold, near_high_threshold=near_high_threshold
                )
                overview_rows.append({
                    "產業": SECTOR_CN[sector],
                    "成分股數": len(tickers),
                    "熊市比例(%)": round(bear_pct.dropna().iloc[-1], 1) if bear_pct.dropna().shape[0] else np.nan,
                    "接近新高比例(%)": round(newhigh_pct.dropna().iloc[-1], 1) if newhigh_pct.dropna().shape[0] else np.nan,
                })
            except Exception as e:
                st.warning(f"{SECTOR_CN[sector]} 下載失敗：{e}")
        progress.progress(1.0, text="完成")

        overview_df = pd.DataFrame(overview_rows).sort_values("熊市比例(%)", ascending=False)
        st.session_state["overview_df"] = overview_df

    if "overview_df" in st.session_state:
        overview_df = st.session_state["overview_df"]
        st.dataframe(overview_df, use_container_width=True, hide_index=True)

        fig, ax = plt.subplots(figsize=(10, 5))
        x = np.arange(len(overview_df))
        width = 0.38
        ax.bar(x - width / 2, overview_df["熊市比例(%)"], width, label=f"回落>{bear_threshold}%", color="#4A90D9")
        ax.bar(x + width / 2, overview_df["接近新高比例(%)"], width, label="接近新高", color="#2E9E4E")
        ax.set_xticks(x)
        ax.set_xticklabels(overview_df["產業"], rotation=30, ha="right")
        ax.set_ylabel("成分股比例 (%)")
        ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.2)
        plt.tight_layout()
        st.pyplot(fig)
    else:
        st.info("點上面的按鈕開始計算（會依序下載11個產業、約500檔股票的資料）")

# ---------- Tab 2：單一產業深入圖（類似截圖那種上下兩張圖） ----------
with tab2:
    sector_choice = st.selectbox(
        "選擇要深入看的產業",
        options=list(SECTOR_ETF.keys()),
        format_func=lambda s: SECTOR_CN[s],
    )
    if st.button(f"產生「{SECTOR_CN[sector_choice]}」深入圖"):
        tickers = const_df[const_df["Sector"] == sector_choice]["Ticker"].tolist()
        with st.spinner(f"下載 {SECTOR_CN[sector_choice]} 共 {len(tickers)} 檔股票資料中..."):
            close = download_prices(tickers, period=period)
            index_price = download_index(SECTOR_ETF[sector_choice], period=period)
            pct_below, bear_pct, newhigh_pct = compute_breadth(
                close, bear_threshold=bear_threshold, near_high_threshold=near_high_threshold
            )
        fig = plot_sector_chart(index_price, bear_pct, newhigh_pct, SECTOR_CN[sector_choice], bear_threshold)
        st.pyplot(fig)

        st.markdown("#### 目前離高點最遠的10檔個股（拖累最深）")
        latest_pct = pct_below.iloc[-1].dropna().sort_values(ascending=False).head(10)
        detail = const_df.set_index("Ticker").loc[latest_pct.index, ["Security"]].copy()
        detail["距252日高點回落(%)"] = latest_pct.round(1).values
        st.dataframe(detail, use_container_width=True)
