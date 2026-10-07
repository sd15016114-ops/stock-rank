#!/usr/bin/env python3
"""盤後抓取台股（上市＋上櫃）與美股的成交值排行，輸出 data/tw.json、data/us.json。

用法：
    python scraper/fetch_turnover.py          # 台股、美股都抓
    python scraper/fetch_turnover.py tw       # 只抓台股
    python scraper/fetch_turnover.py us       # 只抓美股

設計原則（比照利率站）：
- 只用官方或公開的盤後資料，一天各連線一次。
- 抓不到、筆數太少或數值異常時，不寫入壞資料，沿用前一次的檔案並標記 stale。
- 台股以證交所為主；櫃買中心抓不到或日期還沒更新時，先只出上市排行並標記 partial。
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent.parent / "data"
TPE = timezone(timedelta(hours=8))
BOT_UA = "StockRankBot/0.1 (daily after-close turnover ranking; +https://github.com/sd15016114-ops/stock-rank)"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")     # Nasdaq 不回應非瀏覽器的請求

TWSE_URLS = ("https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json",
             "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")      # 第二個是備援，更新較慢
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
NASDAQ_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true"

# 當日走勢小圖用的盤中資料（需要金鑰，放在 GitHub 的 Secrets；沒設定就略過，網頁改畫漲跌幅橫條）
FUGLE_URL = "https://api.fugle.tw/marketdata/v1.0/stock/intraday/candles/%s?timeframe=5"       # 富果，台股
ALPACA_URL = "https://data.alpaca.markets/v2/stocks/bars"                                       # Alpaca，美股
FUGLE_KEY = os.environ.get("FUGLE_API_KEY", "").strip()
ALPACA_ID = os.environ.get("ALPACA_API_KEY", "").strip()
ALPACA_SECRET = os.environ.get("ALPACA_API_SECRET", "").strip()

KEEP_STOCKS, KEEP_ETFS, KEEP_US = 100, 50, 100     # 每個市場保留的檔數
KEEP_DAYS = 30                                      # 保留最近幾個交易日的排行，供網頁切換日期與比較名次
MIN_ROWS = {"twse": 500, "tpex": 300, "us": 2000}  # 少於這個數字代表資料不完整


# ---------------------------------------------------------------- 共用
def get_json(url, ua=BOT_UA, tries=3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, timeout=40, headers={
                "User-Agent": ua, "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"})
            r.raise_for_status()
            return r.json()
        except Exception as e:      # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise last


def to_num(s):
    """'1,234.50'、'$12.3'、'+0.5'、'-1.2%' → 數字；'--'、'除息'、空白 → None。"""
    if isinstance(s, (int, float)):
        return float(s)
    t = re.sub(r"[,$%\s]", "", str(s or "")).replace("＋", "+").replace("－", "-")
    if not re.match(r"^[+-]?\d+(\.\d+)?$", t):
        return None
    return float(t)


def roc_date(s):
    """民國日期 '1151006' 或 '115/10/06'，或西元 '20261006' → '2026-10-06'。"""
    d = re.sub(r"\D", "", str(s or ""))
    if len(d) == 8:
        return "%s-%s-%s" % (d[:4], d[4:6], d[6:])
    if len(d) == 7:
        return "%d-%s-%s" % (int(d[:3]) + 1911, d[3:5], d[5:])
    return None


def tw_kind(code):
    """'etf'（00 開頭）、'stock'（四碼數字），其餘（權證、特別股、債券等）回傳 None 不收。"""
    if code.startswith("00"):
        return "etf"
    if len(code) == 4 and code.isdigit():
        return "stock"
    return None


def pick(rec, *names):
    for n in names:
        if n in rec and rec[n] not in (None, ""):
            return rec[n]
    return None


def tw_row(market, code, name, close, change, shares, value):
    code = str(code or "").strip()
    kind = tw_kind(code)
    close, value, shares, change = to_num(close), to_num(value), to_num(shares), to_num(change)
    if not kind or not value or close is None:
        return None
    prev = close - change if change is not None else None
    return {"code": code, "name": str(name or "").strip(), "market": market, "etf": kind == "etf",
            "close": close, "change": change,
            "pct": round(change / prev * 100, 2) if prev else None,
            "volume": int(shares or 0), "value": int(value)}


# ---------------------------------------------------------------- 台股
def parse_twse(payload):
    """回傳 (日期, 個股清單, 全市場成交值)。兩種格式都收：www 的 fields/data，或 openapi 的物件陣列。"""
    if isinstance(payload, dict):
        fields = [re.sub(r"\s", "", f) for f in payload.get("fields") or []]
        recs = [dict(zip(fields, r)) for r in payload.get("data") or []]
        date = roc_date(payload.get("date"))
    else:
        recs, date = payload, None
    rows, total = [], 0
    for r in recs:
        date = date or roc_date(pick(r, "Date", "日期"))
        total += to_num(pick(r, "TradeValue", "成交金額")) or 0
        row = tw_row("上市", pick(r, "Code", "證券代號"), pick(r, "Name", "證券名稱"),
                     pick(r, "ClosingPrice", "收盤價"), pick(r, "Change", "漲跌價差"),
                     pick(r, "TradeVolume", "成交股數"), pick(r, "TradeValue", "成交金額"))
        if row:
            rows.append(row)
    return date, rows, int(total)


def parse_tpex(payload):
    rows, total, date = [], 0, None
    for r in payload:
        date = date or roc_date(pick(r, "Date", "資料日期"))
        total += to_num(pick(r, "TransactionAmount", "成交金額")) or 0
        row = tw_row("上櫃", pick(r, "SecuritiesCompanyCode", "代號"), pick(r, "CompanyName", "名稱"),
                     pick(r, "Close", "收盤"), pick(r, "Change", "漲跌"),
                     pick(r, "TradingShares", "成交股數"), pick(r, "TransactionAmount", "成交金額"))
        if row:
            rows.append(row)
    return date, rows, int(total)


def top_of(rows):
    """每個市場留成交值前 100 檔個股＋前 50 檔 ETF，網頁怎麼篩都夠排出前 100 名。"""
    rows = sorted(rows, key=lambda r: -r["value"])
    return ([r for r in rows if not r["etf"]][:KEEP_STOCKS] + [r for r in rows if r["etf"]][:KEEP_ETFS])


def fetch_twse():
    best, err = None, None
    for url in TWSE_URLS:
        try:
            date, rows, total = parse_twse(get_json(url))
            if not date or len(rows) < MIN_ROWS["twse"]:
                raise ValueError("證交所資料不完整（%d 檔）" % len(rows))
            if not best or date > best[0]:
                best = (date, rows, total)
        except Exception as e:      # noqa: BLE001
            err = e
            print("      證交所 %s 讀取失敗：%s" % (url.split("/")[2], e))
    if not best:
        raise err
    return best


def build_tw(old=None):
    date, rows, total = fetch_twse()
    out = {"date": date, "status": "ok", "markets": {"上市": {"date": date, "count": len(rows), "total_value": total}},
           "sources": ["https://www.twse.com.tw/zh/trading/historical/stock-day-all.html"]}
    try:
        tdate, trows, ttotal = parse_tpex(get_json(TPEX_URL))
        if len(trows) < MIN_ROWS["tpex"]:
            raise ValueError("櫃買中心資料不完整（%d 檔）" % len(trows))
        if tdate != date:
            raise ValueError("櫃買中心日期是 %s，證交所是 %s，還沒同步" % (tdate, date))
        out["markets"]["上櫃"] = {"date": tdate, "count": len(trows), "total_value": ttotal}
        out["sources"].append("https://www.tpex.org.tw/zh-tw/mainboard/trading/info/pricing.html")
        rows = top_of(rows) + top_of(trows)
        total += ttotal
    except Exception as e:      # noqa: BLE001
        print("      上櫃資料未取得，先只出上市排行：%s" % e)
        out.update(status="partial", error="上櫃：%s" % e)
        rows = top_of(rows)
    rows = sorted(rows, key=lambda r: -r["value"])
    reuse_sparks(rows, old, date)
    out.update(total_value=total, rows=rows, spark=add_tw_sparks(rows, date))
    return out


# ---------------------------------------------------------------- 當日走勢
def reuse_sparks(rows, old, date):
    """同一個交易日已經抓過走勢的股票直接沿用，不重複連線。"""
    if not old or old.get("date") != date:
        return
    have = {r["code"]: r["spark"] for r in old.get("rows", []) if r.get("spark")}
    for r in rows:
        if r["code"] in have:
            r["spark"] = have[r["code"]]


def parse_fugle(payload, date):
    """富果日內 K 線 → 當日價格序列（開盤價＋每根 K 線收盤價）；日期不是當天就不收。"""
    data = (payload or {}).get("data") or []
    if (payload or {}).get("date") != date or len(data) < 2:
        return None
    return [data[0]["open"]] + [c["close"] for c in data]


def add_tw_sparks(rows, date):
    """回傳 (成功檔數, 應抓檔數)。免費方案每分鐘 60 次，所以每檔之間停 1.1 秒。"""
    todo = [r for r in rows if not r.get("spark")]
    if not FUGLE_KEY or not todo:
        return len(rows) - len(todo), len(rows) if FUGLE_KEY else 0
    s = requests.Session()
    s.headers.update({"X-API-KEY": FUGLE_KEY, "User-Agent": BOT_UA})
    for r in todo:
        for attempt in range(2):
            try:
                resp = s.get(FUGLE_URL % r["code"], timeout=20)
                if resp.status_code == 429:             # 超過速率限制，等一下再試一次
                    time.sleep(30)
                    continue
                if resp.status_code in (401, 403):
                    print("      富果金鑰無效或沒有權限（HTTP %d），略過走勢" % resp.status_code)
                    return sum(1 for x in rows if x.get("spark")), len(rows)
                pts = parse_fugle(resp.json(), date) if resp.ok else None
                if pts:
                    r["spark"] = pts
                break
            except Exception:       # noqa: BLE001   單一檔失敗不影響其他
                break
        time.sleep(1.1)
    return sum(1 for x in rows if x.get("spark")), len(rows)


def us_session_utc(date):
    """美股正常交易時段（紐約 09:30–16:00）換成 UTC 的起訖時間字串。"""
    from zoneinfo import ZoneInfo
    y, m, d = (int(x) for x in date.split("-"))
    ny = ZoneInfo("America/New_York")
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (datetime(y, m, d, 9, 30, tzinfo=ny).astimezone(timezone.utc).strftime(fmt),
            datetime(y, m, d, 16, 0, tzinfo=ny).astimezone(timezone.utc).strftime(fmt))


def parse_alpaca(payload, out):
    """Alpaca 多檔 K 線 → {代號: [(開盤, 收盤), ...]}，分頁時累加到 out。"""
    for sym, bars in ((payload or {}).get("bars") or {}).items():
        out.setdefault(sym, []).extend((b["o"], b["c"]) for b in bars)
    return (payload or {}).get("next_page_token")


def add_us_sparks(rows, date):
    todo = [r for r in rows if not r.get("spark")]
    if not (ALPACA_ID and ALPACA_SECRET) or not todo:
        return len(rows) - len(todo), len(rows) if ALPACA_ID and ALPACA_SECRET else 0
    start, end = us_session_utc(date)
    s = requests.Session()
    s.headers.update({"APCA-API-KEY-ID": ALPACA_ID, "APCA-API-SECRET-KEY": ALPACA_SECRET, "User-Agent": BOT_UA})
    bars = {}
    for i in range(0, len(todo), 50):
        params = {"symbols": ",".join(r["code"].replace("/", ".") for r in todo[i:i + 50]), "timeframe": "10Min",
                  "start": start, "end": end, "limit": 10000, "adjustment": "raw"}
        for _ in range(10):                             # 分頁
            try:
                resp = s.get(ALPACA_URL, params=params, timeout=30)
                if resp.status_code in (401, 403):
                    print("      Alpaca 金鑰無效或沒有權限（HTTP %d），略過走勢" % resp.status_code)
                    return sum(1 for x in rows if x.get("spark")), len(rows)
                resp.raise_for_status()
                token = parse_alpaca(resp.json(), bars)
            except Exception as e:  # noqa: BLE001
                print("      Alpaca 讀取失敗：%s" % e)
                break
            if not token:
                break
            params["page_token"] = token
        time.sleep(0.5)
    for r in todo:
        b = bars.get(r["code"].replace("/", "."))
        if b and len(b) >= 2:
            r["spark"] = [b[0][0]] + [c for _, c in b]
    return sum(1 for x in rows if x.get("spark")), len(rows)


# ---------------------------------------------------------------- 美股
US_SUFFIX = re.compile(r"\s+(Common Stock|Common Shares|Ordinary Shares|Class [A-C] (Common|Ordinary|Capital) (Stock|Shares)|"
                       r"American Depositary Shares?|Depositary Shares?)\b.*$", re.I)


def us_session_date(now=None):
    """最近一個已收盤的美股交易日（以紐約時間 16:00 為準；不含假日判斷）。"""
    try:
        from zoneinfo import ZoneInfo
        ny = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    except Exception:               # noqa: BLE001   沒有時區資料時用美東標準時間估算
        ny = (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=-5)))
    d = ny.date() if ny.hour >= 16 else ny.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def parse_us(payload):
    data = (payload or {}).get("data") or {}
    recs = data.get("rows") or (data.get("table") or {}).get("rows") or []
    rows, total = [], 0
    for r in recs:
        sym = str(r.get("symbol") or "").strip()
        close, vol = to_num(r.get("lastsale")), to_num(r.get("volume"))
        if not sym or not close or not vol or re.search(r"[\^/]", sym):     # ^ 與 / 是特別股、權證
            continue
        value = close * vol
        total += value
        change = to_num(r.get("netchange"))
        prev = close - change if change is not None else None
        rows.append({"code": sym, "name": US_SUFFIX.sub("", str(r.get("name") or "").strip()),
                     "sector": (r.get("sector") or "").strip(), "close": close, "change": change,
                     "pct": round(change / prev * 100, 2) if prev else to_num(r.get("pctchange")),
                     "volume": int(vol), "value": int(value)})
    return rows, int(total)


def build_us(old=None):
    rows, total = parse_us(get_json(NASDAQ_URL, ua=BROWSER_UA))
    if len(rows) < MIN_ROWS["us"]:
        raise ValueError("Nasdaq 資料不完整（%d 檔）" % len(rows))
    rows.sort(key=lambda r: -r["value"])
    date, count, rows = us_session_date(), len(rows), rows[:KEEP_US]
    reuse_sparks(rows, old, date)
    return {"date": date, "status": "ok", "count": count, "total_value": total,
            "sources": ["https://www.nasdaq.com/market-activity/stocks/screener"], "rows": rows,
            "spark": add_us_sparks(rows, date)}


# ---------------------------------------------------------------- 主程式
def suspicious(new, old):
    """與前一次相比，全市場成交值少於五分之一或多於五倍，多半是資料有問題。"""
    a, b = new.get("total_value"), (old or {}).get("total_value")
    if a and b and not 0.2 <= a / b <= 5:
        return "全市場成交值 %s→%s，變動過大請人工確認" % (b, a)
    return None


def save_history(key, snap):
    """把當天的排行另存一份到 data/history/<市場>/<日期>.json，只留最近 KEEP_DAYS 個交易日，並更新日期清單。"""
    folder = DATA / "history" / key
    folder.mkdir(parents=True, exist_ok=True)
    if snap and snap.get("date") and snap.get("rows"):
        (folder / ("%s.json" % snap["date"])).write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    files = sorted((f for f in folder.glob("*.json") if re.match(r"^\d{4}-\d\d-\d\d$", f.stem)), reverse=True)
    for f in files[KEEP_DAYS:]:
        f.unlink()
    dates = [f.stem for f in files[:KEEP_DAYS]]
    (DATA / ("%s_dates.json" % key)).write_text(json.dumps({"dates": dates}, ensure_ascii=False) + "\n", encoding="utf-8")
    return dates


def run(key, label, build):
    path = DATA / ("%s.json" % key)
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    now = datetime.now(TPE).isoformat(timespec="seconds")
    try:
        new = build(old)
        got, want = new.pop("spark", (0, 0))            # 走勢小圖抓到幾檔；沒設定金鑰時 want 為 0
        if not new["rows"] or new["rows"][0]["value"] <= 0:
            raise ValueError("排行是空的")
        bad = suspicious(new, old if old and old.get("rows") else None)
        if bad:
            raise ValueError(bad)
        same = old and {k: v for k, v in old.items() if k != "updated"} == new
        new["updated"] = old["updated"] if same else now      # 內容沒變就不改檔案，避免產生沒有意義的提交
        top = new["rows"][0]
        print("%-5s %s  %s  共 %d 檔  第一名 %s %s%s" % (
            "OK" if new["status"] == "ok" else "PART", label, new["date"], len(new["rows"]), top["code"], top["name"],
            "  （%s）" % new["error"] if new.get("error") else ""))
        if want:
            print("      當日走勢 %d/%d 檔" % (got, want))
        else:
            print("      未設定走勢資料的金鑰，略過當日走勢")
        ok = new["status"] == "ok" and (not want or got >= want * 0.5)     # 有設金鑰卻抓不到一半，視為失敗以便通知
        save_history(key, new)
    except Exception as e:          # noqa: BLE001
        print("FAIL  %s  %s" % (label, e))
        new = dict(old, status="stale", error=str(e), checked=now) if old and old.get("rows") else \
            {"updated": now, "status": "failed", "error": str(e), "rows": []}
        ok = False
    DATA.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return ok


def main(only):
    jobs = [("tw", "台股", build_tw), ("us", "美股", build_us)]
    results = [run(*j) for j in jobs if not only or j[0] in only]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:])))
