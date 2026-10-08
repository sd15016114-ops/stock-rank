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
    for day in ("2026-10-06", "2026-10-02"):
        p = get("/v2/aggs/grouped/locale/us/market/stocks/%s" % day, adjusted="true")
        res = p.get("results") or []
        say("  grouped %s:" % day, {k: p.get(k) for k in ("status", "resultsCount", "message")}, "rows", len(res))
        for r in sorted(res, key=lambda r: -(r.get("vw") or r.get("c") or 0) * (r.get("v") or 0))[:3]:
            say("   ", json.dumps(r))
        time.sleep(13)
        for tf in ("5/minute", "30/minute", "1/hour"):
            p = get("/v2/aggs/ticker/NVDA/range/%s/%s/%s" % (tf, day, day), adjusted="true", sort="asc", limit=5000)
            res = p.get("results") or []
            say("  NVDA %s %s:" % (tf, day), {k: p.get(k) for k in ("status", "resultsCount", "message")}, "bars", len(res))
            for r in res[:1] + res[-1:]:
                say("   ", json.dumps(r))
            time.sleep(13)
Path(__file__).resolve().parent.parent.joinpath("data", "probe_polygon.log").write_text("\n".join(OUT) + "\n", encoding="utf-8")
