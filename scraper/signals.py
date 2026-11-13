"""連續訊號與個股卡片的資料。每天盤後跑（法人資料出來之後）：
  1. 算出連續放量、外資連買、投信連買、外資投信同步買、板塊連續增加 → data/signals_tw.json
  2. 全市場每一檔最近 60 個交易日的收盤、成交值、外資、投信 → 寫進 Supabase 的 stock_hist 表（個股卡片讀）

資料來源都是自己存的：data/full/tw（全市場收盤與成交值）、data/full/chips（全市場法人買賣超）、
data/names_tw.json（名稱）、data/industry_tw.json（產業）、data/rotation_tw.json（板塊占比）。
用法：python scraper/signals.py [--no-upload]"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DAYS = 60                 # 卡片與訊號看最近 60 個交易日
AVG_DAYS = 60             # 放大倍數：跟前 60 日平均比
MIN_PRIOR = 20            # 前面至少有 20 天才算放大倍數
MIN_LISTED = 60           # 資料裡不到 60 個交易日的新股不列放量（平常的量算不準，倍數沒有意義）
RATIO_HOT = 1.5           # 放量的門檻
MIN_STREAK = 3            # 至少連續 3 天才列入
TOP = 80                  # 每一種訊號最多列幾檔
MIN_VALUE = 5e7           # 最新一天成交值至少 5,000 萬，太冷門的不列
TPE = timezone(timedelta(hours=8))
SBL_HOT = 2.0             # 借券賣出是前 20 日平均的 2 倍以上
SBL_MIN_AMT = 2e7         # 而且借券賣出金額至少 2,000 萬
DT_MIN_VALUE = 3e8        # 當沖比例只看成交值 3 億以上的
DT_TOP = 60
EXTRA_URLS = {
    "dt": ("https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?date=%(ymd)s&selectType=All&response=json",
           "https://www.tpex.org.tw/web/stock/trading/intraday_stat/intraday_trading_stat_result.php?l=zh-tw&o=json&d=%(roc)s"),
    "sbl": ("https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date=%(ymd)s&response=json",
            "https://www.tpex.org.tw/web/stock/margin_trading/margin_sbl/margin_sbl_result.php?l=zh-tw&o=json&d=%(roc)s"),
}


def jload(p, default=None):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


# ---------------------------------------------------------------- 當沖、借券賣出（盤後公布，缺哪天補哪天）
def parse_dt(payload):
    """當日沖銷交易標的及成交量值 → {代號: 當沖成交金額（買進、賣出平均，元）}"""
    from fetch_turnover import raw_table, to_num
    fields, data = raw_table(payload, "證券代號", "當日沖銷交易買進成交金額", "當日沖銷交易賣出成交金額")
    if not fields:
        return {}
    i = {f: k for k, f in enumerate(fields)}
    out = {}
    for r in data:
        b, s_ = to_num(r[i["當日沖銷交易買進成交金額"]]), to_num(r[i["當日沖銷交易賣出成交金額"]])
        if b is not None and s_ is not None:
            out[str(r[0]).strip()] = int((b + s_) / 2)
    return out


def parse_sbl(payload):
    """信用額度總量管制餘額表 → {代號: [借券當日賣出, 當日還券, 當日餘額]}（張）。
    欄位依序：代號、名稱、融券六欄、借券（前日餘額、當日賣出、當日還券、當日調整、當日餘額、次一營業日可限額）、備註"""
    from fetch_turnover import raw_table, lots
    fields, data = raw_table(payload, "當日賣出", "當日還券")
    if not fields or len(fields) < 13 or fields[9] != "當日賣出" or fields[10] != "當日還券" or fields[12] != "當日餘額":
        return {}
    return {str(r[0]).strip(): [lots(r[9]) or 0, lots(r[10]) or 0, lots(r[12]) or 0] for r in data if len(r) >= 13 and str(r[0]).strip()}


def fetch_extra(dates):
    """最近 DAYS 個交易日裡，當沖、借券還沒存的日子去抓（上市、上櫃都有資料才存，沒公布的下次再抓）"""
    from fetch_turnover import get_text, BROWSER_UA
    parsers = {"dt": parse_dt, "sbl": parse_sbl}
    got = 0
    for kind, (u1, u2) in EXTRA_URLS.items():
        folder = DATA / "full" / kind
        folder.mkdir(parents=True, exist_ok=True)
        for d in dates:
            f = folder / ("%s.json" % d)
            if f.exists():
                continue
            y, m, dd = d.split("-")
            keys = {"ymd": y + m + dd, "roc": "%d/%s/%s" % (int(y) - 1911, m, dd)}
            parts = []
            for u in (u1, u2):
                try:
                    parts.append(parsers[kind](json.loads(get_text(u % keys, ua=BROWSER_UA, tries=2))))
                except Exception as e:             # noqa: BLE001
                    print("  %s %s 讀取失敗：%s" % (d, kind, e))
                    parts.append({})
                time.sleep(3)                      # 證交所、櫃買對連續請求有限制
            if all(parts):
                f.write_text(json.dumps(dict(parts[0], **parts[1]), separators=(",", ":")) + "\n", encoding="utf-8")
                got += 1
            else:
                print("  %s %s 還沒公布（上市 %d、上櫃 %d 檔）" % (d, kind, len(parts[0]), len(parts[1])))
    keep = set(dates)
    for kind in EXTRA_URLS:                        # 超過 DAYS 天的舊檔刪掉
        for f in (DATA / "full" / kind).glob("*.json"):
            if f.stem not in keep and f.stem < min(dates):
                f.unlink()
    print("當沖、借券：新抓 %d 份" % got)


def load_days():
    """全市場每天的 {代號: (收盤, 成交值)}，舊到新"""
    files = sorted((DATA / "full" / "tw").glob("*.json"))
    days = []
    for f in files:
        j = jload(f)
        days.append((j["date"], {r[0]: (r[1], r[2]) for mk in ("上市", "上櫃") for r in j.get(mk, [])}))
    return days


def streak(flags):
    n = 0
    for x in reversed(flags):
        if not x:
            break
        n += 1
    return n


def build():
    days = load_days()
    chips = {f.stem: jload(f) for f in (DATA / "full" / "chips").glob("*.json")}
    dts = {f.stem: jload(f) for f in (DATA / "full" / "dt").glob("*.json")}
    sbls = {f.stem: jload(f) for f in (DATA / "full" / "sbl").glob("*.json")}
    names = {}
    for f in sorted((DATA / "history" / "tw").glob("*.json")) + [DATA / "tw.json"]:   # 排行裡出現過的名稱先墊底
        for r in (jload(f, {}) or {}).get("rows", []):
            names[r["code"]] = r["name"]
    names.update(jload(DATA / "names_tw.json", {}) or {})                            # 全市場名稱（盤後抓的）為準
    imap = (jload(DATA / "industry_tw.json", {}) or {}).get("map", {})
    win = days[-DAYS:]
    dates = [d for d, _ in win]
    first = len(days) - len(win)
    stocks = {}
    for code in win[-1][1]:
        close, value, pct, ratio, f, t, dt, sbl, sblb = [], [], [], [], [], [], [], [], []
        for k in range(first, len(days)):
            d, m = days[k]
            c, v = m.get(code, (None, None))
            prev = days[k - 1][1].get(code) if k > 0 else None
            close.append(c)
            value.append(v)
            pct.append(round((c / prev[0] - 1) * 100, 2) if c and prev and prev[0] else None)
            prior = [days[j][1][code][1] for j in range(max(0, k - AVG_DAYS), k) if code in days[j][1]]
            ratio.append(round(v / (sum(prior) / len(prior)), 2) if v and len(prior) >= MIN_PRIOR and sum(prior) else None)
            ch = chips.get(d)
            x = ch.get(code) if ch else None
            f.append(x[0] if x else (0 if ch else None))       # 那天有法人資料但沒這檔＝沒買賣
            t.append(x[1] if x else (0 if ch else None))
            dd = dts.get(d)
            dt.append(round(dd.get(code, 0) / v * 100, 1) if dd is not None and v else None)    # 當沖占成交值 %
            sb = sbls.get(d)
            y = sb.get(code) if sb else None
            sbl.append(y[0] if y else (0 if sb else None))       # 借券賣出（張）
            sblb.append(y[2] if y else (0 if sb else None))      # 借券賣出餘額（張）
        prior = [days[j][1][code][1] for j in range(max(0, len(days) - 1 - AVG_DAYS), len(days) - 1) if code in days[j][1]]
        listed = sum(1 for _, m in days if code in m)
        stocks[code] = {"listed": listed, "name": names.get(code, code), "ind": "ETF" if code.startswith("00") else imap.get(code, ""),
                        "close": close, "value": value, "pct": pct, "ratio": ratio, "f": f, "t": t, "dt": dt, "sbl": sbl, "sblb": sblb,
                        "avg": round(sum(prior) / len(prior)) if prior else None}
    return dates, stocks


def sg(x):
    return 0 if not x else 1 if x > 0 else -1


def day_dirs(k, s, ok):
    """最近 10 天每天的方向（1 紅、-1 綠、0 空心）：
    法人連買：當天買超紅、賣超綠；同步買：兩個都買紅、兩個都賣綠；放量：有放量的那天看漲跌上色"""
    if k == "f":
        d = [sg(x) for x in s["f"]]
    elif k == "t":
        d = [sg(x) for x in s["t"]]
    elif k == "ft":
        d = [1 if sg(a) == sg(b) == 1 else -1 if sg(a) == sg(b) == -1 else 0 for a, b in zip(s["f"], s["t"])]
    else:
        d = [(sg(p) or 1) if o else 0 for o, p in zip(ok, s["pct"])]
    return d[-10:]


def signals(dates, stocks):
    out = {k: [] for k in ("vol", "f", "t", "ft")}
    for code, s in stocks.items():
        if code.startswith("00") or (s["value"][-1] or 0) < MIN_VALUE:
            continue
        tests = {"vol": [r is not None and r >= RATIO_HOT and s["listed"] >= MIN_LISTED for r in s["ratio"]],
                 "f": [x is not None and x > 0 for x in s["f"]],
                 "t": [x is not None and x > 0 for x in s["t"]],
                 "ft": [a is not None and b is not None and a > 0 and b > 0 for a, b in zip(s["f"], s["t"])]}
        for k, ok in tests.items():
            n = streak(ok)
            if n < MIN_STREAK:
                continue
            amt = None
            if k in ("f", "t", "ft"):
                arr = s["t"] if k == "t" else s["f"]
                amt = sum(arr[-n:])
            out[k].append({"code": code, "name": s["name"], "ind": s["ind"], "close": s["close"][-1], "pct": s["pct"][-1],
                           "n": n, "dots": ok[-10:], "dd": day_dirs(k, s, ok), "amt": amt, "amt_t": sum(s["t"][-n:]) if k == "ft" else None,
                           "value": s["value"][-1], "ratio": s["ratio"][-1]})
    for k in out:
        out[k].sort(key=lambda x: (-x["n"], -(x["amt"] if x["amt"] is not None else x["value"] or 0)))
        out[k] = out[k][:TOP]
    out.update(extra_signals(stocks))
    rot = jload(DATA / "rotation_tw.json", {})
    sec = []
    for kind in ("ind", "th"):
        for name, sh in (rot.get(kind) or {}).items():
            if name in ("ETF", "其他") or len(sh) < 3:
                continue
            up = [i > 0 and sh[i] > sh[i - 1] for i in range(len(sh))]
            n = streak(up)
            if n >= 2 and sh[-1] >= 0.3:
                dd = [0 if i == 0 else sg(round(sh[i] - sh[i - 1], 3)) for i in range(len(sh))][-10:]
                sec.append({"kind": kind, "name": name, "n": n, "dots": up[-10:], "dd": dd, "share": sh[-1], "chg": round(sh[-1] - sh[-1 - n], 3)})
    sec.sort(key=lambda x: (-x["n"], -x["chg"]))
    chip_days = sum(1 for d in dates if (DATA / "full" / "chips" / ("%s.json" % d)).exists())
    return {"date": dates[-1], "updated": datetime.now(TPE).isoformat(timespec="seconds"), "chip_days": chip_days,
            "extra_days": sum(1 for d in dates if (DATA / "full" / "dt" / ("%s.json" % d)).exists()),
            "rot_date": (rot.get("dates") or [None])[-1], "sig": out, "sec": sec[:40]}


def avg_prior(arr, n=20):
    xs = [x for x in arr[-1 - n:-1] if x is not None]
    return sum(xs) / len(xs) if len(xs) >= 5 else None


def extra_signals(stocks):
    """借券賣出暴增、借券餘額連增、當沖比例高"""
    sbl, sblb, dt = [], [], []
    for code, s in stocks.items():
        if code.startswith("00"):
            continue
        c, v = s["close"][-1], s["value"][-1] or 0
        base = {"code": code, "name": s["name"], "ind": s["ind"], "close": c, "pct": s["pct"][-1], "value": v}
        today = s["sbl"][-1]
        if today and c:
            a = avg_prior(s["sbl"])
            amt = today * 1000 * c
            if amt >= SBL_MIN_AMT and (a is None or a == 0 or today >= SBL_HOT * a):
                sbl.append(dict(base, lots=today, amt=amt, x=round(today / a, 1) if a else None, bal=s["sblb"][-1],
                                dbal=(s["sblb"][-1] - s["sblb"][-2]) if s["sblb"][-2] is not None else None))
        up = [i > 0 and a is not None and b is not None and a > b for i, (a, b) in enumerate(zip(s["sblb"], [None] + s["sblb"][:-1]))]
        n = streak(up)
        if n >= MIN_STREAK and v >= MIN_VALUE:
            bal = s["sblb"]
            sblb.append(dict(base, n=n, dots=up[-10:], dd=[0 if i == 0 or bal[i] is None or bal[i - 1] is None else -sg(bal[i] - bal[i - 1]) for i in range(len(bal))][-10:], bal=s["sblb"][-1], add=s["sblb"][-1] - s["sblb"][-1 - n]))
        r = s["dt"][-1]
        if r is not None and v >= DT_MIN_VALUE:
            dt.append(dict(base, r=r, avg=round(avg_prior(s["dt"]), 1) if avg_prior(s["dt"]) is not None else None))
    sbl.sort(key=lambda x: -x["amt"])
    sblb.sort(key=lambda x: (-x["n"], -x["add"]))
    dt.sort(key=lambda x: -x["r"])
    return {"sbl": sbl[:TOP], "sblb": sblb[:TOP], "dt": dt[:DT_TOP]}


def upload(dates, stocks):
    url = re.sub(r"(/rest/v1)?/*$", "", os.environ.get("SUPABASE_URL", "").strip())
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not url or not key:
        print("沒有設定 Supabase，跳過上傳")
        return
    headers = {"apikey": key, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}
    if not key.startswith("sb_"):
        headers["Authorization"] = "Bearer " + key
    rows = []
    for code, s in stocks.items():
        rows.append({"code": code, "updated_at": datetime.now(TPE).isoformat(timespec="seconds"), "data": {
            "name": s["name"], "ind": s["ind"], "dates": dates, "avg": round(s["avg"] / 1e6) if s["avg"] else None,
            "close": s["close"], "pct": s["pct"], "ratio": s["ratio"], "f": s["f"], "t": s["t"],
            "dt": s["dt"], "sbl": s["sbl"], "sblb": s["sblb"],
            "value": [round(v / 1e6) if v is not None else None for v in s["value"]]}})       # 成交值用百萬元，檔案小一點
    ok = 0
    for i in range(0, len(rows), 300):
        body = json.dumps(rows[i:i + 300], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(url + "/rest/v1/stock_hist?on_conflict=code", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            ok += 300 if 200 <= r.status < 300 else 0
    print("個股卡片資料上傳 Supabase：%d 檔" % len(rows))


def main():
    if "--no-fetch" not in sys.argv:
        days = sorted(f.stem for f in (DATA / "full" / "tw").glob("*.json"))[-DAYS:]
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        fetch_extra(days)
    dates, stocks = build()
    out = signals(dates, stocks)
    (DATA / "signals_tw.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    have_chips = sum(1 for d in dates if (DATA / "full" / "chips" / ("%s.json" % d)).exists())
    print("連續訊號 %s：%s；板塊 %d；法人資料 %d/%d 天" % (out["date"], "、".join("%s %d" % (k, len(v)) for k, v in out["sig"].items()),
                                                 len(out["sec"]), have_chips, len(dates)))
    if "--no-upload" not in sys.argv:
        upload(dates, stocks)


if __name__ == "__main__":
    main()
