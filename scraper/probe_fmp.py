"""實測 FMP（Financial Modeling Prep）能不能當美股盤中資料來源。
用法：python scraper/probe_fmp.py 分鐘數
  分鐘數 0：只試一次各個介面，看免費方案能不能用、回傳什麼欄位（休市時也能測）
  分鐘數 N：每分鐘抓一次整個 NASDAQ 和 NYSE，連續 N 分鐘，看數字多久更新一次
金鑰從環境變數 FMP_API_KEY 讀（放在 GitHub Secrets），結果寫在 data/probe_fmp.log。免費方案一天 250 次，30 分鐘大約用 60 次。"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

KEY = os.environ.get("FMP_API_KEY", "").strip().strip("\"'")   # 去掉不小心貼到的空白、換行或引號
BASE = "https://financialmodelingprep.com"
TPE, ET = timezone(timedelta(hours=8)), timezone(timedelta(hours=-5))
WATCH = ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "META", "AMD", "PLTR"]
LOG = []


def log(msg):
    line = "%s（美東 %s）  %s" % (datetime.now(TPE).strftime("%H:%M:%S"), datetime.now(ET).strftime("%H:%M"), msg)
    print(line, flush=True)
    LOG.append(line)


def get(path):
    url = BASE + path + ("&" if "?" in path else "?") + "apikey=" + KEY
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "stock-rank/1.0"}), timeout=60) as r:
            body = r.read()
            return r.status, body, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300], time.time() - t0


def rows_of(body):
    try:
        j = json.loads(body)
    except ValueError:
        return None
    return j if isinstance(j, list) else None


def probe_once():
    for path in ("/stable/batch-exchange-quote?exchange=NASDAQ", "/stable/batch-exchange-quote?exchange=NYSE&short=false",
                 "/stable/quote?symbol=AAPL", "/stable/batch-quote?symbols=AAPL,NVDA,MSFT",
                 "/api/v3/quotes/nasdaq", "/api/v3/quote/AAPL"):
        status, body, secs = get(path)
        rows = rows_of(body)
        if rows:
            log("%-55s HTTP %d  %.1f 秒  %d KB  %d 筆  欄位：%s" % (path, status, secs, len(body) // 1024, len(rows), ",".join(list(rows[0])[:20])))
            a = next((r for r in rows if r.get("symbol") == "AAPL"), rows[0])
            log("    範例：%s" % json.dumps(a, ensure_ascii=False)[:400])
        else:
            log("%-55s HTTP %d  %.1f 秒  回應：%s" % (path, status, secs, body[:200].decode("utf-8", "replace") if isinstance(body, bytes) else body))


def watch(minutes):
    prev, changes, ok, fail = {}, {c: 0 for c in WATCH}, 0, 0
    for _ in range(minutes):
        start = time.time()
        snap, total, n, codes = {}, 0.0, 0, []
        for ex in ("NASDAQ", "NYSE"):
            status, body, secs = get("/stable/batch-exchange-quote?exchange=%s&short=false" % ex)
            rows = rows_of(body)
            codes.append("%s %d" % (ex, status))
            if not rows:
                continue
            n += len(rows)
            for r in rows:
                total += (r.get("price") or 0) * (r.get("volume") or 0)
                if r.get("symbol") in WATCH:
                    snap[r["symbol"]] = (r.get("price"), r.get("volume"), r.get("timestamp"))
        if snap:
            ok += 1
            moved = [c for c in snap if prev.get(c) and prev[c][:2] != snap[c][:2]]
            for c in moved:
                changes[c] += 1
            a = snap.get("AAPL", (None, None, None))
            ts = datetime.fromtimestamp(a[2], ET).strftime("%H:%M:%S") if isinstance(a[2], (int, float)) else a[2]
            log("%s  %d 檔  估計成交值 %.0f 億美元  有變動：%s  AAPL %s／量 %s／報價時間（美東）%s" % (
                "、".join(codes), n, total / 1e8, ",".join(moved) or "無", a[0], a[1], ts))
            prev = snap
        else:
            fail += 1
            log("失敗：%s" % "、".join(codes))
        time.sleep(max(0, 60 - (time.time() - start)))
    log("結果：成功 %d 次、失敗 %d 次；每檔數字有變動的次數：%s" % (ok, fail, "、".join("%s %d" % kv for kv in changes.items())))


if __name__ == "__main__":
    if not KEY:
        raise SystemExit("沒有設定 FMP_API_KEY")
    log("金鑰長度 %d 個字元，開頭 %s…（只印前 3 碼確認有讀到）" % (len(KEY), KEY[:3]))
    m = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    probe_once() if m == 0 else watch(m)
    out = Path(__file__).resolve().parent.parent / "data" / "probe_fmp.log"
    out.write_text("\n".join(LOG) + "\n", encoding="utf-8")
