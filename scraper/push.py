"""推播通知（Web Push）。訂閱存在 Supabase 的 push_subs 表，由網頁的「通知」設定寫入。

  python scraper/push.py pubkey     印出公開金鑰（網頁訂閱時要用）
  python scraper/push.py test       傳一則測試通知給所有訂閱
  python scraper/push.py close      收盤摘要（盤中資金跑完後）
  python scraper/push.py signals    盤後訊號（法人資料齊全後，每天只傳一次）

推播用的 VAPID 金鑰不另外存：由 SUPABASE_SECRET_KEY 推導出來（同一把 secret 永遠得到同一把金鑰）。
如果之後換了 Supabase 的 secret key，金鑰會跟著變，大家要在網頁上重新開一次通知。"""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = "https://sd15016114-ops.github.io/stock-rank/"
TPE = timezone(timedelta(hours=8))
STATE = DATA / "push_state.json"


def jload(p, default=None):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


# ---------------------------------------------------------------- 金鑰與 Supabase
def secret():
    k = os.environ.get("SUPABASE_SECRET_KEY", "").strip()
    if not k:
        sys.exit("沒有 SUPABASE_SECRET_KEY")
    return k


def vapid_key():
    from cryptography.hazmat.primitives.asymmetric import ec
    n = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551      # P-256 的階
    d = int.from_bytes(hmac.new(secret().encode(), b"stock-rank-vapid-v1", hashlib.sha256).digest(), "big") % (n - 1) + 1
    return ec.derive_private_key(d, ec.SECP256R1())


