"""離線測試解析邏輯：資料依各來源實際回傳的格式仿製。 python3 tests/test_parse.py"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
from fetch_turnover import parse_twse, parse_tpex, parse_us, top_of, roc_date, to_num, tw_kind, suspicious

# 證交所 openapi：物件陣列
OPENAPI = [
    {"Date": "1151005", "Code": "00400A", "Name": "主動國泰動能高息", "TradeVolume": "49479634", "TradeValue": "811259179",
     "OpeningPrice": "16.20", "HighestPrice": "16.54", "LowestPrice": "16.19", "ClosingPrice": "16.52", "Change": "0.7400", "Transaction": "9712"},
    {"Date": "1151005", "Code": "2330", "Name": "台積電", "TradeVolume": "30000000", "TradeValue": "45000000000",
     "OpeningPrice": "1490.00", "HighestPrice": "1510.00", "LowestPrice": "1485.00", "ClosingPrice": "1500.00", "Change": "-15.0000", "Transaction": "50000"},
    {"Date": "1151005", "Code": "2881A", "Name": "富邦特", "TradeVolume": "1000", "TradeValue": "60000",
     "OpeningPrice": "60.00", "HighestPrice": "60.00", "LowestPrice": "60.00", "ClosingPrice": "60.00", "Change": "0.0000", "Transaction": "1"},
    {"Date": "1151005", "Code": "1234", "Name": "沒成交", "TradeVolume": "0", "TradeValue": "0",
     "OpeningPrice": "", "HighestPrice": "", "LowestPrice": "", "ClosingPrice": "", "Change": "", "Transaction": "0"},
]
date, rows, total = parse_twse(OPENAPI)
assert date == "2026-10-05", date
assert [r["code"] for r in rows] == ["00400A", "2330"], rows          # 特別股與沒成交的不收
assert rows[0]["etf"] and not rows[1]["etf"]
assert rows[1]["pct"] == round(-15 / 1515 * 100, 2) and rows[1]["value"] == 45000000000
assert total == 811259179 + 45000000000 + 60000

# 證交所 www：fields + data
WWW = {"stat": "OK", "date": "20261006", "fields": ["證券代號", "證券名稱", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數"],
       "data": [["2330", "台積電", "30,000,000", "45,000,000,000", "1,490.00", "1,510.00", "1,485.00", "1,500.00", "+15.00", "50,000"],
                ["0050", "元大台灣50", "10,000,000", "2,000,000,000", "200.00", "201.00", "199.00", "200.00", "X0.00", "9,000"]]}
date, rows, total = parse_twse(WWW)
assert date == "2026-10-06" and len(rows) == 2 and rows[0]["close"] == 1500 and rows[0]["pct"] == round(15 / 1485 * 100, 2)
assert rows[1]["etf"] and rows[1]["pct"] is None                      # 漲跌欄不是數字時不算漲跌幅

# 櫃買中心
TPEX = [{"Date": "1151006", "SecuritiesCompanyCode": "6488", "CompanyName": "環球晶", "Close": "400.00", "Change": "+5.00",
         "TradingShares": "5000000", "TransactionAmount": "2000000000"},
        {"Date": "1151006", "SecuritiesCompanyCode": "00679B", "CompanyName": "元大美債20年", "Close": "28.00", "Change": "-0.10",
         "TradingShares": "90000000", "TransactionAmount": "2520000000"},
        {"Date": "1151006", "SecuritiesCompanyCode": "712345", "CompanyName": "某權證", "Close": "1.00", "Change": "0.00",
         "TradingShares": "1000", "TransactionAmount": "1000"},
        {"Date": "1151006", "SecuritiesCompanyCode": "5347", "CompanyName": "世界", "Close": "---", "Change": "除息",
         "TradingShares": "0", "TransactionAmount": "0"}]
date, rows, total = parse_tpex(TPEX)
assert date == "2026-10-06" and [r["code"] for r in rows] == ["6488", "00679B"] and rows[0]["market"] == "上櫃"

many = [dict(rows[0], code=str(1000 + i), value=1000 - i) for i in range(130)] + [dict(rows[1], code="00%03d" % i, value=5000 - i) for i in range(70)]
kept = top_of(many)
assert len(kept) == 150 and sum(r["etf"] for r in kept) == 50

# Nasdaq
US = {"data": {"asof": None, "headers": {}, "rows": [
    {"symbol": "NVDA", "name": "NVIDIA Corporation Common Stock", "lastsale": "$150.00", "netchange": "3.00", "pctchange": "2.041%",
     "volume": "200000000", "marketCap": "3.6E12", "country": "United States", "sector": "Technology"},
    {"symbol": "BRK/A", "name": "Berkshire", "lastsale": "$700000", "netchange": "0", "pctchange": "0%", "volume": "100", "sector": ""},
    {"symbol": "GOOGL", "name": "Alphabet Inc. Class A Common Stock", "lastsale": "$180.50", "netchange": "-1.50", "pctchange": "-0.824%",
     "volume": "30000000", "sector": "Technology"},
    {"symbol": "ZZZ", "name": "No trade", "lastsale": "$1.00", "netchange": "", "pctchange": "", "volume": "0", "sector": ""}]}}
rows, total = parse_us(US)
assert [r["code"] for r in rows] == ["NVDA", "GOOGL"], rows
assert rows[0]["name"] == "NVIDIA Corporation" and rows[1]["name"] == "Alphabet Inc."
assert rows[0]["value"] == 30000000000 and rows[0]["pct"] == round(3 / 147 * 100, 2) and rows[1]["pct"] < 0

assert roc_date("115/10/06") == "2026-10-06" and to_num("--") is None and to_num("1,234.5") == 1234.5
assert tw_kind("0050") == "etf" and tw_kind("2330") == "stock" and tw_kind("2881A") is None
assert suspicious({"total_value": 1}, {"total_value": 100}) and not suspicious({"total_value": 90}, {"total_value": 100})

# 歷史檔：只留最近 KEEP_DAYS 天，日期清單由新到舊
import tempfile, fetch_turnover as ft
with tempfile.TemporaryDirectory() as tmp:
    ft.DATA = Path(tmp)
    for i in range(70):
        dates = ft.save_history("tw", {"date": "2026-%02d-%02d" % (1 + i // 28, i % 28 + 1), "rows": [{"code": "2330"}]})
    assert len(dates) == ft.KEEP_DAYS and dates == sorted(dates, reverse=True)
    assert len(list((Path(tmp) / "history" / "tw").glob("*.json"))) == ft.KEEP_DAYS
    assert ft.save_history("tw", {"status": "failed", "rows": []}) == dates          # 失敗的結果不會存成歷史

# 來源還沒同步時，不能用只有上市的排行蓋掉同一天的完整排行
with tempfile.TemporaryDirectory() as tmp:
    ft.DATA = Path(tmp)
    full = {"date": "2026-10-06", "status": "ok", "updated": "x", "total_value": 100, "rows": [{"code": "2330", "value": 9}, {"code": "6488", "value": 5}]}
    (Path(tmp) / "tw.json").write_text(json.dumps(full), encoding="utf-8")
    part = lambda: {"date": "2026-10-06", "status": "partial", "error": "上櫃：還沒同步", "total_value": 60, "rows": [{"code": "2330", "name": "台積電", "value": 9}]}
    assert ft.run("tw", "台股", part) is True
    assert json.loads((Path(tmp) / "tw.json").read_text(encoding="utf-8")) == full
    newer = lambda: dict(part(), date="2026-10-07")
    assert ft.run("tw", "台股", newer) is False                      # 新的一天只有上市：照寫，但標記為不完整
    assert json.loads((Path(tmp) / "tw.json").read_text(encoding="utf-8"))["date"] == "2026-10-07"

# 證交所官網回 CSV 時也要能讀
CSVTEXT = '\ufeff"日期","證券代號","證券名稱","成交股數","成交金額","開盤價","最高價","最低價","收盤價","漲跌價差","成交筆數"\r\n' \
    '"1151007","00400A","主動國泰動能高息","65642556","1084672563","16.57","16.68","16.43","16.47","-0.1400","17068"\r\n' \
    '"1151007","2330","台積電","30,000,000","45,000,000,000","2,590.00","2,600.00","2,580.00","2,595.00","10.0000","50,000"\r\n'
date, rows, total = parse_twse(ft.records(CSVTEXT.lstrip("\ufeff")))
assert date == "2026-10-07" and [r["code"] for r in rows] == ["00400A", "2330"] and rows[1]["close"] == 2595 and rows[0]["pct"] < 0, (date, rows)
assert ft.records('[{"Code": "2330"}]') == [{"Code": "2330"}]

# ---- 可指定日期的來源（回補用）：格式取自 2026/10/07 實測
MI = {"stat": "OK", "date": "20261006", "tables": [
    {"title": "115年10月06日 大盤統計資訊", "fields": ["成交統計", "成交金額(元)", "成交股數(股)", "成交筆數"], "data": [["1.一般股票", "961,889,298,570", "4,664,694,508", "4,005,991"]]},
    {"title": "115年10月06日 每日收盤行情(全部(不含權證、牛熊證、可展延牛熊證))",
     "fields": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價", "最後揭示買量", "最後揭示賣價", "最後揭示賣量", "本益比"],
     "data": [["0050", "元大台灣50", "70,945,715", "94,076", "8,238,226,818", "116.30", "116.60", "115.70", "116.50", "<p style= color:red>+</p>", "0.55", "116.45", "416", "116.50", "2,743", "0.00"],
              ["00400A", "主動國泰動能高息", "65,642,556", "17,068", "1,084,672,563", "16.57", "16.68", "16.43", "16.47", "<p style= color:green>-</p>", "0.14", "16.46", "170", "16.47", "61", "0.00"],
              ["2330", "台積電", "16,941,183", "70,880", "43,643,595,922", "2,565.00", "2,585.00", "2,560.00", "2,585.00", "<p> </p>", "0.00", "2,580.00", "18", "2,585.00", "494", "29.96"],
              ["2881A", "富邦特", "1,000", "1", "60,000", "60.00", "60.00", "60.00", "60.00", "<p> </p>", "0.00", "", "", "", "", ""]]},
    {}]}
date, rows, total = ft.parse_mi_index(MI)
assert date == "2026-10-06" and [r["code"] for r in rows] == ["0050", "00400A", "2330"], rows
assert rows[0]["change"] == 0.55 and rows[0]["pct"] > 0 and rows[0]["etf"]
assert rows[1]["change"] == -0.14 and rows[1]["pct"] == round(-0.14 / 16.61 * 100, 2)        # 綠色是跌
assert rows[2]["change"] == 0 and rows[2]["pct"] == 0 and not rows[2]["etf"]
assert total == 8238226818 + 1084672563 + 43643595922 + 60000
assert ft.parse_mi_index({"stat": "很抱歉，沒有符合條件的資料!", "type": "ALLBUT0999"}) == (None, [], 0)          # 休市日

OTC_FIELDS = ["代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低", "成交股數  ", " 成交金額(元)", " 成交筆數 ", "最後買價", "最後買量<br>(張數)", "最後賣價", "最後賣量<br>(張數)", "發行股數 ", "次日漲停價 ", "次日跌停價"]
OTC = {"stat": "ok", "date": "20261006", "tables": [{"title": "上櫃股票每日收盤行情(不含定價)", "date": "115/10/06", "fields": OTC_FIELDS, "data": [
    ["00679B", "元大美債20年", "24.33", "-0.17", "24.37", "24.37", "24.29", "28,931,000", "703,547,420", "5,878", "24.32", "564", "24.33", "508", "6,229,692,000", "9,999.95", "0.01"],
    ["6488", "環球晶", "1,205.00", "+25.00", "1,175.00", "1,260.00", "1,145.00", "13,422,000", "16,240,995,000", "10,578", "1,200.00", "177", "1,205.00", "29", "528,113,725", "1,325.00", "1,085.00"],
    ["712345", "某權證", "1.00", "0.00", "1.00", "1.00", "1.00", "1,000", "1,000", "1", "", "", "", "", "", "", ""]]}]}
date, rows, total = ft.parse_tpex_day(OTC)
assert date == "2026-10-06" and [r["code"] for r in rows] == ["00679B", "6488"] and rows[1]["value"] == 16240995000
assert rows[0]["pct"] == round(-0.17 / 24.5 * 100, 2) and rows[1]["pct"] == round(25 / 1180 * 100, 2) and rows[1]["market"] == "上櫃"
assert ft.parse_tpex_day({"stat": "ok", "date": "20261004", "tables": [{"fields": OTC_FIELDS, "data": []}]}) == (None, [], 0)   # 休市日

# ---- 全市場存檔、均值與放大倍數、產業、回補
def mk(code, value, pct=1.0, market="上市"):
    return {"code": code, "name": "N" + code, "market": market, "etf": code.startswith("00"), "close": 10.0, "change": 0.1, "pct": pct, "volume": 1000, "value": value}

with tempfile.TemporaryDirectory() as tmp:
    ft.DATA = Path(tmp)
    ft.values_before.__defaults__[0].clear()
    ft.industry_path().write_text(json.dumps({"updated": ft.datetime.now(ft.TPE).isoformat(), "map": {"2330": "半導體", "2454": "半導體", "2881": "金融保險"}}), encoding="utf-8")
    for i in range(1, 8):                                   # 7 個交易日：2330 每天 100，2454 只有 3 天有資料
        ft.save_full("2026-09-%02d" % i, [mk("2330", 100), mk("2881", 50)] + ([mk("2454", 10)] if i > 4 else []), [mk("6488", 20, market="上櫃")])
    snap = ft.snapshot("2026-09-08", [mk("2330", 300, 2.0), mk("2454", 100, -1.0), mk("2881", 50, 0.0), mk("0050", 80, 0.5)], 530, [mk("6488", 20, 4.0, "上櫃")], 20, ["x"])
    by = {r["code"]: r for r in snap["rows"]}
    assert snap["avg_days"] == 7 and by["2330"]["avg"] == 100 and by["2330"]["ratio"] == 3.0 and by["6488"]["ratio"] == 1.0
    assert "ratio" not in by["2454"] and "ratio" not in by["0050"]            # 資料不足 5 天或沒有歷史：不算
    assert by["2330"]["ind"] == "半導體" and by["0050"]["ind"] == "ETF" and by["6488"]["ind"] == "其他"
    ind = {g["name"]: g for g in snap["industries"]}
    assert snap["industries"][0]["name"] == "半導體" and ind["半導體"]["value"] == 400 and ind["半導體"]["count"] == 2
    assert ind["半導體"]["pct"] == round((2.0 * 300 - 1.0 * 100) / 400, 2)   # 成交值加權平均
    assert ind["半導體"]["top"][0] == ["2330", "N2330", 300, 2.0] and ind["ETF"]["value"] == 80
    # 只保留 KEEP_FULL 天
    keep, ft.KEEP_FULL = ft.KEEP_FULL, 3
    ft.save_full("2026-09-08", [mk("2330", 300)], [])
    assert ft.full_dates() == ["2026-09-08", "2026-09-07", "2026-09-06"]
    ft.KEEP_FULL = keep

with tempfile.TemporaryDirectory() as tmp:
    ft.DATA = Path(tmp)
    ft.values_before.__defaults__[0].clear()
    ft.industry_path().write_text(json.dumps({"updated": ft.datetime.now(ft.TPE).isoformat(), "map": {"2330": "半導體"}}), encoding="utf-8")
    ft.time.sleep = lambda s: None
    ft.MIN_ROWS = {"twse": 1, "tpex": 1, "us": 1}
    calls = []
    def fake_day(d):
        calls.append(d)
        if ft.date_weekday(d) == 2:                          # 假裝每週三休市（例如颱風假）
            return None
        return [mk("2330", 100 + len(calls))], 100, [mk("6488", 20, market="上櫃")], 20
    ft.fetch_day = fake_day
    assert ft.backfill(8) == 0
    assert len(ft.full_dates()) == 8 and not any(ft.date_weekday(d) >= 5 for d in calls)       # 週末不連線
    assert not any(ft.date_weekday(d) == 2 for d in ft.full_dates())                           # 休市日沒有存檔
    dates = json.loads((Path(tmp) / "tw_dates.json").read_text(encoding="utf-8"))["dates"]
    assert dates == ft.full_dates()
    newest = json.loads((Path(tmp) / "tw.json").read_text(encoding="utf-8"))
    assert newest["date"] == dates[0] and newest["avg_days"] == 7 and "ratio" in newest["rows"][0]
    oldest = json.loads((Path(tmp) / "history" / "tw" / (dates[-1] + ".json")).read_text(encoding="utf-8"))
    assert oldest["avg_days"] == 0 and "ratio" not in oldest["rows"][0]
    n = len(calls)
    assert ft.backfill(8) == 0 and len(calls) == n                                             # 已經有的日期不重抓
    assert ft.backfill(8, force=True) == 0 and len(calls) > n                                  # force：全部重抓

# ---- 美股休市：內容和前一個交易日完全相同就不存檔
with tempfile.TemporaryDirectory() as tmp:
    ft.DATA = Path(tmp)
    usrow = lambda c, v: {"code": "NVDA", "name": "NVIDIA", "close": c, "volume": v, "value": int(c * v), "pct": 1.0, "change": 1.0}
    old = {"date": "2026-10-09", "status": "ok", "updated": "x", "total_value": 100, "rows": [usrow(100.0, 5)]}
    (Path(tmp) / "us.json").write_text(json.dumps(old), encoding="utf-8")
    assert ft.run("us", "美股", lambda: {"date": "2026-10-12", "status": "ok", "total_value": 100, "rows": [usrow(100.0, 5)]}) is True
    assert json.loads((Path(tmp) / "us.json").read_text(encoding="utf-8")) == old and not (Path(tmp) / "history" / "us" / "2026-10-12.json").exists()
    assert ft.run("us", "美股", lambda: {"date": "2026-10-13", "status": "ok", "total_value": 110, "rows": [usrow(101.0, 6)]}) is True
    assert json.loads((Path(tmp) / "us.json").read_text(encoding="utf-8"))["date"] == "2026-10-13"

# 美股改用 Polygon：日期與價量以 Polygon 為準，名稱產業來自 Nasdaq 清單；成交值用成交均價
G6 = {"results": [{"T": "NVDA", "v": 100.0, "vw": 240.0, "o": 242.1, "c": 239.24}, {"T": "SPY", "v": 50.0, "vw": 779.0, "c": 779.09},
                  {"T": "BRK.B", "v": 10.0, "vw": 500.0, "c": 501.0}, {"T": "ZERO", "v": 0, "c": 1.0}]}
G5 = {"results": [{"T": "NVDA", "v": 127.0, "vw": 238.0, "c": 238.9}]}
day, prev = ft.parse_grouped(G6), ft.parse_grouped(G5)
assert "ZERO" not in day and day["NVDA"] == (239.24, 100.0, 24000.0)
snap = ft.us_snapshot("2026-10-06", day, prev, {"NVDA": ["NVIDIA Corporation", "Technology"], "BRK/B": ["Berkshire", "Finance"], "GONE": ["x", ""]})
assert snap["date"] == "2026-10-06" and [r["code"] for r in snap["rows"]] == ["NVDA", "BRK/B"] and snap["count"] == 2      # SPY 不在清單（ETF）不收
assert snap["rows"][0]["change"] == 0.34 and snap["rows"][0]["pct"] == 0.14 and snap["rows"][0]["value"] == 24000 and snap["rows"][1]["pct"] is None
# 找交易日：還沒開放的日子與休市日都跳過，日期完全照 Polygon
from datetime import date as _date
calls = []
def fake_day(d):
    calls.append(d)
    if d == "2026-10-07":
        raise ft.NotYet("before end of day")
    return {} if d == "2026-10-05" else {"T%d" % i: (1.0, 1.0, 1.0) for i in range(ft.MIN_ROWS["us"])}
real_day, ft.polygon_day = ft.polygon_day, fake_day
got = ft.us_sessions(2, start=_date(2026, 10, 8))
ft.polygon_day = real_day
assert [d for d, _ in got] == ["2026-10-06", "2026-10-02"] and calls == ["2026-10-07", "2026-10-06", "2026-10-05", "2026-10-02"], (got and [d for d, _ in got], calls)

# 台股當日走勢：富果歷史 K 線回傳是新到舊，要排回舊到新；不是指定日期的不收
FK = {"symbol": "2330", "timeframe": "10", "data": [
    {"date": "2026-10-07T13:30:00.000+08:00", "open": 2585, "close": 2585}, {"date": "2026-10-07T13:20:00.000+08:00", "open": 2575, "close": 2575},
    {"date": "2026-10-07T09:10:00.000+08:00", "open": 2575, "close": 2580}, {"date": "2026-10-07T09:00:00.000+08:00", "open": 2565, "close": 2575},
    {"date": "2026-10-06T13:30:00.000+08:00", "open": 1, "close": 1}]}
assert ft.fugle_closes(FK, "2026-10-07") == [2565, 2575, 2580, 2575, 2585]
assert ft.fugle_closes(FK, "2026-10-08") is None and ft.fugle_closes({}, "2026-10-07") is None
print("全部通過")
