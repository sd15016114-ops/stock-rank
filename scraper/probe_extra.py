"""試抓當沖、借券賣出的資料來源，印出欄位和前幾列（只用來確認格式）"""
import json
import sys
import time
sys.path.insert(0, "scraper")
from fetch_turnover import get_text, BROWSER_UA   # noqa: E402

DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-11-11"
y, m, d = DATE.split("-")
K = {"ymd": y + m + d, "roc": "%d/%s/%s" % (int(y) - 1911, m, d), "slash": "%s/%s/%s" % (y, m, d)}
URLS = [
    ("櫃當沖1", "https://www.tpex.org.tw/web/stock/trading/intraday_stat/intraday_trading_stat_result.php?l=zh-tw&o=json&d=%(roc)s"),
    ("櫃當沖2", "https://www.tpex.org.tw/www/zh-tw/intraday/stat?type=Daily&date=%(slash)s&response=json"),
    ("櫃當沖3", "https://www.tpex.org.tw/www/zh-tw/intraday/stat?date=%(slash)s&type=EW&response=json"),
    ("櫃當沖4", "https://www.tpex.org.tw/www/zh-tw/intraday/statistics?date=%(slash)s&response=json"),
    ("櫃當沖5", "https://www.tpex.org.tw/web/stock/trading/intraday_trading/intraday_trading_stat_result.php?l=zh-tw&o=json&d=%(roc)s"),
    ("櫃當沖6", "https://www.tpex.org.tw/www/zh-tw/intraday/trading?date=%(slash)s&response=json"),
    ("櫃當沖7", "https://www.tpex.org.tw/openapi/v1/tpex_intraday_trading_statistics"),
    ("櫃當沖8", "https://www.tpex.org.tw/openapi/v1/tpex_intraday_trading"),
]
for name, url in URLS:
    u = url % K
    try:
        t = get_text(u, ua=BROWSER_UA, tries=1)
        try:
            j = json.loads(t)
        except Exception:      # noqa: BLE001
            print("==", name, "不是 JSON：", t[:300].replace("\n", " "))
            continue
        if isinstance(j, list):
            print("==", name, "清單", len(j), "前 2：", j[:2])
            continue
        tables = j.get("tables") or ([j] if j.get("fields") or j.get("data") else [])
        print("==", name, "鍵：", list(j.keys())[:15], "stat:", j.get("stat"), "表數：", len(tables))
        for k, tb in enumerate(tables):
            print("  表", k, tb.get("title"), "欄位：", tb.get("fields"))
            data = tb.get("data") or []
            print("    筆數", len(data), "前 2：", data[:2])
        if not tables:
            for k in ("aaData", "reportDate", "iTotalRecords"):
                if k in j:
                    print("  ", k, str(j[k])[:400])
    except Exception as e:     # noqa: BLE001
        print("==", name, "失敗：", e)
    time.sleep(3)
