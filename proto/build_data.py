"""原型用：從現有的 data/history（每天排行上的股票）和 data/rotation_tw.json 算出連續訊號與個股卡片的資料 → proto/data.json"""
import glob, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
days = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(str(ROOT / "data/history/tw/*.json")))]
dates = [d["date"] for d in days]
by = []                                   # 每天 {代號: 列}
for d in days:
    m = {r["code"]: r for r in d["rows"]}
    for c, p in (d.get("chip_rank", {}).get("pool") or {}).items():
        m.setdefault(c, dict(p, code=c))
    by.append(m)
last = by[-1]

def series(code, fn):
    return [fn(m[code]) if code in m else None for m in by]

def streak(vals):
    n = 0
    for v in reversed(vals):
        if v: n += 1
        else: break
    return n

sig = {"vol": [], "f": [], "t": [], "ft": []}
for code, r in last.items():
    if r.get("etf"):
        continue
    inst = series(code, lambda x: x.get("inst"))
    ratio = series(code, lambda x: x.get("ratio"))
    tests = {"vol": [x is not None and x >= 1.5 for x in ratio],
             "f": [bool(x) and x[0] > 0 for x in inst],
             "t": [bool(x) and x[1] > 0 for x in inst],
             "ft": [bool(x) and x[0] > 0 and x[1] > 0 for x in inst]}
    for k, ok in tests.items():
        n = streak(ok)
        if n >= 3:
            amt = sum((inst[-1 - i] or [0, 0])[0 if k in ("f", "ft") else 1] for i in range(n)) if k != "vol" else None
            sig[k].append({"code": code, "name": r.get("name"), "ind": r.get("ind"), "close": r.get("close"), "pct": r.get("pct"),
                           "n": n, "dots": [bool(x) for x in ok[-10:]], "amt": amt,
                           "ratio": r.get("ratio"), "value": r.get("value")})
for k in sig:
    sig[k].sort(key=lambda x: (-x["n"], -(x["amt"] or x["value"] or 0)))
rot = json.load(open(ROOT / "data/rotation_tw.json", encoding="utf-8"))
sec = []
for kind in ("ind", "th"):
    for name, s in rot[kind].items():
        if name in ("ETF", "其他"):
            continue
        up = [i > 0 and s[i] > s[i - 1] for i in range(len(s))]
        n = streak(up)
        if n >= 2 and s[-1] >= 0.3:
            sec.append({"kind": kind, "name": name, "n": n, "dots": up[-10:], "share": s[-1], "chg": s[-1] - s[-1 - n]})
sec.sort(key=lambda x: (-x["n"], -x["chg"]))
codes = {x["code"] for k in sig for x in sig[k][:40]} | {"2330", "2454", "1303"}
cards = {}
for c in codes:
    r = last.get(c) or {}
    cards[c] = {"name": r.get("name"), "ind": r.get("ind"), "avg": r.get("avg"),
                "close": series(c, lambda x: x.get("close")), "pct": series(c, lambda x: x.get("pct")),
                "value": series(c, lambda x: x.get("value")), "ratio": series(c, lambda x: x.get("ratio")),
                "inst": series(c, lambda x: x.get("inst"))}
out = {"dates": dates, "sig": {k: v[:40] for k, v in sig.items()}, "sec": sec[:30], "cards": cards}
(ROOT / "proto/data.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print({k: len(v) for k, v in sig.items()}, len(sec), len(cards), (ROOT / "proto/data.json").stat().st_size // 1024, "KB")
print([ (x["name"], x["n"]) for x in sig["f"][:5]], [(x["name"], x["n"]) for x in sec[:5]])
