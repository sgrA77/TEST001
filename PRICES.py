#!/usr/bin/env python3
"""PRICES.py - 관심 종목 현재가 경량 수집 (GitHub Actions 루프, 10분 간격)

- 대상: MA.py 의 대상 전체(ma_watch + 대시보드 MARKET/성장률 + 핀) + 환율·VIX
- 야후 chart range=1d: regularMarketPrice, chartPreviousClose
- 결과: prices.json {updated, p:{심볼:[현재가, 전일종가]}}  (실패 종목은 이전 값 유지)
"""
import json, sys, time, datetime as dt, requests
from concurrent.futures import ThreadPoolExecutor
import MA

UA = {"User-Agent": "Mozilla/5.0"}
EXTRA = ["KRW=X", "JPY=X", "^VIX"]


def one(sym):
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=1d", headers=UA, timeout=20)
            m = r.json()["chart"]["result"][0]["meta"]
            return sym, [round(float(m["regularMarketPrice"]), 4), round(float(m.get("chartPreviousClose") or m.get("previousClose")), 4)]
        except Exception:
            time.sleep(1)
    return sym, None


def main():
    try:
        old = json.load(open("prices.json", encoding="utf-8")).get("p", {})
    except Exception:
        old = {}
    syms = list(dict.fromkeys([t[0] for t in MA.collect_targets()] + EXTRA))
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = dict(ex.map(one, syms))
    p = dict(old)
    ok = 0
    for s, v in res.items():
        if v:
            p[s] = v; ok += 1
    print(f"ok {ok}/{len(syms)}")
    if ok == 0:
        sys.exit(1)
    now = dt.datetime.utcnow() + dt.timedelta(hours=9)
    json.dump({"updated": now.strftime("%Y-%m-%d %H:%M"), "p": p}, open("prices.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
