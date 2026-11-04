"""實測 Nasdaq 篩選器能不能當美股盤中資料來源：每分鐘抓一次全市場，連續 30 分鐘。
看三件事：會不會被擋（HTTP 狀態、回應時間）、資料多久更新一次（幾檔大型股的價格與成交量有沒有變）、
以及成交量看起來是不是盤中累積的。結果寫在 data/probe_nasdaq_live.log。"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_turnover import NASDAQ_URL, BROWSER_UA, DATA  # noqa: E402

WATCH = ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "META", "AMD", "PLTR"]
MINUTES = int(sys.argv[1]) if len(sys.argv) > 1 else 30
TPE = timezone(timedelta(hours=8))
ET = timezone(timedelta(hours=-5))
LOG = []


def log(msg):
    line = "%s（美東 %s）  %s" % (datetime.now(TPE).strftime("%H:%M:%S"), datetime.now(ET).strftime("%H:%M"), msg)
    print(line, flush=True)
    LOG.append(line)


def num(s):
    try:
        return float(str(s).replace("$", "").replace(",", "").replace("%", ""))
    except ValueError:
        return None


def fetch():
    req = urllib.request.Request(NASDAQ_URL, headers={"User-Agent": BROWSER_UA, "Accept": "application/json, text/plain, */*",
                                                       "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=40) as r:
        body = r.read()
        return r.status, body, time.time() - t0


prev, changes, ok, fail = {}, {c: 0 for c in WATCH}, 0, 0
for i in range(MINUTES):
    start = time.time()
    try:
        status, body, secs = fetch()
        rows = (json.loads(body).get("data") or {}).get("rows") or []
        by = {r.get("symbol"): r for r in rows}
        total = sum((num(r.get("lastsale")) or 0) * (num(r.get("volume")) or 0) for r in rows)
        snap = {c: (num(by[c].get("lastsale")), num(by[c].get("volume"))) for c in WATCH if c in by}
        moved = [c for c in snap if prev.get(c) and prev[c] != snap[c]]
        for c in moved:
            changes[c] += 1
        ok += 1
        log("HTTP %d  %.1f 秒  %d KB  %d 檔  估計全市場成交值 %.0f 億美元  有變動：%s  例：AAPL %s／量 %s" % (
            status, secs, len(body) // 1024, len(rows), total / 1e8, ",".join(moved) or "無",
            snap.get("AAPL", (None,))[0], snap.get("AAPL", (None, None))[1]))
        prev = snap
    except Exception as e:  # noqa: BLE001
        fail += 1
        log("失敗：%s" % str(e)[:200])
    time.sleep(max(0, 60 - (time.time() - start)))

log("結果：成功 %d 次、失敗 %d 次" % (ok, fail))
log("每檔在 %d 次之中數字有變動的次數：%s" % (MINUTES - 1, "、".join("%s %d" % kv for kv in changes.items())))
(DATA / "probe_nasdaq_live.log").write_text("\n".join(LOG) + "\n", encoding="utf-8")
