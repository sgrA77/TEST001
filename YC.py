#!/usr/bin/env python3
"""YC.py - 연봉(올해 1월 첫 거래일 시가 기준) 양/음봉 정보. 하루 1회 -> yc-data 브랜치 yc.json
{updated, year, items:{심볼:{o:연시가, h:올해고가, l:올해저가, c:최근종가}}}"""
import json, time, datetime as dt, requests
UA = {"User-Agent": "Mozilla/5.0"}
SYMS = ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","TSM","MU","AMD","AVGO"]
def one(s):
    for host in ("query1","query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{s}?range=ytd&interval=1d", headers=UA, timeout=20)
            res = r.json()["chart"]["result"][0]; q = res["indicators"]["quote"][0]
            o = [x for x in q["open"] if x]; h = [x for x in q["high"] if x]; l = [x for x in q["low"] if x]; c = [x for x in q["close"] if x]
            return {"o": round(o[0],2), "h": round(max(h),2), "l": round(min(l),2), "c": round(res["meta"].get("regularMarketPrice") or c[-1],2)}
        except Exception:
            time.sleep(1)
    return None
items = {s: one(s) for s in SYMS}
items = {k: v for k, v in items.items() if v}
now = dt.datetime.utcnow() + dt.timedelta(hours=9)
json.dump({"updated": now.strftime("%Y-%m-%d %H:%M"), "year": now.year, "items": items}, open("yc.json","w"), ensure_ascii=False, separators=(",",":"))
print(len(items), "/", len(SYMS))
