#!/usr/bin/env python3
"""USHIST_FETCH.py - 미국 지수 장기 일봉(최대 기간) 수집 -> ushist.json (GitHub Actions)"""
import json, time, requests
UA = {"User-Agent": "Mozilla/5.0"}
SYMS = {"^GSPC": "S&P500", "^NDX": "NASDAQ100", "^IXIC": "NASDAQ Comp", "^DJI": "DOW", "SPY": "SPY", "QQQ": "QQQ"}
out = {}
for s in SYMS:
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{s}?period1=-1325635200&period2=1900000000&interval=1d", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            q = j["indicators"]["quote"][0]
            rows = [[t, q["open"][i], q["high"][i], q["low"][i], q["close"][i]] for i, t in enumerate(j["timestamp"]) if q["close"][i] is not None]
            out[s] = rows; print(s, len(rows)); break
        except Exception as e:
            print("::warning::", s, host, e); time.sleep(2)
json.dump(out, open("ushist.json", "w"))
