"""離線測試解析邏輯：資料依各來源實際回傳的格式仿製。 python3 tests/test_parse.py"""
import json
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
print("全部通過")
