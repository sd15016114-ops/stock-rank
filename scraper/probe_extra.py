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
    ("上市當沖", "https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?date=%(ymd)s&selectType=All&response=json"),
    ("上櫃當沖a", "https://www.tpex.org.tw/web/stock/trading/intraday_trading/intraday_trading_list_result.php?l=zh-tw&o=json&d=%(roc)s"),
    ("上櫃當沖b", "https://www.tpex.org.tw/www/zh-tw/intraday/stat?date=%(slash)s&response=json"),
    ("上市借券", "https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date=%(ymd)s&response=json"),
    ("上櫃借券a", "https://www.tpex.org.tw/web/stock/margin_trading/margin_sbl/margin_sbl_result.php?l=zh-tw&o=json&d=%(roc)s"),
    ("上櫃借券b", "https://www.tpex.org.tw/www/zh-tw/margin/sbl?date=%(slash)s&response=json"),
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
