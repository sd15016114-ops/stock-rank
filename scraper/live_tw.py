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
import json
import math
import os
import sys
import time
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone, time as dtime
from pathlib import Path

TPE = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "live_tw.json"
BASE_DAYS = 20          # 「平常占比」用前 20 個交易日的平均
TOP_N = 8               # 每個板塊列出成交值最大的幾檔
SAMPLE_MIN = 5          # 板塊走勢每 5 分鐘記一點
FLOW_MIN = 5            # 「近 5 分鐘」的資金
OPEN_T, CLOSE_T, END_T = dtime(9, 0), dtime(13, 30), dtime(13, 36)
CHUNK = 500             # Shioaji 一次最多查 500 檔快照
MAX_RELOGIN = 3


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


def aggregate(quotes, names, groups, base, at, phase, past=None, hist=None, themes=None):
    """把每檔的快照整理成網頁用的格式。
    quotes：{代號: {"v": 累積成交值(元), "p": 漲跌幅(%), "c": 成交價, "m": 市場}}
    past：FLOW_MIN 分鐘前的 (板塊成交值, 全市場成交值)，用來算近幾分鐘的資金流向
    hist：{"ts": [...], "ind": {名稱: [...]}, "th": {...}}，每 SAMPLE_MIN 分鐘的累積成交值（百萬元）"""
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
                 "top": [[c, names.get(c, c), quotes[c]["v"], quotes[c].get("p"), quotes[c].get("c")] for c in codes[:TOP_N]]}
            if pv is not None:
                g["f"] = v - pv.get(kind, {}).get(name, 0)          # 近 FLOW_MIN 分鐘流入的成交值
                g["fs"] = round(g["f"] / flow * 100, 3) if flow else 0  # 占這段時間全市場成交值的比重
            if hist and name in hist.get(kind, {}):
                g["h"] = hist[kind][name]
            rows.append(g)
        out[kind] = sorted(rows, key=lambda g: -g["v"])
    mk = {}
    for q in quotes.values():
        mk[q["m"]] = mk.get(q["m"], 0) + q["v"]
    return {"date": at.date().isoformat(), "t": at.isoformat(timespec="seconds"), "phase": phase,
            "total": total, "flow": flow, "flow_min": FLOW_MIN, "markets": mk,
            "count": sum(1 for q in quotes.values() if q["v"] > 0),
            "up": sum(1 for q in quotes.values() if (q.get("p") or 0) > 0),
            "dn": sum(1 for q in quotes.values() if (q.get("p") or 0) < 0),
            "base_days": base.get("days"), "base_total": base.get("total"),
            "ts": (hist or {}).get("ts", []), "ind": out["ind"], "th": out["th"]}


def add_sample(hist, at, gv, kinds_names):
    """每 SAMPLE_MIN 分鐘記一次各板塊的累積成交值（百萬元）；中途才出現的板塊前面補 0"""
    hist["ts"].append(at.strftime("%H:%M"))
    n = len(hist["ts"])
    for kind in ("ind", "th"):
        names = set(hist[kind]) | set(gv[kind]) | set(kinds_names.get(kind, []))
        for name in names:
            seq = hist[kind].setdefault(name, [])
            seq.extend([0] * (n - 1 - len(seq)))
            seq.append(round(gv[kind].get(name, 0) / 1e6))


# ---------------------------------------------------------------- Supabase
def sb_put(payload):
    url, key = os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_SECRET_KEY", "")
    if not url or not key:
        return False
    body = json.dumps([{"id": "tw", "data": payload, "updated_at": payload["t"]}], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
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
    api.login(api_key=key, secret_key=secret, fetch_contract=True, subscribe_trade=False)
    return api


def sj_contracts(api, uni):
    cons, names, miss = [], {}, []
    for code in uni:
        try:
            c = api.Contracts.Stocks[code]
        except Exception:                          # noqa: BLE001
            c = None
        if c is None:
            miss.append(code)
            continue
        cons.append(c)
        names[code] = c.name
    if miss:
        log("永豐查不到 %d 檔：%s" % (len(miss), " ".join(miss[:20])))
    return cons, names


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


def run():
    today = now().date()
    if not trading_day(today):
        log("今天休市，不執行")
        return
    imap, themes = load_imap(), load_themes()
    groups, base, uni = memberships(imap, themes), baseline(imap, themes), universe()
    log("全市場 %d 檔，平常占比用前 %d 個交易日" % (len(uni), base["days"]))
    api, relogin = sj_login(), 0
    cons, names = sj_contracts(api, uni)
    hist, recent, scale, fails, last = {"ts": [], "ind": {}, "th": {}}, deque(maxlen=FLOW_MIN + 3), None, 0, None
    wait_until(datetime.combine(today, OPEN_T, TPE) + timedelta(seconds=20))
    while now().time() < END_T:
        at = now().replace(second=0, microsecond=0)
        try:
            quotes, scale = sj_quotes(api, cons, uni, scale)
            fails = 0
            gv = group_values(quotes, groups)
            total = sum(q["v"] for q in quotes.values())
            past = None
            for (m, g, t) in recent:                 # 找最接近 FLOW_MIN 分鐘前的那一筆
                if (at - m).total_seconds() >= FLOW_MIN * 60 - 5:
                    past = (g, t)
            recent.append((at, gv, total))
            if at.minute % SAMPLE_MIN == 0 or not hist["ts"] or (at.time() >= CLOSE_T and hist["ts"][-1] < "13:30"):
                add_sample(hist, at, gv, {"th": list(themes)})
            phase = "closed" if at.time() >= CLOSE_T else "open"
            last = aggregate(quotes, names, groups, base, at, phase, past, hist, themes)
            save_local(last)
            ok = sb_put(last)
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
    api = sj_login()
    log("登入成功。%s" % usage(api))
    cons = [api.Contracts.Stocks[c] for c in ("2330", "2317", "0050", "6488", "3008")]
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
        log("Supabase 寫入：%s" % ("成功" if sb_put(payload) else "沒有設定"))


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
                q[code] = {"v": int(value * f), "p": round((close / pc - 1) * 100, 2) if pc and close else None, "c": close, "m": mk}
        return q

    day = datetime.fromisoformat(cur["date"]).replace(tzinfo=TPE)
    end_m = 122                                    # 11:02
    hist = {"ts": [], "ind": {}, "th": {}}
    for m in list(range(5, end_m, SAMPLE_MIN)):
        add_sample(hist, day + timedelta(hours=9, minutes=m), group_values(quotes_at(m), groups), {"th": list(themes)})
    at = day + timedelta(hours=9, minutes=end_m)
    pq = quotes_at(end_m - FLOW_MIN)
    past = (group_values(pq, groups), sum(q["v"] for q in pq.values()))
    payload = aggregate(quotes_at(end_m), names, groups, base, at, "open", past, hist, themes)
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
    elif cmd == "mock":
        mock(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        raise SystemExit("用法：live_tw.py run|probe|mock [日期]")
