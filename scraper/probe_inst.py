"""實測三大法人買賣金額彙總表（大盤層級）：證交所 BFI82U、櫃買中心 3itrdsum。"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_turnover import get_text, BROWSER_UA  # noqa: E402

URLS = [
    ("上市 BFI82U", "https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate=20261030&response=json"),
    ("上櫃 3itrdsum 舊網址", "https://www.tpex.org.tw/web/stock/3insti/3insti_summary/3itrdsum_result.php?l=zh-tw&t=D&p=1&d=115/10/30&o=json"),
    ("上櫃 3itrdsum 新網址", "https://www.tpex.org.tw/www/zh-tw/insti/summary?type=Daily&date=2026%2F10%2F30&response=json"),
]
for name, url in URLS:
    print("=" * 10, name)
    try:
        t = get_text(url, ua=BROWSER_UA)
        try:
            j = json.loads(t)
            print(json.dumps(j, ensure_ascii=False)[:2500])
        except ValueError:
            print("不是 JSON：", t[:500])
    except Exception as e:  # noqa: BLE001
        print("失敗：", e)
