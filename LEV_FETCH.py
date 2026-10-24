#!/usr/bin/env python3
"""LEV_FETCH.py - 2x 레버리지 ETF 전체 이력(종가·분할) -> lev.json (GitHub Actions)"""
import json, time, requests
UA = {"User-Agent": "Mozilla/5.0"}
SYMS = ["SSO","SPUU","QLD","USD","ROM","DDM","UWM","MVV","UGL","AGQ","UCO","SAA","UYG","UPRO","TQQQ","SOXL","QQQ","SPY","SOXX","GLD"]
out = {}
for s in SYMS:
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{s}?period1=946684800&period2=1900000000&interval=1d&events=split", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            q = j["indicators"]["quote"][0]
            rows = [[t, q["close"][i]] for i, t in enumerate(j["timestamp"]) if q["close"][i] is not None]
            sp = [[v["date"], v["numerator"], v["denominator"]] for v in (j.get("events", {}).get("splits", {}) or {}).values()]
            out[s] = {"rows": rows, "splits": sorted(sp)}; print(s, len(rows), len(sp)); break
        except Exception as e:
            print("::warning::", s, host, e); time.sleep(2)
json.dump(out, open("lev.json", "w"))
