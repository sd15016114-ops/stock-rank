#!/usr/bin/env python3
"""實測 Polygon 免費方案能不能取得公司圖示（結果寫到 data/probe_logo.log，不會印出金鑰）。只在分支上手動執行。"""
import json
import os
import time
from pathlib import Path

import requests

KEY = os.environ.get("POLYGON_API_KEY", "").strip()
OUT = []


def say(*a):
    line = " ".join(str(x) for x in a).replace(KEY, "***") if KEY else " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def main():
    say("key set:", bool(KEY))
    for t in ("NVDA", "SPY", "MU", "SPCX"):
        r = requests.get("https://api.polygon.io/v3/reference/tickers/%s" % t, headers={"Authorization": "Bearer " + KEY}, timeout=30)
        say(t, "details HTTP", r.status_code)
        res = (r.json() or {}).get("results") or {}
        say("  ", {k: res.get(k) for k in ("name", "type", "homepage_url", "branding")})
        time.sleep(12.5)
        icon = (res.get("branding") or {}).get("icon_url")
        if icon:
            for how in ("header", "param"):
                if how == "header":
                    g = requests.get(icon, headers={"Authorization": "Bearer " + KEY}, timeout=30)
                else:
                    g = requests.get(icon, params={"apiKey": KEY}, timeout=30)
                say("   icon via", how, "HTTP", g.status_code, g.headers.get("content-type"), len(g.content), "bytes")
                time.sleep(12.5)
                if g.ok:
                    break


try:
    main()
finally:
    Path(__file__).resolve().parent.parent.joinpath("data", "probe_logo.log").write_text("\n".join(OUT) + "\n", encoding="utf-8")