def pubkey():
    from cryptography.hazmat.primitives import serialization
    raw = vapid_key().public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def sb(path, method="GET", body=None):
    url = re.sub(r"(/rest/v1)?/*$", "", os.environ.get("SUPABASE_URL", "").strip()) + "/rest/v1/" + path
    key = secret()
    h = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_"):
        h["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode()
        return json.loads(t) if t else None


def subscribers():
    return sb("push_subs?select=endpoint,sub,prefs") or []


def send(rows, make):
    """make(prefs) 回傳 None（不傳）或 {title, body, url, tag}"""
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid01
    v = Vapid01(private_key=vapid_key())
    ok = gone = 0
    for r in rows:
        msg = make(r.get("prefs") or {})
        if not msg:
            continue
        try:
            webpush(r["sub"], json.dumps(msg, ensure_ascii=False), vapid_private_key=v,
                    vapid_claims={"sub": "https://sd15016114-ops.github.io"}, ttl=6 * 3600)
            ok += 1
        except WebPushException as e:
            code = getattr(e.response, "status_code", None)
            if code in (404, 410):                 # 使用者取消了，或換了瀏覽器
                sb("push_subs?endpoint=eq." + urllib.request.quote(r["endpoint"], safe=""), "DELETE")
                gone += 1
            else:
                print("傳送失敗：%s" % str(e)[:200])
    print("推播：傳出 %d 則，清掉失效訂閱 %d 個（共 %d 個訂閱）" % (ok, gone, len(rows)))


# ---------------------------------------------------------------- 內容
def yi(v):
    v = abs(v) / 1e8
    return "%.0f" % v if v >= 100 else "%.1f" % v


def sgn(p):
    return ("+" if p > 0 else "") + "%.2f%%" % p


def close_msg():
    live = jload(DATA / "live_tw.json")
    today = datetime.now(TPE).date().isoformat()
    if not live or live.get("date") != today:
        print("今天沒有盤中資料，不傳收盤摘要")
        return None
    quotes = jload(DATA / "live_quotes_tw.json", {})
    ix = {x["k"]: x for x in live.get("ix") or []}
    t = ix.get("tse")
    title = "收盤｜加權 %s %s" % ("{:,.0f}".format(t["c"]), sgn(t["pct"])) if t else "今日收盤"
    hot = sorted([g for g in live.get("ind", []) if g["n"] not in ("ETF", "其他") and (g.get("fn") or 0) > 0], key=lambda g: -g["fn"])[:3]
    parts = []
    if hot:
        parts.append("資金最熱：" + "、".join("%s %s 億" % (g["n"], yi(g["fn"])) for g in hot))
    br = live.get("br")
    if br:
        parts.append("上漲 %d、下跌 %d 家" % (br["up"], br["dn"]))
    base = "；".join(parts)

    def make(prefs):
        if prefs.get("close") is False:
            return None
        body = base
        watch = [c for c in prefs.get("watch") or [] if c in quotes and quotes[c][1] is not None]
        if watch:
            body += "\n自選：" + "、".join("%s %s" % (quotes[c][2], sgn(quotes[c][1])) for c in watch[:8])
        return {"title": title, "body": body, "url": SITE, "tag": "close-" + today}
    return make


def signals_msg():
    sig = jload(DATA / "signals_tw.json")
    if not sig:
        return None
    d = sig["date"]
    if not (DATA / "full" / "chips" / ("%s.json" % d)).exists():
        print("%s 的法人資料還沒齊，晚一點再傳" % d)
        return None
    st = jload(STATE, {})
    if st.get("signals") == d:
        print("%s 的盤後訊號已經傳過" % d)
        return None
    S = sig["sig"]
    new = {k: [x for x in S.get(k, []) if x.get("n") == 3] for k in ("vol", "f", "t", "ft")}   # 剛好滿 3 天＝今天新上榜
    lab = {"vol": "連續放量", "f": "外資連買", "t": "投信連買", "ft": "外資投信同步買"}
    lines = ["%s 新上榜 %d 檔" % (lab[k], len(v)) for k, v in new.items() if v]
    if S.get("sbl"):
        lines.append("借券賣出暴增：" + "、".join(x["name"] for x in S["sbl"][:4]) + ("等 %d 檔" % len(S["sbl"]) if len(S["sbl"]) > 4 else ""))
    base = "；".join(lines) or "今天沒有新的訊號"
    m, dd = int(d[5:7]), int(d[8:10])
    hits = {}                                       # 代號 → 這檔今天出現在哪些名單

    def note(code, text):
        hits.setdefault(code, []).append(text)
    for x in S.get("vol", []):
        note(x["code"], "連 %d 天放量" % x["n"])
    for x in S.get("f", []):
        note(x["code"], "外資連 %d 買" % x["n"])
    for x in S.get("t", []):
        note(x["code"], "投信連 %d 買" % x["n"])
    for x in S.get("sbl", []):
        note(x["code"], "借券賣出暴增")
    for x in S.get("dt", [])[:20]:
        note(x["code"], "當沖 %.0f%%" % x["r"])
    names = {x["code"]: x["name"] for k in S for x in S[k]}

    def make(prefs):
        if prefs.get("signals") is False:
            return None
        mine = [c for c in prefs.get("watch") or [] if c in hits]
        body = base
        if mine:
            body = "自選：" + "；".join("%s %s" % (names.get(c, c), "、".join(hits[c])) for c in mine[:6]) + "\n" + base
        return {"title": "盤後訊號 %d/%d" % (m, dd), "body": body, "url": SITE + "signals.html", "tag": "signals-" + d}

    make.done = lambda: STATE.write_text(json.dumps(dict(st, signals=d)) + "\n", encoding="utf-8")
    return make


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    if cmd == "pubkey":
        print("推播公開金鑰：" + pubkey())
        return
    make = {"close": close_msg, "signals": signals_msg,
            "test": lambda: (lambda prefs: {"title": "通知測試成功", "body": "之後收盤摘要和盤後訊號會從這裡傳給你。", "url": SITE, "tag": "test"})}[cmd]()
    if not make:
        return
    rows = subscribers()
    if not rows:
        print("目前沒有人開通知")
    else:
        send(rows, make)
    if hasattr(make, "done"):
        make.done()


if __name__ == "__main__":
    main()
