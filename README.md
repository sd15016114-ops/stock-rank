# 股市動能排行：台股、美股盤後成交值排行

做法比照利率站：GitHub Actions 每個交易日收盤後自動抓資料，存成 `data/tw.json`、`data/us.json`，
`index.html` 讀檔顯示。

| 市場 | 來源 | 成交值 | 更新時間（台灣） |
|---|---|---|---|
| 台股上市 | 臺灣證券交易所「每日收盤行情」 | 官方成交金額 | 週一到週五 17:30、21:30 |
| 台股上櫃 | 證券櫃檯買賣中心開放資料 | 官方成交金額 | 同上 |
| 美股 | Nasdaq 股票篩選器（免金鑰） | 收盤價 × 成交量（估算） | 週二到週六 06:30 |

台股收個股與 ETF（不含權證、特別股）；美股收 NYSE、Nasdaq、NYSE American 的股票，不含 ETF。

## 放上 GitHub

1. 建立一個新的程式庫（要公開，網頁才讀得到資料），把整個資料夾上傳，`.github` 資料夾也要。
3. 到 Settings → Pages，Source 選 `Deploy from a branch`，分支選 `main`、資料夾選 `/ (root)`。
4. 到 Actions 分頁，選「盤後更新成交值排行」，按 Run workflow 手動跑一次。
5. 跑完後打開 `https://你的帳號.github.io/程式庫名稱/` 就能看到排行。

之後會照排程自動執行，資料有變動才會產生新的提交。任何一個市場抓取失敗，該次執行會顯示紅色，GitHub 會寄信通知。

## 在自己的電腦測試

    pip install -r scraper/requirements.txt
    python tests/test_parse.py            # 離線測試解析邏輯
    python scraper/fetch_turnover.py      # 實際連線抓台股與美股
    python scraper/fetch_turnover.py tw   # 只抓台股
    python -m http.server                 # 再開 http://localhost:8000 看網頁

## 資料格式

    {
      "date": "2026-10-07",              // 交易日
      "updated": "2026-10-07T17:31:02+08:00",
      "status": "ok",                    // ok 正常、partial 只有上市、stale 沿用舊資料、failed 從未成功
      "total_value": 650000000000,       // 全市場成交值（台股為元，美股為美元）
      "rows": [{
        "code": "2330", "name": "台積電", "market": "上市", "etf": false,
        "close": 1500.0, "change": 15.0, "pct": 1.01,
        "volume": 30000000,              // 成交股數
        "value": 45000000000             // 成交值
      }]
    }

台股每個市場保留成交值前 100 檔個股與前 50 檔 ETF，美股保留前 100 檔。

## 歷史排行與名次比較

每次抓取成功，當天的排行會另存一份到 `data/history/tw/日期.json`、`data/history/us/日期.json`，
日期清單在 `data/tw_dates.json`、`data/us_dates.json`。網頁上可以切換交易日，名次下方會顯示
與前一個交易日相比的升降（▲ 上升、▼ 下降、新進榜）。

預設保留最近 30 個交易日，要改天數請調整 `scraper/fetch_turnover.py` 的 `KEEP_DAYS`。

## 保護機制

- 抓不到資料或檔數太少：不寫入，沿用前一次資料並標記 `stale`，網頁會顯示提示。
- 全市場成交值與前一次相差超過五倍：視為可疑，同樣沿用舊資料。
- 櫃買中心抓不到，或日期還沒跟上證交所：先只出上市排行並標記 `partial`，21:30 那次會再補。

## 已知限制

- 美股成交值是估算值；交易日用美東時間推算，遇到美股休市日會顯示成休市當天的日期，內容則是前一個交易日。
- Nasdaq 偶爾不回應 GitHub 機房的連線。如果常常失敗，可以改用 Polygon 等需要金鑰的來源。
