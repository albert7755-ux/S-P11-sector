# S-P11-sector
11sector
[README.md](https://github.com/user-attachments/files/29833573/README.md)
# 產業回落 / 創高比較工具

仿照 Turning Point Research 的圖表邏輯，統計標普500「11大 GICS 產業」成分股中：
- 有多少比例的股票「從一年高點回落超過X%（進入熊市）」
- 有多少比例的股票「接近或創一年新高」

上圖的產業走勢，用的是 **S&P 官方產業指數本身**（如 `^SP500-45` = S&P 500 Information Technology），不是用 ETF 代替，跟原始截圖標題完全對應。

## 檔案說明
- `app.py`：主程式，全部邏輯都在這一個檔案裡
- `constituents.csv`：標普500成分股清單與所屬產業（資料來源：GitHub `datasets/s-and-p-500-companies`），偶爾成分股會變動，之後可以重新下載這個檔案更新
- `requirements.txt`：Python 套件清單
- `packages.txt`：Streamlit Cloud 需要的系統套件（中文字型），沒有這個檔案圖表中文會變成方框

## 部署到 Streamlit Cloud（跟你其他23個App一樣的流程）

1. 到你的 GitHub（`albert7755-ux`）建一個新的 repository，例如叫 `sector-breadth`
2. 把這4個檔案（`app.py`、`constituents.csv`、`requirements.txt`、`packages.txt`）都上傳上去
3. 到 https://share.streamlit.io 用同一個 GitHub 帳號登入
4. 選「New app」→ 選這個 repo → Main file path 填 `app.py` → Deploy
5. 第一次啟動會需要幾分鐘安裝套件，之後就可以直接用網址開啟

## 使用上的小提醒

- **第一次載入會比較慢**：因為要跟 Yahoo Finance 一次抓好幾十~上百檔股票的兩年份股價，尤其「11大產業總覽」那個按鈕，會依序抓完全部503檔股票，大概需要1~3分鐘，之後6小時內會用快取（不用重新抓）
- 左側可以調整「熊市定義」（預設回落超過20%，跟你截圖那張圖一樣）跟「新高定義」的門檻
- 如果 Yahoo Finance 那邊突然連不上（他們偶爾會擋太密集的請求），單一產業的下載會失敗，這時候等幾分鐘再試通常就會好

## 之後可以擴充的方向（先幫你記下來）

- 把某個產業的走勢圖存成PDF或圖片，方便你直接貼進客戶簡報
- 把「11大產業總覽」的結果串進龍蝦Bot的每日報告，做成「/breadth」指令
- 加入台股（用不同的成分股清單 + 台股ETF）做類似比較
