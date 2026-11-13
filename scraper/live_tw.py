"""盤中資金板塊：交易時間每分鐘抓一次全市場快照（永豐 Shioaji），
算出各產業與概念股的累積成交值，寫進 Supabase 給網頁讀；收盤後把最後一份存進 data/live_tw.json。

用法：
  python scraper/live_tw.py run          盤中一路跑到收盤（GitHub Actions 每個交易日早上啟動）
  python scraper/live_tw.py probe        登入永豐抓幾檔試試，確認金鑰、成交值單位與 Supabase 寫入
  python scraper/live_tw.py mock [日期]  用盤後資料做一份「模擬」的盤中資料，只給網頁預覽用

需要的環境變數（放在 GitHub Secrets，不要寫進程式）：
  SHIOAJI_API_KEY、SHIOAJI_SECRET_KEY    永豐 API 金鑰（只需要行情權限，不需要下單憑證）
  SUPABASE_URL、SUPABASE_SECRET_KEY      Supabase 專案網址與可寫入的金鑰
"""
import inspect
import json
import math
import re
import os
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone, time as dtime
from pathlib import Path

TPE = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "live_tw.json"
BASE_DAYS = 20          # 「平常占比」用前 20 個交易日的平均
TOP_N = 30              # 每個板塊存成交值最大的 30 檔（列表展開看前 8 檔，熱力圖放大後看 30 檔）
SAMPLE_MIN = 5          # 板塊走勢每 5 分鐘記一點
FLOW_MIN = 5            # 「近 5 分鐘」的資金
LOGIN_T, OPEN_T, CLOSE_T, END_T = dtime(8, 50), dtime(9, 0), dtime(13, 30), dtime(13, 36)
CHUNK = 500             # Shioaji 一次最多查 500 檔快照
MAX_RELOGIN = 3
INDEXES = (("tse", "IX0001", "加權指數", "上市"), ("otc", "IX0043", "櫃買指數", "上櫃"))   # 永豐的指數代號
LIMIT_P = 9.5           # 漲跌幅 9.5% 以上算漲停／跌停（台股上限 10%，價格跳動單位會讓實際漲停略低於 10%）


def now():
    return datetime.now(TPE)


def log(msg):
    print("%s  %s" % (now().strftime("%H:%M:%S"), msg), flush=True)


# ---------------------------------------------------------------- 基本資料
def full_files():
    return sorted((DATA / "full" / "tw").glob("*.json"), reverse=True)


def universe():
    """最近一個交易日有成交的上市櫃股票與 ETF：{代號: 市場}"""
    f = full_files()[0]
    j = json.loads(f.read_text(encoding="utf-8"))
    return {r[0]: mk for mk in ("上市", "上櫃") for r in j.get(mk, [])}


def is_etf(code):
    return code.startswith("00")


def load_imap():
    p = DATA / "industry_tw.json"
    return json.loads(p.read_text(encoding="utf-8")).get("map", {}) if p.exists() else {}


def load_themes():
    p = DATA / "themes_tw.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8")).get("themes", {})
    return {name: [str(x).split()[0] for x in items] for name, items in raw.items()}


def ind_of(code, imap):
    return "ETF" if is_etf(code) else imap.get(code, "其他")


def memberships(imap, themes):
    """{代號: (產業, [題材…])}"""
    th = {}
    for name, codes in themes.items():
        for c in codes:
            th.setdefault(c, []).append(name)
    return lambda code: (ind_of(code, imap), th.get(code, []))


def baseline(imap, themes, days=BASE_DAYS):
    """前 N 個交易日各板塊占全市場成交值的平均比重（%）：{"ind": {...}, "th": {...}, "days": n, "total": 平均每日總成交值}"""
    groups = memberships(imap, themes)
    acc = {"ind": {}, "th": {}}
    totals = []
    files = full_files()[:days]
    for f in files:
        j = json.loads(f.read_text(encoding="utf-8"))
        rows = j.get("上市", []) + j.get("上櫃", [])
        total = sum(r[2] for r in rows) or 1
        totals.append(total)
        day = {"ind": {}, "th": {}}
        for code, _close, value in rows:
            ind, ths = groups(code)
            day["ind"][ind] = day["ind"].get(ind, 0) + value
            for t in ths:
                day["th"][t] = day["th"].get(t, 0) + value
        for kind in acc:
            for k, v in day[kind].items():
                acc[kind].setdefault(k, []).append(v / total * 100)
    n = len(files) or 1
    return {"days": len(files), "total": round(sum(totals) / n) if totals else 0,
            "ind": {k: round(sum(v) / n, 3) for k, v in acc["ind"].items()},
            "th": {k: round(sum(v) / n, 3) for k, v in acc["th"].items()}}


def trading_day(d):
    if d.weekday() >= 5:
        return False
    p = DATA / "holidays_tw.json"
    if p.exists():
        years = json.loads(p.read_text(encoding="utf-8")).get("years", {})
        if d.isoformat() in years.get(str(d.year), []):
            return False
    return True


# ---------------------------------------------------------------- 板塊加總
def group_values(quotes, groups):
    """各板塊目前的累積成交值：{"ind": {名稱: 值}, "th": {...}}"""
    out = {"ind": {}, "th": {}}
    for code, q in quotes.items():
        ind, ths = groups(code)
        out["ind"][ind] = out["ind"].get(ind, 0) + q["v"]
        for t in ths:
            out["th"][t] = out["th"].get(t, 0) + q["v"]
    return out


