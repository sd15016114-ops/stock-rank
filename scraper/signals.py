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


def jload(p, default=None):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


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
        close, value, pct, ratio, f, t = [], [], [], [], [], []
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
        prior = [days[j][1][code][1] for j in range(max(0, len(days) - 1 - AVG_DAYS), len(days) - 1) if code in days[j][1]]
        listed = sum(1 for _, m in days if code in m)
        stocks[code] = {"listed": listed, "name": names.get(code, code), "ind": "ETF" if code.startswith("00") else imap.get(code, ""),
                        "close": close, "value": value, "pct": pct, "ratio": ratio, "f": f, "t": t,
                        "avg": round(sum(prior) / len(prior)) if prior else None}
    return dates, stocks


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
                           "n": n, "dots": ok[-10:], "amt": amt, "amt_t": sum(s["t"][-n:]) if k == "ft" else None,
                           "value": s["value"][-1], "ratio": s["ratio"][-1]})
    for k in out:
        out[k].sort(key=lambda x: (-x["n"], -(x["amt"] if x["amt"] is not None else x["value"] or 0)))
        out[k] = out[k][:TOP]
    rot = jload(DATA / "rotation_tw.json", {})
    sec = []
    for kind in ("ind", "th"):
        for name, sh in (rot.get(kind) or {}).items():
            if name in ("ETF", "其他") or len(sh) < 3:
                continue
            up = [i > 0 and sh[i] > sh[i - 1] for i in range(len(sh))]
            n = streak(up)
            if n >= 2 and sh[-1] >= 0.3:
                sec.append({"kind": kind, "name": name, "n": n, "dots": up[-10:], "share": sh[-1], "chg": round(sh[-1] - sh[-1 - n], 3)})
    sec.sort(key=lambda x: (-x["n"], -x["chg"]))
    chip_days = sum(1 for d in dates if (DATA / "full" / "chips" / ("%s.json" % d)).exists())
    return {"date": dates[-1], "updated": datetime.now(TPE).isoformat(timespec="seconds"), "chip_days": chip_days,
            "rot_date": (rot.get("dates") or [None])[-1], "sig": out, "sec": sec[:40]}


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
            "value": [round(v / 1e6) if v is not None else None for v in s["value"]]}})       # 成交值用百萬元，檔案小一點
    ok = 0
    for i in range(0, len(rows), 300):
        body = json.dumps(rows[i:i + 300], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(url + "/rest/v1/stock_hist?on_conflict=code", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            ok += 300 if 200 <= r.status < 300 else 0
    print("個股卡片資料上傳 Supabase：%d 檔" % len(rows))


def main():
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
