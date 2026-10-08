#!/usr/bin/env python3
"""實測各資料來源目前的回應格式，結果寫到 data/probe.log（只在分支上手動執行）。"""
import json
import sys
import time
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "probe.log"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Accept-Language": "zh-TW,zh;q=0.9"}
URLS = [
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date=20261006&type=ALLBUT0999",
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date=20261007&type=ALLBUT0999",
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date=20260911&type=ALLBUT0999",
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date=20261004&type=ALLBUT0999",
    "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&date=20260715&type=ALLBUT0999",
    "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&o=json&d=115/10/06&se=EW",
    "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&o=json&d=115/09/11&se=EW",
    "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&o=json&d=115/10/04&se=EW",
    "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2026/10/06&type=EW&response=json",
    "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2026/10/04&type=EW&response=json",
    "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
    "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
]


def describe(j, depth=0):
    out = []
    if isinstance(j, dict):
        out.append("keys=%s" % list(j.keys())[:20])
        for k in ("stat", "date", "reportDate", "totalCount", "iTotalRecords"):
            if k in j:
                out.append("%s=%r" % (k, j[k]))
        for i, t in enumerate(j.get("tables") or []):
            if isinstance(t, dict):
                data = t.get("data") or []
                out.append("table[%d] title=%r date=%r fields=%s rows=%d" % (i, t.get("title"), t.get("date"), t.get("fields"), len(data)))
                big = [r for r in data if isinstance(r, list) and r and str(r[0]).strip() in ("2330", "0050", "6488", "00679B", "8069")]
                for r in (data[:2] + big[:3]):
                    out.append("    %s" % json.dumps(r, ensure_ascii=False))
        if "aaData" in j:
            out.append("aaData rows=%d first=%s" % (len(j["aaData"]), json.dumps(j["aaData"][:2], ensure_ascii=False)))
    elif isinstance(j, list):
        out.append("list len=%d" % len(j))
        for r in j[:2]:
            out.append("    %s" % json.dumps(r, ensure_ascii=False))
        if j and isinstance(j[0], dict):
            for key in ("產業別", "SecuritiesIndustryCode"):
                if key in j[0]:
                    out.append("    %s values=%s" % (key, sorted({str(r.get(key)) for r in j})))
    return out


lines = []
for u in URLS:
    lines.append("== " + u)
    try:
        r = requests.get(u, headers=UA, timeout=40)
        lines.append("HTTP %d, %d bytes, type=%s" % (r.status_code, len(r.content), r.headers.get("content-type")))
        try:
            lines += describe(r.json())
        except Exception as e:      # noqa: BLE001
            lines.append("not json (%s): %r" % (e, r.text[:300]))
    except Exception as e:          # noqa: BLE001
        lines.append("ERROR %s" % e)
    time.sleep(3)
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
sys.exit(0)