class Flows:
    """資金流入／流出（每分鐘價格方向法）：每檔股票這一分鐘新增的成交值，成交價比上一分鐘高算流入、低算流出，
    價格沒變就沿用這檔上一次的方向。第一次看到的時候（開盤，或程式中途才啟動），先用當天的漲跌決定方向。
    這是用每分鐘快照推估的「主動買／主動賣」，不是逐筆內外盤，所以是近似值。"""

    def __init__(self):
        self.last = {}          # 代號 → (累積成交值, 成交價, 方向)
        self.io = {}            # 代號 → [流入, 流出]（元）

    def update(self, quotes):
        for code, q in quotes.items():
            v, c = q["v"], q.get("c")
            if v <= 0 or c is None:
                continue
            pv, pc, pd = self.last.get(code, (0, None, 0))
            if pc is None:
                p = q.get("p") or 0
                d = 1 if p > 0 else -1 if p < 0 else 0
            else:
                d = 1 if c > pc else -1 if c < pc else pd
            dv = v - pv
            if dv > 0 and d:
                self.io.setdefault(code, [0, 0])[0 if d > 0 else 1] += dv
            self.last[code] = (v, c, d)


def group_net(io, groups):
    """各板塊目前的累積淨流入：{"ind": {名稱: 值}, "th": {...}}"""
    out = {"ind": {}, "th": {}}
    for code, (fi, fo) in io.items():
        ind, ths = groups(code)
        out["ind"][ind] = out["ind"].get(ind, 0) + fi - fo
        for t in ths:
            out["th"][t] = out["th"].get(t, 0) + fi - fo
    return out


STOCK_TOP = 100          # 個股排行：成交值前 100 檔
STOCK_FLOW = 50          # 再加上淨流入、流出、近 5 分鐘流入流出各前 50 檔（重複的只留一份）


def stock_rank(quotes, names, groups, io, past_io=None):
    """盤中個股資金排行：[代號, 名稱, 產業, 累積成交值, 漲跌幅, 成交價, 淨流入, 近 FLOW_MIN 分鐘淨流入]"""
    net = {c: x[0] - x[1] for c, x in (io or {}).items()}
    live = [c for c, q in quotes.items() if q["v"] > 0]
    f5 = {c: net.get(c, 0) - past_io.get(c, 0) for c in live} if past_io is not None else {}
    pick = set(sorted(live, key=lambda c: -quotes[c]["v"])[:STOCK_TOP])
    if net:
        by = sorted(live, key=lambda c: net.get(c, 0))
        pick |= set(by[:STOCK_FLOW]) | set(by[-STOCK_FLOW:])
    if f5:
        by = sorted(live, key=lambda c: f5[c])
        pick |= set(by[:STOCK_FLOW]) | set(by[-STOCK_FLOW:])
    rows = []
    for c in sorted(pick, key=lambda c: -quotes[c]["v"]):
        q = quotes[c]
        rows.append([c, names.get(c, c), groups(c)[0], q["v"], q.get("p"), q.get("c"),
                     net.get(c) if net else None, f5.get(c) if f5 else None])
    return rows


class Indexes:
    """加權、櫃買指數：每分鐘一筆，pts[i] 是 9:00 之後第 i+1 分鐘的收盤點數。
    第一次抓的時候用今天的分K把開盤到現在補齊（排程晚啟動或重新登入也不會缺一段）"""
    def __init__(self):
        self.cons, self.data, self.filled = {}, {}, set()

    def connect(self, api):
        self.cons = {}
        for key, code, _, _ in INDEXES:
            try:
                c = get_contract(api, code)
                if c is not None:
                    self.cons[key] = c
            except Exception as e:                 # noqa: BLE001
                log("拿不到指數 %s：%s" % (code, e))

    def backfill(self, api, key, today):
        try:
            kb = api.kbars(self.cons[key], start=today.isoformat(), end=today.isoformat())
        except Exception as e:                     # noqa: BLE001
            log("指數分K 補資料失敗：%s" % e)
            return
        pts = self.data[key].setdefault("pts", [])
        for ts, c in zip(kb.ts, kb.Close):
            t = datetime.fromtimestamp(ts / 1e9, timezone.utc)        # 永豐的時間戳是台灣時間當成 UTC
            i = (t.hour - 9) * 60 + t.minute - 1
            if 0 <= i < 270:
                while len(pts) <= i:
                    pts.append(None)
                pts[i] = round(float(c), 2)
        self.filled.add(key)

    def update(self, api, at):
        if not self.cons:
            return
        snaps = {s.code: s for s in api.snapshots(list(self.cons.values()))}
        for key, code, name, mk in INDEXES:
            s = snaps.get(code)
            if not s or not s.close:
                continue
            c, chg = float(s.close), float(s.change_price or 0)
            d = self.data.setdefault(key, {"pts": []})
            d.update({"n": name, "mk": mk, "c": round(c, 2), "chg": round(chg, 2), "pct": round(float(s.change_rate or 0), 2),
                      "ref": round(c - chg, 2), "o": round(float(s.open or 0), 2), "h": round(float(s.high or 0), 2),
                      "l": round(float(s.low or 0), 2), "v": int(s.total_amount or 0), "vr": float(getattr(s, "volume_ratio", 0) or 0) or None})
            if key not in self.filled:
                self.backfill(api, key, at.date())
            i = min((at.hour - 9) * 60 + at.minute - 1, 269)
            if i >= 0:
                pts = d["pts"]
                while len(pts) <= i:
                    pts.append(pts[-1] if pts else None)    # 中間漏抓的分鐘先用前一筆補
                pts[i] = d["c"]

    def payload(self):
        return [dict(self.data[k], k=k) for k, _, _, _ in INDEXES if k in self.data]


