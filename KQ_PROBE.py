#!/usr/bin/env python3
"""KQ_PROBE.py - pykrx(KRX) 접근 가능 여부 + Yahoo 코스닥 지수 확인 -> kq_probe.json"""
import json, traceback, requests
out = {}
try:
    from pykrx import stock
    df = stock.get_market_cap_by_ticker("20150102", market="KOSDAQ")
    out["pykrx_cap_rows"] = int(len(df)); out["pykrx_cols"] = [str(c) for c in df.columns]
    out["pykrx_head"] = df.sort_values(df.columns[0], ascending=False).head(5).reset_index().to_dict("records") if len(df) else []
    t = df.index[0]
    o = stock.get_market_ohlcv_by_date("20150101", "20150131", str(t))
    out["pykrx_ohlcv_rows"] = int(len(o))
except Exception as e:
    out["pykrx_err"] = repr(e)[:300]; out["pykrx_tb"] = traceback.format_exc()[-600:]
UA = {"User-Agent": "Mozilla/5.0"}
for s in ("%5EKQ11", "%5EKS11", "%5EKQ150", "229200.KS", "232080.KS", "247540.KQ", "196170.KQ"):
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1=946684800&period2=1900000000&interval=1mo", headers=UA, timeout=60)
        j = r.json()["chart"]["result"][0]
        out["y_" + s] = [len(j["timestamp"]), j["timestamp"][0]]
    except Exception as e:
        out["y_" + s] = "ERR " + repr(e)[:80]
json.dump(out, open("kq_probe.json", "w"), ensure_ascii=False, default=str)
print(out)
