"""盤中資金板塊的離線測試：python3 tests/test_live.py"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
import live_tw as L  # noqa: E402

imap = {"2330": "半導體", "2303": "半導體", "2382": "電腦及週邊"}
themes = {"AI伺服器": ["2382", "2330"], "空題材": ["9999"]}
groups = L.memberships(imap, themes)
quotes = {
    "2330": {"v": 600, "p": 2.0, "c": 1000, "m": "上市"},
    "2303": {"v": 200, "p": -1.0, "c": 50, "m": "上市"},
    "2382": {"v": 150, "p": 0.0, "c": 300, "m": "上市"},
    "0050": {"v": 50, "p": 1.0, "c": 100, "m": "上市"},
    "6488": {"v": 0, "p": None, "c": None, "m": "上櫃"},
}
base = {"days": 20, "total": 900, "ind": {"半導體": 70.0, "電腦及週邊": 10.0}, "th": {"AI伺服器": 50.0}}
at = datetime(2026, 10, 22, 10, 0, tzinfo=L.TPE)

gv = L.group_values(quotes, groups)
assert gv["ind"] == {"半導體": 800, "電腦及週邊": 150, "ETF": 50, "其他": 0}, gv
assert gv["th"] == {"AI伺服器": 750}, gv

past = ({"ind": {"半導體": 700, "電腦及週邊": 100}, "th": {"AI伺服器": 650}}, 900)
hist = {"ts": [], "ind": {}, "th": {}}
L.add_sample(hist, at, gv, {"th": list(themes)})
p = L.aggregate(quotes, {"2330": "台積電"}, groups, base, at, "open", past, hist, themes)
assert p["total"] == 1000 and p["flow"] == 100 and p["count"] == 4 and p["up"] == 2 and p["dn"] == 1, p
semi = p["ind"][0]
assert semi["n"] == "半導體" and semi["v"] == 800 and semi["s"] == 80.0 and semi["a"] == 70.0, semi
assert semi["p"] == round((2.0 * 600 - 1.0 * 200) / 800, 2), semi        # 以成交值加權的漲跌幅
assert semi["f"] == 100 and semi["fs"] == 100.0, semi                      # 近 5 分鐘：800-700，占全市場流入 100 的 100%
assert semi["top"][0][:2] == ["2330", "台積電"] and semi["top"][1][1] == "2303"
assert semi["h"] == [0] or semi["h"] == [round(800 / 1e6)], semi["h"]
names = [g["n"] for g in p["ind"]]
assert "ETF" in names and "其他" not in names, names                       # 沒成交的不列
ai = next(g for g in p["th"] if g["n"] == "AI伺服器")
assert ai["v"] == 750 and ai["k"] == 2 and ai["f"] == 100, ai
empty = next(g for g in p["th"] if g["n"] == "空題材")
assert empty["v"] == 0 and empty["k"] == 0, empty                          # 題材還沒成交也列出來

# 板塊走勢：中途才出現的板塊前面補 0
hist = {"ts": [], "ind": {}, "th": {}}
L.add_sample(hist, at, {"ind": {"A": 1e6}, "th": {}}, {})
L.add_sample(hist, at, {"ind": {"A": 2e6, "B": 3e6}, "th": {}}, {})
assert hist["ind"] == {"A": [1, 2], "B": [0, 3]}, hist

# 成交值單位判斷
class S:
    def __init__(self, amt, vol, avg):
        self.total_amount, self.total_volume, self.average_price = amt, vol, avg
assert L.amount_scale([S(1000 * 1000 * 10, 1000, 10)]) == 1
assert L.amount_scale([S(1000 * 10, 1000, 10)]) == 1000

# 基準占比與休市判斷用真實資料檔跑一次，只確認格式
b = L.baseline(L.load_imap(), L.load_themes())
assert b["days"] > 0 and abs(sum(b["ind"].values()) - 100) < 0.5, sum(b["ind"].values())
assert not L.trading_day(datetime(2026, 10, 24).date())                    # 星期六
print("全部通過")