LAG_HOT = 6            # 最多列幾個熱門板塊
LAG_MIN_P = 1.0        # 板塊平均漲幅至少 1% 才算「在漲」
LAG_GAP = 1.5          # 個股漲幅比板塊平均少 1.5 個百分點以上才算落後
LAG_MIN_V = 3e7        # 個股今天至少成交 3,000 萬，太冷門的不列
LAG_N = 5              # 每個板塊列幾檔
LAG_MIN_FN = 1e7       # 個股自己至少淨流入 1,000 萬


def laggards(out, quotes, names, io):
    """熱門板塊裡還沒漲的：板塊在漲、資金淨流入最多，但個股漲幅明顯落後板塊平均、自己也有資金流入的股票"""
    if not io:
        return []
    hot = [(kind, g) for kind in ("ind", "th") for g in out[kind]
           if g["n"] not in ("ETF", "其他") and (g.get("fn") or 0) > 0 and (g.get("p") or 0) >= LAG_MIN_P]
    hot.sort(key=lambda x: -x[1]["fn"])
    res, seen = [], set()
    for kind, g in hot:
        rows = []
        for c in g["_codes"]:
            q = quotes[c]
            fn = io[c][0] - io[c][1] if c in io else 0
            if is_etf(c) or q.get("p") is None or q["v"] < LAG_MIN_V or fn < LAG_MIN_FN or q["p"] > g["p"] - LAG_GAP:
                continue
            rows.append([c, names.get(c, c), q["p"], q["v"], fn, q.get("c")])
        if not rows:
            continue
        key = tuple(sorted(r[0] for r in rows))
        if key in seen:                            # 概念股常常跟產業的成員一樣，重複的不列兩次
            continue
        seen.add(key)
        rows.sort(key=lambda r: -r[4])
        res.append({"k": kind, "n": g["n"], "p": g["p"], "fn": g["fn"], "up": g["up"], "cnt": g["k"], "rows": rows[:LAG_N]})
        if len(res) >= LAG_HOT:
            break
    return res


def breadth(quotes):
    """漲跌家數（不含 ETF）：上漲、下跌、平盤、漲停、跌停"""
    ps = [q["p"] for c, q in quotes.items() if q.get("p") is not None and not is_etf(c)]
    return {"up": sum(1 for p in ps if p > 0), "dn": sum(1 for p in ps if p < 0), "eq": sum(1 for p in ps if p == 0),
            "lu": sum(1 for p in ps if p >= LIMIT_P), "ld": sum(1 for p in ps if p <= -LIMIT_P)}


def aggregate(quotes, names, groups, base, at, phase, past=None, hist=None, themes=None, io=None, past_net=None, past_io=None, ix=None):
    """把每檔的快照整理成網頁用的格式。
    quotes：{代號: {"v": 累積成交值(元), "p": 漲跌幅(%), "c": 成交價, "m": 市場}}
    past：FLOW_MIN 分鐘前的 (板塊成交值, 全市場成交值)，用來算近幾分鐘的資金流向
    hist：{"ts": [...], "ind": {名稱: [...]}, "th": {...}, "net": {"ind": ..., "th": ...}}，每 SAMPLE_MIN 分鐘的累積成交值與累積淨流入（百萬元）
    io：Flows.io，每檔的累積 [流入, 流出]；past_net：FLOW_MIN 分鐘前各板塊的累積淨流入"""
    io = io or {}
    total = sum(q["v"] for q in quotes.values())
    pv, ptotal = past if past else (None, None)
    flow = total - ptotal if ptotal is not None else None
    members = {"ind": {}, "th": {}}
    for code, q in quotes.items():
        if q["v"] <= 0:
            continue
        ind, ths = groups(code)
        members["ind"].setdefault(ind, []).append(code)
        for t in ths:
            members["th"].setdefault(t, []).append(code)
    for t in (themes or {}):                       # 題材裡的股票都還沒成交時也列出來（成交值 0）
        members["th"].setdefault(t, [])
    out = {}
    for kind, gs in members.items():
        rows = []
        for name, codes in gs.items():
            codes.sort(key=lambda c: -quotes[c]["v"])
            v = sum(quotes[c]["v"] for c in codes)
            w = [(quotes[c]["p"], quotes[c]["v"]) for c in codes if quotes[c].get("p") is not None]
            wsum = sum(x for _, x in w)
            g = {"n": name, "v": v, "k": len(codes),
                 "s": round(v / total * 100, 3) if total else 0,
                 "a": base.get(kind, {}).get(name),
                 "p": round(sum(p * x for p, x in w) / wsum, 2) if wsum else None,
                 "up": sum(1 for c in codes if (quotes[c].get("p") or 0) > 0),
                 "dn": sum(1 for c in codes if (quotes[c].get("p") or 0) < 0),
                 "top": [[c, names.get(c, c), quotes[c]["v"], quotes[c].get("p"), quotes[c].get("c"),
                          io[c][0] - io[c][1] if c in io else 0] for c in codes[:TOP_N]]}
            if io:
                g["fi"] = sum(io[c][0] for c in codes if c in io)       # 累積流入
                g["fo"] = sum(io[c][1] for c in codes if c in io)       # 累積流出
                g["fn"] = g["fi"] - g["fo"]                             # 淨流入
                if past_net is not None:
                    g["fn5"] = g["fn"] - past_net.get(kind, {}).get(name, 0)   # 近 FLOW_MIN 分鐘淨流入
            if pv is not None:
                g["f"] = v - pv.get(kind, {}).get(name, 0)          # 近 FLOW_MIN 分鐘流入的成交值
                g["fs"] = round(g["f"] / flow * 100, 3) if flow else 0  # 占這段時間全市場成交值的比重
            if hist and name in hist.get(kind, {}):
                g["h"] = hist[kind][name]
            if hist and name in hist.get("net", {}).get(kind, {}):
                g["hn"] = hist["net"][kind][name]
            g["_codes"] = codes
            rows.append(g)
        out[kind] = sorted(rows, key=lambda g: -g["v"])
    lag = laggards(out, quotes, names, io)
    for kind in out:
        for g in out[kind]:
            g.pop("_codes", None)
    mk = {}
    for q in quotes.values():
        mk[q["m"]] = mk.get(q["m"], 0) + q["v"]
    return {"date": at.date().isoformat(), "t": at.isoformat(timespec="seconds"), "phase": phase,
            "total": total, "flow": flow, "flow_min": FLOW_MIN, "markets": mk,
            "fi": sum(x[0] for x in io.values()) if io else None, "fo": sum(x[1] for x in io.values()) if io else None,
            "count": sum(1 for q in quotes.values() if q["v"] > 0),
            "up": sum(1 for q in quotes.values() if (q.get("p") or 0) > 0),
            "dn": sum(1 for q in quotes.values() if (q.get("p") or 0) < 0),
            "base_days": base.get("days"), "base_total": base.get("total"),
            "ix": ix or [], "br": breadth(quotes), "lag": lag,
            "ts": (hist or {}).get("ts", []), "ind": out["ind"], "th": out["th"],
            "stocks": stock_rank(quotes, names, groups, io, past_io)}


