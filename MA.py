#!/usr/bin/env python3
"""MA.py - 주봉 이동평균선(MA60·MA120) 추적 (GitHub Actions, API 키 불필요)

- 대상: ma_watch.json 의 items (종목 추가는 거기에 한 줄 추가)
- 야후 파이낸스 chart API 주봉(1wk) 5년 → 주봉 종가로 MA60/MA120 계산
- 마지막 봉은 '이번 주 진행 중인 봉'(현재가 기준)이며 MA에도 포함 (HTS/차트 프로그램 기본과 동일)
- 결과: ma.json   (종목 하나가 실패하면 이전 값 유지, 전부 실패하면 종료코드 1)
"""
import json, sys, time, datetime as dt, requests

UA = {"User-Agent": "Mozilla/5.0"}   # TEST001.py와 동일 (긴 UA는 야후가 빈 응답을 줌)
KEEP = 130   # 차트용 최근 주봉 수


def fetch(sym):
    last = None
    for host in ("query1", "query2"):
        for _ in range(2):
            try:
                r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1wk", headers=UA, timeout=25)
                if not r.text.strip():
                    raise RuntimeError(f"빈 응답 HTTP {r.status_code}")
                res = r.json()["chart"]["result"][0]
                q = res["indicators"]["quote"][0]
                bars = [(t, c) for t, c in zip(res["timestamp"], q["close"]) if c is not None]
                return bars, res["meta"]
            except Exception as e:
                last = e; time.sleep(2)
    raise RuntimeError(f"{sym}: {last}")


def sma(vals, n):
    return [round(sum(vals[i - n + 1:i + 1]) / n, 4) if i + 1 >= n else None for i in range(len(vals))]


def build(sym, tz_off):
    bars, meta = fetch(sym)
    closes = [c for _, c in bars]
    price = meta.get("regularMarketPrice", closes[-1])
    closes[-1] = price                       # 진행 중인 주봉은 현재가로
    dates = [dt.datetime.utcfromtimestamp(t + tz_off).strftime("%Y-%m-%d") for t, _ in bars]
    m60, m120 = sma(closes, 60), sma(closes, 120)
    return {"price": round(price, 4), "currency": meta.get("currency", ""),
            "ma60": m60[-1], "ma120": m120[-1], "weeks": len(closes),
            "dates": dates[-KEEP:], "close": [round(c, 4) for c in closes[-KEEP:]],
            "s60": m60[-KEEP:], "s120": m120[-KEEP:]}


def main():
    cfg = json.load(open("ma_watch.json", encoding="utf-8"))
    try:
        old = {x["symbol"]: x for x in json.load(open("ma.json", encoding="utf-8")).get("items", [])}
    except Exception:
        old = {}
    now = dt.datetime.utcnow() + dt.timedelta(hours=9)
    items, ok = [], 0
    for it in cfg["items"]:
        sym = it["symbol"]
        off = 9 * 3600 if (sym.endswith((".KS", ".KQ")) or sym in ("^KS11", "^KQ11")) else -5 * 3600
        try:
            r = build(sym, off); ok += 1; r["stale"] = False
            print("ok", sym, r["price"], r["ma60"], r["ma120"])
        except Exception as e:
            print("[warn]", sym, e); print(f"::error::{sym} {str(e)[:300]}")
            if sym not in old:
                continue
            r = old[sym]; r["stale"] = True
        r.update(symbol=sym, name=it.get("name", sym), group=it.get("group", ""), mas=it.get("mas", [60, 120]))
        items.append(r)
    if ok == 0:
        print("[error] 전부 실패 — ma.json 유지"); sys.exit(1)
    json.dump({"updated": now.strftime("%Y-%m-%d %H:%M"), "items": items},
              open("ma.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
