#!/usr/bin/env python3
"""HJ_FETCH.py - hj_targets.json 종목의 일봉 전체 이력(야후·네이버) -> hj_prices.json (GitHub Actions)"""
import json, re, time, requests, datetime as dt
from concurrent.futures import ThreadPoolExecutor
UA = {"User-Agent": "Mozilla/5.0"}
T = json.load(open("hj_targets.json", encoding="utf-8"))

def yahoo(code, mkt):
    suf = ".KQ" if mkt == "코스닥" else ".KS"
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{code}{suf}?period1=0&period2=1900000000&interval=1d&events=split", headers=UA, timeout=60)
            j = r.json()["chart"]["result"][0]
            q = j["indicators"]["quote"][0]
            rows = [[t, c] for t, c in zip(j["timestamp"], q["close"]) if c is not None]
            sp = [[int(k), v["numerator"], v["denominator"]] for k, v in (j.get("events") or {}).get("splits", {}).items()]
            return {"rows": rows, "splits": sp, "meta": {k: j["meta"].get(k) for k in ("regularMarketPrice", "firstTradeDate", "currency")}}
        except Exception as e:
            err = str(e); time.sleep(1)
    return {"err": err}

def naver(code):
    try:
        r = requests.get(f"https://api.finance.naver.com/siseJson.naver?symbol={code}&requestType=1&startTime=19700101&endTime=20991231&timeframe=day", headers=UA, timeout=60)
        txt = r.text.replace("'", '"')
        rows = []
        for m in re.finditer(r'\["(\d{8})",\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(-?\d+),\s*(\d+)', txt):
            d, o, h, l, c, v = m.groups()
            rows.append([d, int(h), int(l), int(c)])
        return {"rows": rows}
    except Exception as e:
        return {"err": str(e)}

def one(t):
    return t["code"], {"y": yahoo(t["code"], t["mkt"]), "n": naver(t["code"])}

with ThreadPoolExecutor(max_workers=6) as ex:
    res = dict(ex.map(one, T))
for c, v in res.items():
    print(c, len(v["y"].get("rows", [])), len(v["n"].get("rows", [])), v["y"].get("err", ""), v["n"].get("err", ""))
json.dump(res, open("hj_prices.json", "w"), separators=(",", ":"))
