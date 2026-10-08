#!/usr/bin/env python3
"""實測富果金鑰能做什麼（結果寫到 data/probe_fugle.log，不會印出金鑰）。只在分支上手動執行。"""
import json
import os
import time
from pathlib import Path

import requests

KEY = os.environ.get("FUGLE_API_KEY", "").strip()
BASE = "https://api.fugle.tw/marketdata/v1.0/stock"
OUT = []


def say(*a):
    line = " ".join(str(x) for x in a)
    if KEY:
        line = line.replace(KEY, "***")
    OUT.append(line)
    print(line)


def get(path, **params):
    r = requests.get(BASE + path, params=params, headers={"X-API-KEY": KEY}, timeout=30)
    say("GET", path, params, "→ HTTP", r.status_code, "bytes", len(r.content), {k: v for k, v in r.headers.items() if "limit" in k.lower()})
    try:
        return r.json()
    except Exception as e:      # noqa: BLE001
        say("  not json:", e, r.text[:200])
        return {}


def show(p):
    d = p.get("data") if isinstance(p, dict) else None
    say("  ", {k: v for k, v in p.items() if k != "data"} if isinstance(p, dict) else str(p)[:200])
    if isinstance(d, list):
        say("   bars", len(d))
        for b in d[:2] + d[-2:]:
            say("    ", json.dumps(b, ensure_ascii=False))


def main():
    say("key set:", bool(KEY), "length", len(KEY), "time", time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()))
    if not KEY:
        return
    for sym in ("2330", "6488", "0050", "00679B"):
        show(get("/intraday/candles/%s" % sym, timeframe="5"))
        time.sleep(1.2)
    show(get("/intraday/quote/2330"))
    time.sleep(1.2)
    # 歷史 K 線能不能拿到「前一個交易日」的分鐘線（收盤後或隔天補抓用）
    for tf in ("5", "10", "D"):
        show(get("/historical/candles/2330", timeframe=tf, **{"from": "2026-10-07", "to": "2026-10-07"}))
        time.sleep(1.2)
    show(get("/historical/candles/2330", timeframe="5", **{"from": "2026-09-01", "to": "2026-09-01"}))


try:
    main()
finally:
    Path(__file__).resolve().parent.parent.joinpath("data", "probe_fugle.log").write_text("\n".join(OUT) + "\n", encoding="utf-8")
