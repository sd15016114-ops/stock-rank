#!/usr/bin/env python3
"""實測 Polygon 金鑰能做什麼（結果寫到 data/probe_polygon.log，不會印出金鑰）。只在分支上手動執行。"""
import json
import os
import sys
import time
from pathlib import Path

import requests

KEY = os.environ.get("POLYGON_API_KEY", "").strip()
OUT = []


def say(*a):
    line = " ".join(str(x) for x in a)
    if KEY:
        line = line.replace(KEY, "***")
    OUT.append(line)
    print(line)


def get(path, **params):
    r = requests.get("https://api.polygon.io" + path, params=params, headers={"Authorization": "Bearer " + KEY}, timeout=40)
    say("GET", path, params, "→ HTTP", r.status_code, "bytes", len(r.content))
    try:
        return r.json()
    except Exception as e:      # noqa: BLE001
        say("  not json:", e, r.text[:200])
        return {}


say("key set:", bool(KEY), "length", len(KEY))
if KEY:
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-10-07"
    p = get("/v2/aggs/grouped/locale/us/market/stocks/%s" % day, adjusted="true")
    res = p.get("results") or []
    say("  grouped:", {k: p.get(k) for k in ("status", "resultsCount", "queryCount", "error", "message")}, "rows", len(res))
    for r in sorted(res, key=lambda r: -(r.get("vw") or r.get("c") or 0) * (r.get("v") or 0))[:5]:
        say("   ", json.dumps(r))
    time.sleep(13)
    for sym in ("NVDA", "TSM"):
        p = get("/v2/aggs/ticker/%s/range/5/minute/%s/%s" % (sym, day, day), adjusted="true", sort="asc", limit=5000)
        res = p.get("results") or []
        say("  minute %s:" % sym, {k: p.get(k) for k in ("status", "resultsCount", "error", "message")}, "bars", len(res))
        for r in res[:2] + res[-2:]:
            say("   ", json.dumps(r))
        time.sleep(13)
    p = get("/v3/reference/tickers", market="stocks", type="ETF", active="true", limit=5)
    say("  tickers:", {k: p.get(k) for k in ("status", "count", "error", "message")}, [r.get("ticker") for r in p.get("results") or []])
Path(__file__).resolve().parent.parent.joinpath("data", "probe_polygon.log").write_text("\n".join(OUT) + "\n", encoding="utf-8")
