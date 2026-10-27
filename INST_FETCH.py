#!/usr/bin/env python3
"""INST_FETCH.py - 자산군/섹터/대형주 일봉(수정종가) -> inst.json (GitHub Actions)"""
import json, time, requests
UA = {"User-Agent": "Mozilla/5.0"}
SYMS = ["SPY","QQQ","XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","XLB","XLC","TLT","IEF","AGG","GLD","EFA","EEM","VNQ","HYG","DBC","BIL",
        "AAPL","MSFT","AMZN","GOOGL","META","NVDA","TSLA","AVGO","NFLX","XOM","CVX","JPM","BAC","BRK-B","JNJ","LLY","UNH","WMT","KO","INTC","GE","C","WFC","AMD","TSM","005930.KS","000660.KS"]
out = {}
for s in SYMS:
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{s}?period1=1104537600&period2=1900000000&interval=1d&events=div,split", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            ts = j["timestamp"]; adj = j["indicators"]["adjclose"][0]["adjclose"]
            rows = [[t, a] for t, a in zip(ts, adj) if a is not None]
            out[s] = rows; print(s, len(rows)); break
        except Exception as e:
            print("::warning::", s, host, e); time.sleep(2)
json.dump(out, open("inst.json", "w"))
