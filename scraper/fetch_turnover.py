#!/usr/bin/env python3
"""盤後抓取台股（上市＋上櫃）與美股的成交值排行，輸出 data/tw.json、data/us.json。

用法：
    python scraper/fetch_turnover.py          # 台股、美股都抓
    python scraper/fetch_turnover.py tw       # 只抓台股
    python scraper/fetch_turnover.py us       # 只抓美股
    python scraper/fetch_turnover.py backfill 60   # 回補台股最近 60 個交易日（全市場存檔、歷史排行、均值）

設計原則（比照利率站）：
- 只用官方或公開的盤後資料，一天各連線一次。
- 抓不到、筆數太少或數值異常時，不寫入壞資料，沿用前一次的檔案並標記 stale。
- 台股以證交所為主；櫃買中心抓不到或日期還沒更新時，先只出上市排行並標記 partial。
"""
import builtins
import csv
import io
import json
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

KEEP_STOCKS, KEEP_ETFS, KEEP_US = 100, 50, 100     # 每個市場保留的檔數
KEEP_DAYS = 60                                      # 保留最近幾個交易日的排行，供網頁切換日期與比較名次
KEEP_FULL = 65                                      # 全市場精簡檔保留幾個交易日（算 60 日均值要用到當天以前的 60 天）
AVG_DAYS = 60                                       # 均值取當天以前的幾個交易日
AVG_MIN_DAYS = 5                                    # 少於這個天數就不算均值，避免剛上市或資料太少時失真

# 可以指定日期的來源：回補歷史用，平常也當作備援
MI_INDEX_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date=%s&type=ALLBUT0999"          # 20261006
TPEX_DAY_URL = ("https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php"
                "?l=zh-tw&o=json&d=%s&se=EW")                                                                         # 115/10/06
# 產業別（公司基本資料，變動很少，一週更新一次）
IND_TWSE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
IND_TPEX_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
IND_REFRESH_DAYS = 7
IND_TOP = 12                                        # 熱力圖每個產業列出成交值前幾檔
INDUSTRY_NAMES = {
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維", "05": "電機機械", "06": "電器電纜",
    "08": "玻璃陶瓷", "09": "造紙工業", "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業", "14": "建材營造",
    "15": "航運業", "16": "觀光餐旅", "17": "金融保險", "18": "貿易百貨", "19": "綜合", "20": "其他",
    "21": "化學工業", "22": "生技醫療", "23": "油電燃氣", "24": "半導體", "25": "電腦及週邊", "26": "光電",
    "27": "通信網路", "28": "電子零組件", "29": "電子通路", "30": "資訊服務", "31": "其他電子", "32": "文化創意",
    "33": "農業科技", "34": "電子商務", "35": "綠能環保", "36": "數位雲端", "37": "運動休閒", "38": "居家生活",
    "80": "管理股票", "91": "存託憑證",
}
MIN_ROWS = {"twse": 500, "tpex": 300, "us": 2000}  # 少於這個數字代表資料不完整


# ---------------------------------------------------------------- 共用
LOG = []


def print(*args):               # noqa: A001   訊息同時留一份，寫進 data/run_<市場>.log 方便事後查看
    LOG.append(" ".join(str(a) for a in args))
    builtins.print(*args)


def get_text(url, ua=BOT_UA, tries=3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, timeout=40, headers={
                "User-Agent": ua, "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8", "Cache-Control": "no-cache"})
            r.raise_for_status()
            r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
            return r.text.lstrip("\ufeff")
        except Exception as e:      # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise last


def records(text):
    """回應可能是 JSON，也可能是 CSV（證交所官網有時回 CSV）；CSV 轉成和 openapi 一樣的物件陣列。"""
    t = text.strip()
    if t[:1] in "{[":
        return json.loads(t)
    lines = t.splitlines()
    head = next(i for i, l in enumerate(lines) if "證券代號" in l)
    rows = list(csv.reader(io.StringIO("\n".join(lines[head:]))))
    names = [re.sub(r"\s", "", c) for c in rows[0]]
    clean = lambda c: re.sub(r'^="?|"$', "", c.strip())
    return [dict(zip(names, (clean(c) for c in r))) for r in rows[1:] if len(r) >= len(names) - 1 and r[0].strip()]

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


