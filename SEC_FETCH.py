#!/usr/bin/env python3
"""SEC_FETCH.py - 섹터 ETF/지수 1999~ 일봉(수정종가) -> sec.json (GitHub Actions)"""
import json, time, requests
UA = {"User-Agent": "Mozilla/5.0"}
SYMS = [("SPY","SPY"),("QQQ","QQQ"),("XLK","XLK"),("XLF","XLF"),("XLE","XLE"),("XLV","XLV"),("XLY","XLY"),("XLP","XLP"),("XLI","XLI"),("XLU","XLU"),("XLB","XLB"),
        ("SOX","%5ESOX"),("IYR","IYR"),("TLT","TLT"),("GLD","GLD"),("EEM","EEM"),("XBI","XBI")]
out = {}
for s, q in SYMS:
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?period1=915148800&period2=1900000000&interval=1d&events=div,split", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            ts = j["timestamp"]
            ind = j["indicators"]
            arr = ind["adjclose"][0]["adjclose"] if "adjclose" in ind else ind["quote"][0]["close"]
            out[s] = [[t, a] for t, a in zip(ts, arr) if a is not None]; print(s, len(out[s])); break
        except Exception as e:
            print("::warning::", s, host, e); time.sleep(2)
json.dump(out, open("sec.json", "w"))
