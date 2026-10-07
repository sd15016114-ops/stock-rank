#!/usr/bin/env python3
"""實測可指定日期的來源目前回什麼（結果寫到 data/probe.log）。只在分支上手動執行。"""
import json
import re
import time
from pathlib import Path

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) twse-ranking-server/1.0"
OUT = []


def say(*a):
    OUT.append(" ".join(str(x) for x in a))
    print(*a)


def get(url):
    r = requests.get(url, timeout=40, headers={"User-Agent": UA, "Accept": "application/json"})
    say("  HTTP", r.status_code, "bytes", len(r.content), "type", r.headers.get("content-type"))
    try:
        return r.json()
    except Exception as e:      # noqa: BLE001
        say("  not json:", e, "|", r.text[:200].replace("\n", " "))
        return None


def show(p, need):
    if not isinstance(p, dict):
        return
    say("  keys", list(p.keys()), "stat", p.get("stat"), "date", p.get("date"), "tables", len(p.get("tables") or []))
    for t in p.get("tables") or []:
        f = [x.strip() for x in t.get("fields") or []]
        if all(n in f for n in need):
            d = t.get("data") or []
            say("  title", t.get("title"), "| date", t.get("date"), "| rows", len(d), "| totalCount", t.get("totalCount"))
            say("  fields", json.dumps(f, ensure_ascii=False))
            for row in d[:2] + [r for r in d if str(r[0]).strip() in ("2330", "6488", "00679B", "0050")][:3]:
                say("  row", json.dumps(row, ensure_ascii=False))
            codes = [str(r[0]).strip() for r in d]
            say("  4碼", sum(bool(re.match(r"^\d{4}$", c)) for c in codes), "00開頭", sum(c.startswith("00") for c in codes), "其他例", [c for c in codes if not re.match(r"^\d{4}$", c) and not c.startswith("00")][:8])


for iso in ("2026-10-06", "2026-09-11", "2026-07-15", "2026-10-04"):
    say("TWSE MI_INDEX", iso)
    show(get("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date=%s&type=ALLBUT0999" % iso.replace("-", "")), ["證券代號", "成交金額"])
    time.sleep(2)
    y, m, d = iso.split("-")
    say("TPEx stk_wn1430", iso)
    show(get("https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&o=json&d=%d/%s/%s&se=EW" % (int(y) - 1911, m, d)), ["代號", "成交金額(元)"])
    time.sleep(2)
    say("TPEx www dailyQuotes", iso)
    show(get("https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date=%s/%s/%s&type=EW&response=json" % (y, m, d)), ["代號", "成交金額(元)"])
    time.sleep(2)
for name, url in (("上市產業", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"), ("上櫃產業", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O")):
    say(name)
    p = get(url)
    if isinstance(p, list):
        say("  count", len(p), "keys", list(p[0].keys())[:12])
        say("  first", json.dumps({k: p[0][k] for k in list(p[0].keys())[:6]}, ensure_ascii=False))
        key = "產業別" if "產業別" in p[0] else "SecuritiesIndustryCode"
        say("  codes", sorted({str(r.get(key)).strip() for r in p}))
Path(__file__).resolve().parent.parent.joinpath("data", "probe.log").write_text("\n".join(OUT) + "\n", encoding="utf-8")
