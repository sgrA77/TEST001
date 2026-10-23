#!/usr/bin/env python3
"""ETFCMP_FETCH.py - ETF·종목·환율 일봉(종가·수정종가) 2022-12 ~ 현재 -> etfcmp.json (GitHub Actions)"""
import json, time, requests
UA = {"User-Agent": "Mozilla/5.0"}
SYMS = ["SOXX", "QQQ", "SPY", "VOO", "GLD", "IAU", "132030.KS", "411060.KS", "360750.KS", "133690.KS", "381180.KS", "KRW=X"]
P1 = 1669852800  # 2022-12-01
out = {}
for s in SYMS:
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{s}?period1={P1}&period2=1900000000&interval=1d&events=div%7Csplit", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            q = j["indicators"]["quote"][0]; adj = j["indicators"]["adjclose"][0]["adjclose"]
            rows = [[t, q["close"][i], adj[i]] for i, t in enumerate(j["timestamp"]) if q["close"][i] is not None and adj[i] is not None]
            divs = [[v["date"], v["amount"]] for v in (j.get("events", {}).get("dividends", {}) or {}).values()]
            out[s] = {"rows": rows, "divs": sorted(divs)}; print(s, len(rows), len(divs)); break
        except Exception as e:
            print("::warning::", s, host, e); time.sleep(2)
json.dump(out, open("etfcmp.json", "w"))