def add_sample(hist, at, gv, kinds_names, gn=None):
    """每 SAMPLE_MIN 分鐘記一次各板塊的累積成交值與累積淨流入（百萬元）；中途才出現的板塊前面補 0"""
    hist["ts"].append(at.strftime("%H:%M"))
    n = len(hist["ts"])
    net = hist.setdefault("net", {"ind": {}, "th": {}})
    for kind in ("ind", "th"):
        names = set(hist[kind]) | set(gv[kind]) | set(kinds_names.get(kind, []))
        for name in names:
            seq = hist[kind].setdefault(name, [])
            seq.extend([0] * (n - 1 - len(seq)))
            seq.append(round(gv[kind].get(name, 0) / 1e6))
            if gn is not None:
                sn = net[kind].setdefault(name, [])
                sn.extend([0] * (n - 1 - len(sn)))
                sn.append(round(gn[kind].get(name, 0) / 1e6))


# ---------------------------------------------------------------- Supabase
def sb_put(payload, row="tw"):
    url, key = re.sub(r"(/rest/v1)?/*$", "", os.environ.get("SUPABASE_URL", "").strip()), os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not url or not key:
        return False
    body = json.dumps([{"id": row, "data": payload, "updated_at": payload["t"]}], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"apikey": key, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}
    if not key.startswith("sb_"):                  # 舊版的 service_role 金鑰（JWT）要另外放在 Authorization
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url + "/rest/v1/live?on_conflict=id", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return 200 <= r.status < 300


def save_local(payload):
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 永豐 Shioaji
def sj_login():
    import shioaji as sj
    key, secret = os.environ.get("SHIOAJI_API_KEY"), os.environ.get("SHIOAJI_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("未設定 SHIOAJI_API_KEY / SHIOAJI_SECRET_KEY")
    api = sj.Shioaji()
    params = inspect.signature(api.login).parameters        # 新舊版的參數不同，有的才帶
    kw = {k: v for k, v in (("fetch_contract", True), ("subscribe_trade", False)) if k in params}
    api.login(api_key=key, secret_key=secret, **kw)
    return api


def get_contract(api, code):
    """新版用 api.contracts.get(代號)，舊版用 api.Contracts.Stocks[代號]"""
    c = getattr(api, "contracts", None)
    if c is not None and hasattr(c, "get"):
        return c.get(code)
    return api.Contracts.Stocks[code]


def sj_contracts(api, uni):
    cons, names, miss = [], {}, []
    for code in uni:
        try:
            c = get_contract(api, code)
        except Exception:                          # noqa: BLE001
            c = None
        if c is None:
            miss.append(code)
            continue
        cons.append(c)
        names[code] = contract_name(api, c, code)
    if miss:
        log("永豐查不到 %d 檔：%s" % (len(miss), " ".join(miss[:20])))
    return cons, names


def contract_name(api, c, code):
    """新版的合約物件沒有名稱，改從舊版合約表查；都查不到就用代號"""
    n = getattr(c, "name", None)
    if not n:
        try:
            n = api.Contracts.Stocks[code].name
        except Exception:                          # noqa: BLE001
            n = None
    return n or code


def amount_scale(snaps):
    """確認 total_amount 的單位：和「成交張數 × 1000 × 均價」比，回傳要乘的倍數（1 或 1000）"""
    ratios = []
    for s in snaps:
        if s.total_amount and s.total_volume and s.average_price:
            ratios.append(s.total_volume * 1000 * s.average_price / s.total_amount)
    if not ratios:
        return 1
    ratios.sort()
    r = ratios[len(ratios) // 2]
    return 1000 if r > 100 else 1


def sj_quotes(api, cons, uni, scale=None):
    snaps = []
    for i in range(0, len(cons), CHUNK):
        snaps.extend(api.snapshots(cons[i:i + CHUNK]))
    if not snaps:
        raise RuntimeError("快照是空的（可能超過流量上限）")
    if scale is None:
        scale = amount_scale(snaps)
    q = {}
    for s in snaps:
        if s.code in uni:
            q[s.code] = {"v": int(s.total_amount or 0) * scale, "p": round(float(s.change_rate), 2) if s.total_volume else None,
                         "c": float(s.close) if s.close else None, "m": uni[s.code]}
    return q, scale


def usage(api):
    try:
        u = api.usage()
        return "已用流量 %.0f MB／上限 %.0f MB" % (u.bytes / 1e6, u.limit_bytes / 1e6)
    except Exception:                              # noqa: BLE001
        return ""


def wait_until(t):
    while True:
        left = (t - now()).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 30))