def clean_field(f):
    return re.sub(r"<[^>]*>|\s", "", str(f or ""))


def find_table(payload, *need):
    """在 tables 裡找欄位名稱同時包含指定字樣的那張表，回傳 [每列的 {欄位: 值}]。"""
    for t in (payload or {}).get("tables") or []:
        fields = [clean_field(f) for f in (t or {}).get("fields") or []]
        if all(any(n == f or (n.endswith("*") and f.startswith(n[:-1])) for f in fields) for n in need):
            return [dict(zip(fields, r)) for r in t.get("data") or []]
    return None


def parse_mi_index(payload):
    """證交所「每日收盤行情」指定日期版。休市日回傳 (None, [], 0)。
    漲跌價差沒有正負號，方向要看「漲跌(+/-)」欄位 HTML 裡的顏色：red 漲、green 跌。"""
    recs = find_table(payload, "證券代號", "成交金額")
    if (payload or {}).get("stat") != "OK" or not recs:
        return None, [], 0
    rows, total = [], 0
    for r in recs:
        total += to_num(r.get("成交金額")) or 0
        mark = str(r.get("漲跌(+/-)") or "")
        sign = 1 if "red" in mark else -1 if "green" in mark else 0
        diff = to_num(r.get("漲跌價差"))
        row = tw_row("上市", r.get("證券代號"), r.get("證券名稱"), r.get("收盤價"),
                     None if diff is None else sign * abs(diff), r.get("成交股數"), r.get("成交金額"))
        if row:
            rows.append(row)
    return roc_date(payload.get("date")), rows, int(total)


def parse_tpex_day(payload):
    """櫃買中心「上櫃股票每日收盤行情」指定日期版；「漲跌」欄位本身帶正負號。休市日回傳 (None, [], 0)。"""
    recs = find_table(payload, "代號", "成交金額*")
    if not recs:
        return None, [], 0
    rows, total = [], 0
    for r in recs:
        amount = pick(r, "成交金額(元)", "成交金額")
        total += to_num(amount) or 0
        row = tw_row("上櫃", r.get("代號"), r.get("名稱"), r.get("收盤"), r.get("漲跌"), r.get("成交股數"), amount)
        if row:
            rows.append(row)
    return roc_date(payload.get("date")), rows, int(total)


def fetch_day(date):
    """抓指定日期（'2026-10-06'）的上市與上櫃全市場行情；休市日回傳 None。"""
    y, m, d = date.split("-")
    tdate, trows, ttotal = parse_mi_index(json.loads(get_text(MI_INDEX_URL % (y + m + d), ua=BROWSER_UA)))
    if not trows:
        return None
    time.sleep(3)
    odate, orows, ototal = parse_tpex_day(json.loads(get_text(TPEX_DAY_URL % ("%d/%s/%s" % (int(y) - 1911, m, d)), ua=BROWSER_UA)))
    if tdate != date or (orows and odate != date):
        raise ValueError("回傳的日期不符：要 %s，證交所 %s、櫃買 %s" % (date, tdate, odate))
    if len(trows) < MIN_ROWS["twse"] or len(orows) < MIN_ROWS["tpex"]:
        raise ValueError("%s 資料不完整（上市 %d 檔、上櫃 %d 檔）" % (date, len(trows), len(orows)))
    return trows, ttotal, orows, ototal


# ---- 全市場精簡檔：data/full/tw/<日期>.json，只留代號、收盤、成交值，用來算均值
def full_dir():
    return DATA / "full" / "tw"


def full_dates():
    return sorted((f.stem for f in full_dir().glob("*.json") if re.match(r"^\d{4}-\d\d-\d\d$", f.stem)), reverse=True)


def save_full(date, trows, orows):
    full_dir().mkdir(parents=True, exist_ok=True)
    slim = lambda rows: [[r["code"], r["close"], r["value"]] for r in sorted(rows, key=lambda r: r["code"])]
    text = json.dumps({"date": date, "上市": slim(trows), "上櫃": slim(orows)}, ensure_ascii=False, separators=(",", ":"))
    (full_dir() / ("%s.json" % date)).write_text(text + "\n", encoding="utf-8")
    for old in full_dates()[KEEP_FULL:]:
        (full_dir() / ("%s.json" % old)).unlink()


