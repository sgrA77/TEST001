#!/usr/bin/env python3
"""SOX_FETCH.py - ^SOX(필라델피아 반도체지수) 일봉 -> sox.json (GitHub Actions)"""
import json, time, requests
UA = {"User-Agent": "Mozilla/5.0"}
out = {}
for s, q in (("SOX", "%5ESOX"), ("SOXX", "SOXX"), ("SOXL", "SOXL"), ("USD", "USD")):
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?period1=631152000&period2=1900000000&interval=1d", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            qq = j["indicators"]["quote"][0]
            rows = [[t, qq["close"][i]] for i, t in enumerate(j["timestamp"]) if qq["close"][i] is not None]
            out[s] = {"rows": rows}; print(s, len(rows)); break
        except Exception as e:
            print("::warning::", s, host, e); time.sleep(2)
json.dump(out, open("sox.json", "w"))
