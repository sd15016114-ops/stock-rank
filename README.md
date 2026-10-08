# 股市動能排行：台股、美股盤後成交值排行

做法比照利率站：GitHub Actions 每個交易日收盤後自動抓資料，存成 `data/tw.json`、`data/us.json`，
`index.html` 讀檔顯示。

| 市場 | 來源 | 成交值 | 更新時間（台灣） |
|---|---|---|---|
| 台股上市 | 臺灣證券交易所「每日收盤行情」 | 官方成交金額 | 週一到週五 18:30、21:30 |
| 台股上櫃 | 證券櫃檯買賣中心開放資料 | 官方成交金額 | 同上 |
| 美股 | Polygon（日期、價量；需要金鑰 `POLYGON_API_KEY`）＋ Nasdaq 股票清單（公司名稱、產業） | 成交均價 × 成交量 | 週二到週六 13:15 |

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

預設保留最近 60 個交易日，要改天數請調整 `scraper/fetch_turnover.py` 的 `KEEP_DAYS`。

## 全市場存檔、均值與放大倍數（台股）

- 每天另存一份全市場精簡檔 `data/full/tw/日期.json`（約 2,300 檔，只有代號、收盤、成交值），保留 65 個交易日。
- 排行每一列的 `avg` 是「當天以前 60 個交易日」的平均成交值，`ratio` 是當日成交值 ÷ 均值（放大倍數）。
  資料不到 5 天的股票（例如剛上市）不算。`avg_days` 是實際用了幾天。
- 這些都由排程算好寫進 `tw.json`，網頁不用多讀檔案。

### 回補歷史

平常用的兩個來源只有最新一天。要補過去的日期，到 Actions 手動執行，「要做什麼」選 `backfill`，
天數填 `65`（已經有的日期會跳過；填 `65 force` 則全部重抓）。本機執行是：

    python scraper/fetch_turnover.py backfill 65

回補用的是可以指定日期的來源：證交所 `MI_INDEX`、櫃買中心 `stk_wn1430_result.php`。
每天之間會停幾秒，65 天大約 10 分鐘。週末不連線，來源回空的日子（國定假日、颱風假）自動跳過。

## 產業別與熱力圖（台股）

- 產業別來自證交所、櫃買中心的公司基本資料，一週更新一次，存在 `data/industry_tw.json`。
  來源給的是代碼，用程式裡的 `INDUSTRY_NAMES` 轉成名稱；ETF 沒有產業別，獨立成一類。
- `tw.json` 的 `industries` 是全市場各產業的成交值加總、漲跌幅（以成交值加權平均），以及成交值最大的 25 檔。
- 網頁的熱力圖用 squarify 排版，寫在 `index.html` 裡，不靠外部套件。

## 休市日

- 台股：日期用資料本身帶的，不需要假日表。休市日抓到的還是前一個交易日，內容相同就不會產生新的一天。
- 美股：來源沒有日期，交易日用美東時間推算。抓到的價量如果和前一個交易日完全相同，就判定休市、不存檔。

## 實測資料來源

來源改版時，到 Actions 手動執行並把「要做什麼」選成 `probe`，結果會寫在 `data/probe.log`。

## 保護機制

- 抓不到資料或檔數太少：不寫入，沿用前一次資料並標記 `stale`，網頁會顯示提示。
- 全市場成交值與前一次相差超過五倍：視為可疑，同樣沿用舊資料。
- 櫃買中心抓不到，或日期還沒跟上證交所：先只出上市排行並標記 `partial`，21:30 那次會再補。
- 兩個來源日期對不上、而手上已有同一天的完整排行：保留現有資料不覆蓋，等下一次更新。

## 已知限制

- 美股用 Polygon 免費方案：當天的資料要等美東時間過了午夜才開放，所以美股排行與當日走勢在台灣時間下午一點多才更新；每分鐘只能呼叫 5 次，抓 100 檔當日走勢約需 21 分鐘。
- 美股只收 Nasdaq 股票清單裡的個股，不含 ETF。Nasdaq 清單抓不到時會沿用上次存的 `data/us_names.json`。
- 之前曾用 Nasdaq 網頁資料加上時間推算日期，結果日期會早標一天；現在日期一律以 Polygon 為準。要重建美股歷史可在 Actions 手動執行，task 選 `backfill-us`。