def values_before(date, cache={}):
    """指定日期以前最近 AVG_DAYS 個交易日的 [{代號: 成交值}]（新到舊）。"""
    out = []
    for d in [x for x in full_dates() if x < date][:AVG_DAYS]:
        if d not in cache:
            j = json.loads((full_dir() / ("%s.json" % d)).read_text(encoding="utf-8"))
            cache[d] = {r[0]: r[2] for r in j.get("上市", []) + j.get("上櫃", [])}
        out.append(cache[d])
    return out


def apply_avg(snap):
    """每一列加上 avg（近 N 日平均成交值，不含當天）與 ratio（當日成交值 ÷ 均值）。"""
    days = values_before(snap["date"])
    snap["avg_days"] = len(days)
    for r in snap["rows"]:
        vals = [d[r["code"]] for d in days if r["code"] in d]
        r.pop("avg", None)
        r.pop("ratio", None)
        if len(vals) >= AVG_MIN_DAYS and sum(vals) > 0:
            avg = sum(vals) / len(vals)
            r["avg"], r["ratio"] = int(avg), round(r["value"] / avg, 2)
    return snap


# ---- 產業別
def industry_path():
    return DATA / "industry_tw.json"


def load_industry(refresh=True):
    """回傳 {代號: 產業名稱}。檔案超過一週才重新抓；抓不到就沿用舊的。"""
    old = json.loads(industry_path().read_text(encoding="utf-8")) if industry_path().exists() else {}
    age = (datetime.now(TPE) - datetime.fromisoformat(old["updated"])).days if old.get("updated") else 999
    if not refresh or age < IND_REFRESH_DAYS:
        return old.get("map", {})
    try:
        m = {}
        for url, code_key, ind_key in ((IND_TWSE_URL, "公司代號", "產業別"), (IND_TPEX_URL, "SecuritiesCompanyCode", "SecuritiesIndustryCode")):
            for r in get_json(url):
                code, ind = str(r.get(code_key) or "").strip(), str(r.get(ind_key) or "").strip().zfill(2)
                if code:
                    m[code] = INDUSTRY_NAMES.get(ind, "其他")
            time.sleep(2)
        if len(m) < 1500:
            raise ValueError("只有 %d 家" % len(m))
        industry_path().write_text(json.dumps({"updated": datetime.now(TPE).isoformat(timespec="seconds"), "map": m},
                                              ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
        print("      產業別已更新，共 %d 家" % len(m))
        return m
    except Exception as e:      # noqa: BLE001
        print("      產業別更新失敗，沿用舊資料：%s" % e)
        return old.get("map", {})


def industry_of(row, imap):
    return "ETF" if row["etf"] else imap.get(row["code"], "其他")


def industries(rows, imap):
    """各產業的成交值加總與漲跌幅（以成交值加權平均），並列出成交值最大的幾檔，給熱力圖用。"""
    groups = {}
    for r in rows:
        groups.setdefault(industry_of(r, imap), []).append(r)
    out = []
    for name, rs in groups.items():
        rs.sort(key=lambda r: -r["value"])
        value = sum(r["value"] for r in rs)
        w = [(r["pct"], r["value"]) for r in rs if r["pct"] is not None]
        wsum = sum(v for _, v in w)
        out.append({"name": name, "value": value, "count": len(rs),
                    "pct": round(sum(p * v for p, v in w) / wsum, 2) if wsum else None,
                    "top": [[r["code"], r["name"], r["value"], r["pct"]] for r in rs[:IND_TOP]]})
    return sorted(out, key=lambda g: -g["value"])


def snapshot(date, trows, ttotal, orows, ototal, sources):
    """把一天的上市＋上櫃全市場行情整理成網頁用的格式（排行、產業、均值）。"""
    imap = load_industry()
    snap = {"date": date, "status": "ok",
            "markets": {"上市": {"date": date, "count": len(trows), "total_value": ttotal},
                        "上櫃": {"date": date, "count": len(orows), "total_value": ototal}},
            "sources": sources, "total_value": ttotal + ototal,
            "rows": sorted(top_of(trows) + top_of(orows), key=lambda r: -r["value"])}
    if imap:
        snap["industries"] = industries(trows + orows, imap)
        for r in snap["rows"]:
            r["ind"] = industry_of(r, imap)
    return apply_avg(snap)


def top_of(rows):
    """每個市場留成交值前 100 檔個股＋前 50 檔 ETF，網頁怎麼篩都夠排出前 100 名。"""
    rows = sorted(rows, key=lambda r: -r["value"])
    return ([r for r in rows if not r["etf"]][:KEEP_STOCKS] + [r for r in rows if r["etf"]][:KEEP_ETFS])


def fetch_twse():
    best, err = None, None
    for url in TWSE_URLS:
        try:
            fresh = url + ("&" if "?" in url else "?") + "_=%d" % int(time.time())   # 加上時間參數，避免拿到快取裡前一天的舊資料
            date, rows, total = parse_twse(records(get_text(fresh)))
            print("      證交所 %s：%s，%d 檔" % (url.split("/")[2], date, len(rows)))
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


SRC_TWSE = "https://www.twse.com.tw/zh/trading/historical/mi-index.html"
SRC_TPEX = "https://www.tpex.org.tw/zh-tw/mainboard/trading/info/pricing.html"


def build_tw():
    date, rows, total = fetch_twse()
    try:
        tdate, trows, ttotal = parse_tpex(get_json(TPEX_URL + "?_=%d" % int(time.time())))
        if len(trows) < MIN_ROWS["tpex"]:
            raise ValueError("櫃買中心資料不完整（%d 檔）" % len(trows))
        print("      櫃買中心：%s，%d 檔" % (tdate, len(trows)))
        if tdate != date:
            raise ValueError("櫃買中心日期是 %s，證交所是 %s，還沒同步" % (tdate, date))
    except Exception as e:      # noqa: BLE001
        print("      上櫃資料未取得，先只出上市排行：%s" % e)
        return {"date": date, "status": "partial", "error": "上櫃：%s" % e,
                "markets": {"上市": {"date": date, "count": len(rows), "total_value": total}},
                "sources": [SRC_TWSE], "total_value": total, "rows": sorted(top_of(rows), key=lambda r: -r["value"])}
    save_full(date, rows, trows)
    return snapshot(date, rows, total, trows, ttotal, [SRC_TWSE, SRC_TPEX])


def backfill(want):
    """回補台股最近 want 個交易日：全市場精簡檔、每日排行，最後重算每一天的均值。休市日（來源回空的）自動跳過。"""
    del LOG[:]
    try:
        have, day, scanned, added = set(full_dates()), datetime.now(TPE).date(), 0, 0
        latest_path = DATA / "tw.json"
        latest = json.loads(latest_path.read_text(encoding="utf-8")) if latest_path.exists() else {}
        folder = DATA / "history" / "tw"
        folder.mkdir(parents=True, exist_ok=True)
        while len(have) < want and scanned < want * 2 + 30:
            d = day.isoformat()
            day -= timedelta(days=1)
            scanned += 1
            if date_weekday(d) >= 5 or d in have:
                continue
            try:
                got = fetch_day(d)
            except Exception as e:      # noqa: BLE001
                print("FAIL  %s  %s" % (d, e))
                time.sleep(10)
                continue
            if not got:
                print("----  %s  休市" % d)
                time.sleep(3)
                continue
            trows, ttotal, orows, ototal = got
            save_full(d, trows, orows)
            snap = snapshot(d, trows, ttotal, orows, ototal, [SRC_TWSE, SRC_TPEX])
            snap["updated"] = datetime.now(TPE).isoformat(timespec="seconds")
            (folder / ("%s.json" % d)).write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            have.add(d)
            added += 1
            print("OK    %s  上市 %d 檔、上櫃 %d 檔，第一名 %s" % (d, len(trows), len(orows), snap["rows"][0]["name"]))
            time.sleep(4)               # 證交所對連續請求有限制，放慢一點
        # 全部補完後，每一天往前看得到的天數才齊，重算一次均值
        values_before.__defaults__[0].clear()
        for f in sorted(folder.glob("*.json")):
            snap = json.loads(f.read_text(encoding="utf-8"))
            if snap.get("rows") and snap.get("date"):
                f.write_text(json.dumps(apply_avg(snap), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        dates = save_history("tw", None)
        newest = folder / ("%s.json" % dates[0]) if dates else None
        if newest and (not latest.get("rows") or latest.get("date", "") <= dates[0]):
            latest_path.write_text(newest.read_text(encoding="utf-8"), encoding="utf-8")
        print("回補完成：新增 %d 天，全市場存檔共 %d 天，歷史排行共 %d 天" % (added, len(full_dates()), len(dates)))
        return 0 if len(full_dates()) >= min(want, 5) else 1
    finally:
        (DATA / "run_backfill.log").write_text(datetime.now(TPE).isoformat(timespec="seconds") + "\n" + "\n".join(LOG) + "\n", encoding="utf-8")


def date_weekday(d):
    y, m, dd = (int(x) for x in d.split("-"))
    return datetime(y, m, dd).weekday()


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


def build_us():
    rows, total = parse_us(get_json(NASDAQ_URL, ua=BROWSER_UA))
    if len(rows) < MIN_ROWS["us"]:
        raise ValueError("Nasdaq 資料不完整（%d 檔）" % len(rows))
    rows.sort(key=lambda r: -r["value"])
    return {"date": us_session_date(), "status": "ok", "count": len(rows), "total_value": total,
            "sources": ["https://www.nasdaq.com/market-activity/stocks/screener"], "rows": rows[:KEEP_US]}


# ---------------------------------------------------------------- 主程式
def suspicious(new, old):
    """與前一次相比，全市場成交值少於五分之一或多於五倍，多半是資料有問題。"""
    a, b = new.get("total_value"), (old or {}).get("total_value")
    if a and b and not 0.2 <= a / b <= 5:
        return "全市場成交值 %s→%s，變動過大請人工確認" % (b, a)
    return None


def same_market(a, b):
    sig = lambda d: [(r["code"], r["close"], r["volume"]) for r in d.get("rows", [])]
    return sig(a) == sig(b)


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
    del LOG[:]
    try:
        return run_inner(key, label, build)
    finally:
        DATA.mkdir(parents=True, exist_ok=True)
        (DATA / ("run_%s.log" % key)).write_text(datetime.now(TPE).isoformat(timespec="seconds") + "\n" + "\n".join(LOG) + "\n", encoding="utf-8")


def run_inner(key, label, build):
    path = DATA / ("%s.json" % key)
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    now = datetime.now(TPE).isoformat(timespec="seconds")
    try:
        new = build()
        if new["status"] == "partial" and old and old.get("status") == "ok" and old.get("rows") and old.get("date", "") >= new["date"]:
            # 兩個來源還沒同步（例如櫃買已公布今天、證交所還沒），手上已有同一天的完整排行就不要用不完整的蓋掉
            print("SKIP  %s  %s；保留現有的 %s 完整排行，等下一次更新" % (label, new.get("error"), old["date"]))
            save_history(key, None)
            return True
        if not new["rows"] or new["rows"][0]["value"] <= 0:
            raise ValueError("排行是空的")
        if key == "us" and old and old.get("rows") and old.get("date") != new["date"] and same_market(new, old):
            # 價量和前一個交易日完全相同，代表美股休市（或來源還沒更新）：不當成新的一天存檔
            print("SKIP  %s  內容與 %s 完全相同，判定 %s 休市，不存檔" % (label, old["date"], new["date"]))
            return True
        bad = suspicious(new, old if old and old.get("rows") else None)
        if bad:
            raise ValueError(bad)
        same = old and {k: v for k, v in old.items() if k != "updated"} == new
        new["updated"] = old["updated"] if same else now      # 內容沒變就不改檔案，避免產生沒有意義的提交
        top = new["rows"][0]
        print("%-5s %s  %s  共 %d 檔  第一名 %s %s%s" % (
            "OK" if new["status"] == "ok" else "PART", label, new["date"], len(new["rows"]), top["code"], top["name"],
            "  （%s）" % new["error"] if new.get("error") else ""))
        ok = new["status"] == "ok"
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
    if "backfill" in only:
        n = [int(a) for a in sys.argv[1:] if a.isdigit()]
        return backfill(n[0] if n else 60)
    jobs = [("tw", "台股", build_tw), ("us", "美股", build_us)]
    results = [run(*j) for j in jobs if not only or j[0] in only]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(set(sys.argv[1:])))
