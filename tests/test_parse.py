"""離線測試解析邏輯：資料依各來源實際回傳的格式仿製。 python3 tests/test_parse.py"""
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scraper"))
from fetch_turnover import parse_twse, parse_tpex, parse_us, top_of, roc_date, to_num, tw_kind, us_session_date, suspicious

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
assert us_session_date(datetime(2026, 10, 7, 22, 30, tzinfo=timezone.utc)) == "2026-10-07"     # 週三收盤後
assert us_session_date(datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc)) == "2026-10-09"     # 週一開盤前 → 上週五
assert suspicious({"total_value": 1}, {"total_value": 100}) and not suspicious({"total_value": 90}, {"total_value": 100})

# 歷史檔：只留最近 KEEP_DAYS 天，日期清單由新到舊
import tempfile, fetch_turnover as ft
with tempfile.TemporaryDirectory() as tmp:
    ft.DATA = Path(tmp)
    for i in range(1, 36):
        dates = ft.save_history("tw", {"date": "2026-%02d-%02d" % (8 + i // 29, i % 28 + 1), "rows": [{"code": "2330"}]})
    assert len(dates) == ft.KEEP_DAYS and dates == sorted(dates, reverse=True)
    assert len(list((Path(tmp) / "history" / "tw").glob("*.json"))) == ft.KEEP_DAYS
    assert ft.save_history("tw", {"status": "failed", "rows": []}) == dates          # 失敗的結果不會存成歷史

# 當日走勢：富果日內 K 線、Alpaca 多檔 K 線
FUGLE = {"date": "2026-10-07", "symbol": "2330", "timeframe": "5", "data": [
    {"date": "2026-10-07T09:00:00.000+08:00", "open": 2590, "high": 2595, "low": 2585, "close": 2592, "volume": 8450, "average": 2590.1},
    {"date": "2026-10-07T09:05:00.000+08:00", "open": 2592, "high": 2600, "low": 2590, "close": 2598, "volume": 3000, "average": 2594.0}]}
assert ft.parse_fugle(FUGLE, "2026-10-07") == [2590, 2592, 2598]
assert ft.parse_fugle(FUGLE, "2026-10-08") is None and ft.parse_fugle({"date": "2026-10-07", "data": []}, "2026-10-07") is None
bars = {}
assert ft.parse_alpaca({"bars": {"NVDA": [{"t": "2026-10-06T13:30:00Z", "o": 234.0, "h": 236, "l": 233, "c": 235.5, "v": 1, "n": 1, "vw": 235}]},
                        "next_page_token": "abc"}, bars) == "abc"
assert ft.parse_alpaca({"bars": {"NVDA": [{"t": "2026-10-06T13:40:00Z", "o": 235.5, "h": 239, "l": 235, "c": 238.9, "v": 1, "n": 1, "vw": 237}]},
                        "next_page_token": None}, bars) is None
assert bars == {"NVDA": [(234.0, 235.5), (235.5, 238.9)]}
assert ft.us_session_utc("2026-10-06") == ("2026-10-06T13:30:00Z", "2026-10-06T20:00:00Z")      # 夏令時間
assert ft.us_session_utc("2026-12-01") == ("2026-12-01T14:30:00Z", "2026-12-01T21:00:00Z")      # 冬令時間
rows = [{"code": "2330"}, {"code": "2454"}]
ft.reuse_sparks(rows, {"date": "2026-10-07", "rows": [{"code": "2330", "spark": [1, 2]}]}, "2026-10-07")
assert rows[0]["spark"] == [1, 2] and "spark" not in rows[1]
ft.FUGLE_KEY = ""
assert ft.add_tw_sparks(rows, "2026-10-07") == (1, 0)          # 沒設金鑰：不連線
print("全部通過")
