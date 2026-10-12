#!/usr/bin/env python3
"""實測台股籌碼來源（三大法人、融資融券）的格式，結果寫到 data/probe_chips.log。只在分支上手動執行。"""
import json
import time
from pathlib import Path

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
OUT = []


def say(*a):
    OUT.append(" ".join(str(x) for x in a))
    print(*a)


def get(url):
    r = requests.get(url, timeout=40, headers={"User-Agent": UA, "Accept": "application/json"})
    say("GET", url, "→ HTTP", r.status_code, "bytes", len(r.content), r.headers.get("content-type"))
    try:
        return r.json()
    except Exception as e:      # noqa: BLE001
        say("  not json:", e, r.text[:200].replace("\n", " "))
        return None


def show(p):
    if not isinstance(p, dict):
        say("  type", type(p).__name__)
        return
    say("  keys", list(p.keys()), {k: p.get(k) for k in ("stat", "date", "title", "totalCount") if k in p})
    tables = p.get("tables") or ([p] if p.get("fields") else [])
    for i, t in enumerate(tables):
        d = t.get("data") or []
        say("  table[%d] title=%r date=%r rows=%d" % (i, t.get("title"), t.get("date"), len(d)))
        say("    fields", json.dumps(t.get("fields"), ensure_ascii=False))
        if t.get("groups"):
            say("    groups", json.dumps(t.get("groups"), ensure_ascii=False))
        for row in d[:2] + [r for r in d if str(r[0]).strip() in ("2330", "6488", "0050")][:3]:
            say("    row", json.dumps(row, ensure_ascii=False))


for d in ("2026-10-08", "2026-10-09"):
    y, m, dd = d.split("-")
    roc = "%d/%s/%s" % (int(y) - 1911, m, dd)
    for url in ("https://www.twse.com.tw/rwd/zh/fund/T86?date=%s%s%s&selectType=ALLBUT0999&response=json" % (y, m, dd),
                "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date=%s%s%s&selectType=ALL&response=json" % (y, m, dd),
                "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d=%s" % roc,
                "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date=%s/%s/%s&response=json" % (y, m, dd),
                "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&o=json&d=%s" % roc,
                "https://www.tpex.org.tw/www/zh-tw/margin/balance?date=%s/%s/%s&response=json" % (y, m, dd)):
        try:
            show(get(url))
        except Exception as e:  # noqa: BLE001
            say("  ERROR", e)
        time.sleep(4)
Path(__file__).resolve().parent.parent.joinpath("data", "probe_chips.log").write_text("\n".join(OUT) + "\n", encoding="utf-8")
