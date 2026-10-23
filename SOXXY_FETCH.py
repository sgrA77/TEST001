#!/usr/bin/env python3
"""SOXXY_FETCH.py - SOXX와 반도체 대형주 일봉(종가·수정종가) 2018-12 ~ 현재 -> soxxy.json (GitHub Actions)"""
import json, time, requests
UA = {"User-Agent": "Mozilla/5.0"}
SYMS = ["SOXX","NVDA","AVGO","AMD","INTC","QCOM","TXN","MU","AMAT","LRCX","KLAC","MRVL","ADI","MCHP","NXPI","ON","MPWR","TER","SWKS","QRVO","XLNX","MXIM","MLNX","TSM","ASML","ARM","MCHP","WOLF","ENTG"]
P1 = 1543622400  # 2018-12-01
out = {}
for s in dict.fromkeys(SYMS):
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{s}?period1={P1}&period2=1900000000&interval=1d&events=split", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            q = j["indicators"]["quote"][0]
            rows = [[t, q["close"][i]] for i, t in enumerate(j["timestamp"]) if q["close"][i] is not None]
            out[s] = rows; print(s, len(rows)); break
        except Exception as e:
            print("::warning::", s, host, e); time.sleep(2)
json.dump(out, open("soxxy.json", "w"))