def save_quotes(quotes, names):
    """全市場最新價（收盤推播的自選股漲跌用；只留在執行環境，不進 git）"""
    q = {c: [x.get("c"), x.get("p"), names.get(c, c)] for c, x in quotes.items() if x.get("c")}
    (DATA / "live_quotes_tw.json").write_text(json.dumps(q, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def quotes_row(quotes, names, io, past_io, at, phase):
    """自選股頁用：全市場每檔 [價, 漲跌幅, 成交值, 淨流入, 近 5 分鐘淨流入]，鍵是 "s"+代號（數字開頭的鍵 Supabase 會當成陣列索引）"""
    q = {}
    for c, x in quotes.items():
        if x.get("c") is None:
            continue
        net = io[c][0] - io[c][1] if c in io else 0
        f5 = net - past_io.get(c, 0) if past_io is not None else None
        q["s" + c] = [x["c"], x.get("p"), x["v"], net, f5, names.get(c, c)]
    return {"date": at.date().isoformat(), "t": at.isoformat(), "phase": phase, "q": q}


class WatchAlerts:
    """盤中自選股提醒：每檔自選股每種狀況一天最多通知一次。
      急漲急跌：漲跌幅第一次超過 ±5%，漲停／跌停（±9.5%）
      資金急流入／流出：近 5 分鐘淨流入超過 2,000 萬，而且超過這檔平常一天成交值的 1/30
      還沒漲的：出現在熱門板塊落後名單"""
    def __init__(self):
        self.subs, self.loaded, self.sent = [], None, set()
        self.avg = self.avg_value()

    @staticmethod
    def avg_value():
        files = sorted((DATA / "full" / "tw").glob("*.json"))[-20:]
        tot, cnt = {}, {}
        for f in files:
            j = json.loads(f.read_text(encoding="utf-8"))
            for mk in ("上市", "上櫃"):
                for r in j.get(mk, []):
                    tot[r[0]] = tot.get(r[0], 0) + (r[2] or 0)
                    cnt[r[0]] = cnt.get(r[0], 0) + 1
        return {c: tot[c] / cnt[c] for c in tot}

    def refresh(self, at):
        if self.loaded and (at - self.loaded).total_seconds() < 600:
            return
        self.loaded = at
        try:
            import push
            self.subs = [r for r in push.subscribers() if (r.get("prefs") or {}).get("intraday") is not False and (r.get("prefs") or {}).get("watch")]
        except Exception as e:                     # noqa: BLE001
            log("讀取通知訂閱失敗：%s" % e)

    def check(self, at, quotes, names, io, past_io, lag):
        if at.time() < dtime(9, 3) or at.time() >= CLOSE_T:
            return
        self.refresh(at)
        if not self.subs:
            return
        lagset = {r[0]: g["n"] for g in lag or [] for r in g["rows"]}
        events = {}                                # 代號 → [(種類, 文字)]
        codes = {c for r in self.subs for c in r["prefs"]["watch"]}
        for c in codes:
            x = quotes.get(c)
            if not x or x.get("p") is None:
                continue
            p, ev = x["p"], []
            if p >= LIMIT_P:
                ev.append(("lu", "漲停"))
            elif p >= 5:
                ev.append(("u5", "大漲 %+.1f%%" % p))
            if p <= -LIMIT_P:
                ev.append(("ld", "跌停"))
            elif p <= -5:
                ev.append(("d5", "大跌 %.1f%%" % p))
            if past_io is not None and c in io:
                f5 = io[c][0] - io[c][1] - past_io.get(c, 0)
                th = max(2e7, self.avg.get(c, 0) / 30)
                if f5 >= th:
                    ev.append(("fi", "5 分鐘資金流入 %.1f 億" % (f5 / 1e8)))
                elif f5 <= -th:
                    ev.append(("fo", "5 分鐘資金流出 %.1f 億" % (-f5 / 1e8)))
            if c in lagset:
                ev.append(("lag", "%s 族群在漲、這檔還沒漲" % lagset[c]))
            if ev:
                events[c] = ev
        if not events:
            return
        import push

        def make(prefs):
            lines, n = [], 0
            for c in prefs["watch"]:
                for kind, text in events.get(c, []):
                    key = (prefs.get("_ep"), c, kind)
                    if key in self.sent:
                        continue
                    self.sent.add(key)
                    lines.append("%s %s" % (names.get(c, c), text))
                    n += 1
            if not lines:
                return None
            return {"title": "自選股提醒 %s" % at.strftime("%H:%M"), "body": "\n".join(lines[:6]), "url": push.SITE + "watch.html",
                    "tag": "watch-" + at.strftime("%H%M"), "badge": n}
        rows = [dict(r, prefs=dict(r["prefs"], _ep=r["endpoint"])) for r in self.subs]
        try:
            push.send(rows, make)
        except Exception as e:                     # noqa: BLE001
            log("自選股提醒傳送失敗：%s" % e)


def run():
    today = now().date()
    if not trading_day(today):
        log("今天休市，不執行")
        return
    if now().time() >= END_T:
        log("已經收盤，不執行（多排的備用排程）")
        return
    imap, themes = load_imap(), load_themes()
    groups, base, uni = memberships(imap, themes), baseline(imap, themes), universe()
    log("全市場 %d 檔，平常占比用前 %d 個交易日" % (len(uni), base["days"]))
    wait_until(datetime.combine(today, LOGIN_T, TPE))      # 太早啟動時先等著，8:00 永豐流量歸零後再登入
    api, relogin = sj_login(), 0
    cons, names = sj_contracts(api, uni)
    hist, recent, scale, fails, last = {"ts": [], "ind": {}, "th": {}}, deque(maxlen=FLOW_MIN + 3), None, 0, None
    flows, idx = Flows(), Indexes()
    idx.connect(api)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        alerts = WatchAlerts()
    except Exception as e:                         # noqa: BLE001
        log("自選股提醒無法啟用：%s" % e)
        alerts = None
    wait_until(datetime.combine(today, OPEN_T, TPE) + timedelta(seconds=20))
    while now().time() < END_T:
        at = now().replace(second=0, microsecond=0)
        try:
            quotes, scale = sj_quotes(api, cons, uni, scale)
            fails = 0
            gv = group_values(quotes, groups)
            flows.update(quotes)
            gn = group_net(flows.io, groups)
            total = sum(q["v"] for q in quotes.values())
            past = past_net = past_io = None
            for (m, g, t, n, sn) in recent:          # 找最接近 FLOW_MIN 分鐘前的那一筆
                if (at - m).total_seconds() >= FLOW_MIN * 60 - 5:
                    past, past_net, past_io = (g, t), n, sn
            recent.append((at, gv, total, gn, {c: x[0] - x[1] for c, x in flows.io.items()}))
            if at.minute % SAMPLE_MIN == 0 or not hist["ts"] or (at.time() >= CLOSE_T and hist["ts"][-1] < "13:30"):
                add_sample(hist, at, gv, {"th": list(themes)}, gn)
            phase = "closed" if at.time() >= CLOSE_T else "open"
            try:
                idx.update(api, at)
            except Exception as e:                 # noqa: BLE001
                log("指數這一輪沒抓到：%s" % e)
            last = aggregate(quotes, names, groups, base, at, phase, past, hist, themes, flows.io, past_net, past_io, idx.payload())
            save_local(last)
            save_quotes(quotes, names)
            ok = sb_put(last)
            try:
                sb_put(quotes_row(quotes, names, flows.io, past_io, at, phase), row="q")
            except Exception as e:                 # noqa: BLE001
                log("自選股報價沒寫入：%s" % e)
            if alerts:
                alerts.check(at, quotes, names, flows.io, past_io, last.get("lag"))
            log("%s 全市場 %.0f 億%s %s" % (phase, total / 1e8, "" if ok else "（未寫入 Supabase）", usage(api) if at.minute % 30 == 0 else ""))
        except Exception as e:                     # noqa: BLE001
            fails += 1
            log("這一輪失敗（第 %d 次）：%s" % (fails, e))
            if fails >= 3 and relogin < MAX_RELOGIN:
                relogin += 1
                log("重新登入（第 %d 次）" % relogin)
                try:
                    api.logout()
                except Exception:                  # noqa: BLE001
                    pass
                time.sleep(30)
                api = sj_login()
                cons, names = sj_contracts(api, uni)
                idx.connect(api)
                fails = 0
        wait_until(at + timedelta(seconds=60 + 3))
    try:
        api.logout()
    except Exception:                              # noqa: BLE001
        pass
    log("收盤，結束" if last else "今天沒有取得任何資料")
    if not last:
        sys.exit(1)


def probe():
    """登入、抓 5 檔看看欄位與單位，再試寫一次 Supabase。"""
    import shioaji as sj
    api = sj.Shioaji()
    log("shioaji 版本 %s" % getattr(sj, "__version__", "?"))
    log("login 參數：%s" % inspect.signature(api.login))
    log("snapshots 參數：%s" % inspect.signature(api.snapshots))
    api = sj_login()
    log("登入成功。%s" % usage(api))
    for attr in ("contracts", "Contracts"):
        try:
            log("api.%s：%s" % (attr, type(getattr(api, attr)).__name__))
        except Exception as e:                     # noqa: BLE001
            log("api.%s 讀取失敗：%s" % (attr, e))
    cons = [get_contract(api, c) for c in ("2330", "2317", "0050", "6488", "3008")]
    log("合約欄位：%s" % [a for a in dir(cons[0]) if not a.startswith("_")])
    log("名稱：%s" % [contract_name(api, c, c.code) for c in cons])
    snaps = api.snapshots(cons)
    for s in snaps:
        log("%s close=%s change_rate=%s total_volume=%s average_price=%s total_amount=%s" % (
            s.code, s.close, s.change_rate, s.total_volume, s.average_price, s.total_amount))
    log("成交值單位倍數：%d" % amount_scale(snaps))
    uni = universe()
    t0 = time.time()
    all_cons, _ = sj_contracts(api, uni)
    quotes, scale = sj_quotes(api, all_cons, uni)
    log("全市場 %d 檔快照花了 %.1f 秒，合計 %.0f 億。%s" % (len(quotes), time.time() - t0, sum(q["v"] for q in quotes.values()) / 1e8, usage(api)))
    api.logout()
    if os.environ.get("SUPABASE_URL"):
        imap, themes = load_imap(), load_themes()
        groups = memberships(imap, themes)
        payload = aggregate(quotes, {}, groups, baseline(imap, themes), now(), "probe", themes=themes)
        log("Supabase 寫入：%s" % ("成功" if sb_put(payload, "probe") else "沒有設定"))   # 寫到另一列，不蓋掉網頁正在用的資料
        pub = os.environ.get("SUPABASE_PUBLIC_KEY")
        if pub:                                    # 用網頁上的公開金鑰讀回來，確認網頁讀得到、也確認公開金鑰寫不進去
            base = re.sub(r"(/rest/v1)?/*$", "", os.environ["SUPABASE_URL"].strip())
            req = urllib.request.Request(base + "/rest/v1/live?id=eq.probe&select=updated_at,data->>total", headers={"apikey": pub})
            with urllib.request.urlopen(req, timeout=20) as r:
                log("公開金鑰讀回：%s" % r.read().decode("utf-8")[:200])
            try:
                bad = urllib.request.Request(base + "/rest/v1/live", data=b'[{"id":"hack","data":{}}]', method="POST",
                                             headers={"apikey": pub, "Content-Type": "application/json"})
                urllib.request.urlopen(bad, timeout=20)
                log("⚠ 公開金鑰竟然可以寫入，權限要檢查")
            except urllib.error.HTTPError as e:
                log("公開金鑰寫入被擋下（%d），權限正確" % e.code)


def probe_index():
    """試抓加權指數、櫃買指數：合約怎麼拿、快照有哪些欄位、分K能不能補今天的走勢"""
    api = sj_login()
    log("登入成功。%s" % usage(api))
    cc = api.contracts
    log("api.contracts 型別 %s，方法：%s" % (type(cc).__name__, [a for a in dir(cc) if not a.startswith("_")]))
    for name in [a for a in dir(cc) if not a.startswith("_")]:
        try:
            v = getattr(cc, name)
            if callable(v):
                log("  %s%s  %s" % (name, inspect.signature(v) if not isinstance(v, type) else "", (v.__doc__ or "").strip()[:200]))
            else:
                log("  %s = %s" % (name, str(v)[:200]))
        except Exception as e:                     # noqa: BLE001
            log("  %s 讀不到：%s" % (name, e))
    try:
        ix = api.Contracts.Indexs
        log("Indexs 型別 %s：%s" % (type(ix).__name__, [a for a in dir(ix) if not a.startswith("_")]))
        for ex in ("TSE", "OTC"):
            g = getattr(ix, ex)
            log("%s 型別 %s：%s" % (ex, type(g).__name__, [a for a in dir(g) if not a.startswith("_")][:40]))
            try:
                items = list(g)[:5]
                log("  前 5 個：%s" % items)
            except Exception as e:                 # noqa: BLE001
                log("  無法列舉：%s" % e)
    except Exception as e:                         # noqa: BLE001
        log("Indexs 失敗：%r" % e)
    found = {}
    tries = []
    for code in ("001", "101", "TSE001", "OTC101", "IX0001", "IX0043"):
        tries.append(("contracts.get(%s)" % code, lambda c=code: cc.get(c)))
        for kw in ("security_type", "exchange"):
            for val in ("IND", "TSE", "OTC"):
                tries.append(("contracts.get(%s,%s=%s)" % (code, kw, val), lambda c=code, k=kw, v=val: cc.get(c, **{k: v})))
    for label, fn in tries:
        try:
            c = fn()
            if c is not None:
                log("%s → %s" % (label, c))
                found.setdefault(getattr(c, "code", label) + str(getattr(c, "exchange", "")), c)
        except Exception as e:                     # noqa: BLE001
            if "unexpected keyword" not in str(e):
                log("%s 失敗：%s" % (label, str(e)[:100]))
    cons = list(found.values())[:4]
    if cons:
        for s in api.snapshots(cons):
            log("快照：%s" % {k: getattr(s, k) for k in dir(s) if not k.startswith("_") and not callable(getattr(s, k))})
        try:
            today = now().date().isoformat()
            kb = api.kbars(cons[0], start=today, end=today)
            log("分K 筆數 %d；前 3 筆 ts=%s close=%s；最後 ts=%s close=%s" % (len(kb.Close), kb.ts[:3], kb.Close[:3], kb.ts[-1:], kb.Close[-1:]))
        except Exception as e:                     # noqa: BLE001
            log("分K 失敗：%s" % e)
    log(usage(api))
    api.logout()


# ---------------------------------------------------------------- 資金輪動
ROTATION_DAYS = 20


def rotation(days=ROTATION_DAYS):
    """最近 N 個交易日各產業、概念股占全市場成交值的比重（%），給首頁的資金輪動圖用 → data/rotation_tw.json"""
    imap, themes = load_imap(), load_themes()
    groups = memberships(imap, themes)
    files = list(reversed(full_files()[:days]))
    out = {"dates": [], "totals": [], "ind": {}, "th": {}}
    for i, f in enumerate(files):
        j = json.loads(f.read_text(encoding="utf-8"))
        rows = j.get("上市", []) + j.get("上櫃", [])
        total = sum(r[2] for r in rows) or 1
        day = {"ind": {}, "th": {}}
        for code, _close, value in rows:
            ind, ths = groups(code)
            day["ind"][ind] = day["ind"].get(ind, 0) + value
            for t in ths:
                day["th"][t] = day["th"].get(t, 0) + value
        out["dates"].append(j["date"])
        out["totals"].append(total)
        for kind in ("ind", "th"):
            for name in set(out[kind]) | set(day[kind]) | (set(themes) if kind == "th" else set()):
                seq = out[kind].setdefault(name, [0] * i)
                seq.append(round(day[kind].get(name, 0) / total * 100, 3))
    out["updated"] = now().isoformat(timespec="seconds")
    p = DATA / "rotation_tw.json"
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("資金輪動：%s～%s，%d 天" % (out["dates"][0], out["dates"][-1], len(out["dates"])))


# ---------------------------------------------------------------- 預覽用的模擬資料
def mock(date=None):
    """拿某天的盤後全市場資料，假裝現在是盤中 11:02，產生一份模擬的盤中資料。只給網頁預覽，不會上線。"""
    files = full_files()
    idx = 0
    if date:
        idx = [f.stem for f in files].index(date)
    cur = json.loads(files[idx].read_text(encoding="utf-8"))
    prev = json.loads(files[idx + 1].read_text(encoding="utf-8"))
    pclose = {r[0]: r[1] for mk in ("上市", "上櫃") for r in prev[mk]}
    names = {}
    for f in sorted((DATA / "history" / "tw").glob("*.json")):
        for r in json.loads(f.read_text(encoding="utf-8")).get("rows", []):
            names[r["code"]] = r["name"]
    for items in json.loads((DATA / "themes_tw.json").read_text(encoding="utf-8"))["themes"].values():
        for x in items:
            c, _, n = x.partition(" ")
            names.setdefault(c, n)
    imap, themes = load_imap(), load_themes()
    groups = memberships(imap, themes)
    base = baseline(imap, themes)

    def frac(m):                                   # 一天裡累積成交值的比例（開盤、收盤量大的 U 形）
        x = m / 270
        return (0.30 * (1 - (1 - x) ** 4) + 0.55 * x + 0.15 * x ** 6) if m > 0 else 0

    def wiggle(code, m):                           # 每檔股票成交的快慢略有不同
        h = sum(ord(ch) for ch in code)
        return 1 + 0.25 * math.sin(m / 37 + h)

    def quotes_at(m):
        q = {}
        for mk in ("上市", "上櫃"):
            for code, close, value in cur[mk]:
                f = min(1, frac(m) * wiggle(code, m)) if m < 270 else 1
                pc = pclose.get(code)
                h = sum(ord(ch) for ch in code)
                c = round(pc + (close - pc) * min(1, m / 200) + pc * 0.006 * math.sin(m / 9 + h), 2) if pc and close else close
                q[code] = {"v": int(value * f), "p": round((c / pc - 1) * 100, 2) if pc and c else None, "c": c, "m": mk}
        return q

    day = datetime.fromisoformat(cur["date"]).replace(tzinfo=TPE)
    end_m = 122                                    # 11:02
    hist = {"ts": [], "ind": {}, "th": {}}
    flows, past, past_net, past_io = Flows(), None, None, None
    for m in range(1, end_m + 1):                  # 每分鐘跑一次，跟正式執行一樣累積流入流出
        q = quotes_at(m)
        flows.update(q)
        if m == end_m - FLOW_MIN:
            past = (group_values(q, groups), sum(x["v"] for x in q.values()))
            past_net = group_net(flows.io, groups)
            past_io = {c: x[0] - x[1] for c, x in flows.io.items()}
        if m % SAMPLE_MIN == 0 and m < end_m:
            add_sample(hist, day + timedelta(hours=9, minutes=m), group_values(q, groups), {"th": list(themes)}, group_net(flows.io, groups))
    at = day + timedelta(hours=9, minutes=end_m)
    ix = []
    for key, code, name, mk in INDEXES:                # 假的指數走勢：前一天收盤附近上下波動
        ref = 23000.0 if key == "tse" else 260.0
        pts = [round(ref * (1 + 0.004 * math.sin(m / 23) + 0.006 * math.sin(m / 61 + (1 if key == "otc" else 0)) + 0.002 * m / 120), 2) for m in range(1, end_m + 1)]
        c = pts[-1]
        ix.append({"k": key, "n": name, "mk": mk, "c": c, "chg": round(c - ref, 2), "pct": round((c / ref - 1) * 100, 2), "ref": ref,
                   "o": pts[0], "h": max(pts), "l": min(pts), "v": int(sum(x["v"] for x in quotes_at(end_m).values() if x["m"] == mk)), "vr": 1.1, "pts": pts})
    payload = aggregate(quotes_at(end_m), names, groups, base, at, "open", past, hist, themes, flows.io, past_net, past_io, ix)
    payload["mock"] = True
    out = DATA / "live_tw_mock.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("已產生 %s（%d KB）" % (out.relative_to(ROOT), out.stat().st_size // 1024))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        run()
    elif cmd == "probe":
        probe()
    elif cmd == "probe-index":
        probe_index()
    elif cmd == "rotation":
        rotation()
    elif cmd == "mock":
        mock(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        raise SystemExit("用法：live_tw.py run|probe|mock [日期]")
