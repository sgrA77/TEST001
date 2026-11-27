#!/usr/bin/env python3
"""HS_FETCH.py - 반도체 ETF 상위 구성종목 주간 종가 -> hs.json (GitHub Actions)"""
import json, time, requests
UA = {"User-Agent": "Mozilla/5.0"}
TK = ["SMH","SOXX","NVDA","TSM","AVGO","ASML","AMD","MU","INTC","TXN","QCOM","AMAT","LRCX","KLAC","ADI","MRVL","NXPI","MCHP","ARM","ORCL","CRWV","MSFT","AMZN","GOOGL","META","ANT","000660.KS","005930.KS","^KS11","^GSPC","^NDX","GLW","LITE","COHR","CIEN","AAOI","FN","CRDO","ALAB","ANET","APH","AXTI","FCX","SCCO","VRT","GEV","ETN","BE","PWR","NVT","CEG","MOD","SNDK","WDC","STX","TSLA","SPCX","RKLB","ASTS","PL","LUNR","RDW","FLY","VOYG","SATS","IRDM","GSAT","KRMN","BKSY","KTOS","TDY","VIAV","012450.KS","272210.KS","099320.KQ","009150.KS","295310.KQ","347700.KQ","274090.KQ","189300.KQ","042700.KS","462350.KQ","451760.KQ","211270.KQ","361390.KQ","368770.KQ","010820.KS","001430.KS","027360.KS","006800.KS","064350.KS","373220.KS","ATI","CRS","WWD","STM"]
out = {}
for s in TK:
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{s}?period1=1567296000&period2=1900000000&interval=1wk&events=split", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            qq = j["indicators"]["quote"][0]
            rows = [[t, qq["close"][i]] for i, t in enumerate(j["timestamp"]) if qq["close"][i] is not None]
            out[s] = {"rows": rows, "splits": [[int(k), v["numerator"], v["denominator"]] for k, v in (j.get("events") or {}).get("splits", {}).items()]}; print(s, len(rows)); break
        except Exception as e:
            print("::warning::", s, host, e); time.sleep(2)
json.dump(out, open("hs.json", "w"))
